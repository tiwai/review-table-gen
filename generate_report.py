#!/usr/bin/env python3
#
# Copyright (c) 2026 Takashi Iwai
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import base64
import html
import json
import os
import sys
import zlib

def resolve_full_id(dataset, commit_id):
    """If commit_id is short, find the full 40-char ID in the dataset."""
    if len(commit_id) == 40:
        return commit_id
    
    prefix = commit_id[:2]
    
    if isinstance(dataset, str): # Directory path
        prefix_dir = os.path.join(dataset, prefix)
        if not os.path.isdir(prefix_dir):
            return None
        try:
            matches = [d for d in os.listdir(prefix_dir) if d.startswith(commit_id)]
        except:
            return None
    else: # Git Tree object
        try:
            prefix_tree = dataset[prefix]
            matches = [item.name for item in prefix_tree if item.type == 'tree' and item.name.startswith(commit_id)]
        except KeyError:
            return None
    
    if len(matches) == 1:
        return matches[0]
    return None

def get_review_data(dataset, full_id):
    """Retrieve all review files for a given commit in a dataset."""
    prefix = full_id[:2]
    data = {}
    
    def get_blob_content(path):
        if isinstance(dataset, str): # Directory path
            full_path = os.path.join(dataset, prefix, full_id, path)
            if os.path.exists(full_path):
                with open(full_path, "r") as f:
                    return f.read()
        else: # Git Tree object
            try:
                blob = dataset[f"{prefix}/{full_id}/{path}"]
                return blob.data_stream.read().decode('utf-8')
            except KeyError:
                pass
        return None

    metadata_content = get_blob_content("review-metadata.json")
    if metadata_content:
        data["metadata"] = json.loads(metadata_content)
    
    inline_json = get_blob_content("review-inline.json")
    inline_text = get_blob_content("review-inline.txt")
    
    downstream_only = None
    if inline_text:
        # Parse downstream-only findings
        for line in inline_text.splitlines():
            if line.startswith("Findings-downstream-only:"):
                try:
                    downstream_only = int(line.split(":")[1].strip())
                except:
                    pass
                break

    if inline_json:
        data["inline"] = inline_json
        data["inline_is_json"] = True
        if downstream_only is not None:
            data["downstream_only"] = downstream_only
    elif inline_text:
        data["inline"] = inline_text
        data["inline_is_json"] = False
        if downstream_only is not None:
            data["downstream_only"] = downstream_only
            
    pre_verification_content = get_blob_content("review-pre-verification.json")
    if pre_verification_content:
        data["pre_verification"] = pre_verification_content

    fix_patches_content = get_blob_content("review-fix-patches.diff")
    if fix_patches_content:
        data["fix_patches"] = fix_patches_content
            
    return data if data else None

def get_git_tree_path(root_tree, path):
    """Retrieve a Tree or Blob from a Git Tree object by slash-separated path."""
    current = root_tree
    for part in path.split("/"):
        if not part:
            continue
        try:
            current = current[part]
        except KeyError:
            return None
    return current

def get_commit_diff(target_repo, commit_id):
    """Extract the diff for a given commit from the target Git repository."""
    try:
        # Get only the patch/diff of the commit, excluding the commit message
        diff_text = target_repo.git.show(commit_id, format="", no_color=True)
        return diff_text.strip()
    except Exception as e:
        return None

def main():
    parser = argparse.ArgumentParser(description="Generate kernel review report.")
    parser.add_argument("--list", required=True, help="Commit list file")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dataset", help="Database directory")
    group.add_argument("--git", help="Git repository for dataset")
    
    parser.add_argument("--model", action="append", required=True, help="Model directory name (e.g. gpt-oss)")
    parser.add_argument("--git-commit", default="HEAD", help="Git commit ID to read from (default: HEAD)")
    parser.add_argument("--title", default="Potential Regressions", help="Report title")
    parser.add_argument("--rows", type=int, default=50, help="Max rows per page")
    parser.add_argument("--kerncvs", action="store_true", help="Use kerncvs URLs instead of GitHub")
    parser.add_argument("--links-file", help="JSON file containing branch to URL mappings for the branch switcher")
    parser.add_argument("--target-git", help="Git repository for the target code")
    parser.add_argument("--output", default="report.html", help="Output HTML file")
    parser.add_argument("--show-review-time", action="store_true", help="Show review time column in the table by default")
    
    args = parser.parse_args()

    # Parse branch links if provided
    branch_links = {}
    if args.links_file:
        try:
            with open(args.links_file, "r", encoding="utf-8") as f:
                branch_links = json.load(f)
            if not isinstance(branch_links, dict):
                print(f"Error: Links file '{args.links_file}' must be a JSON object mapping names to URLs.")
                sys.exit(1)
        except Exception as e:
            print(f"Error: Could not read links file '{args.links_file}': {e}")
            sys.exit(1)

    # 1. Parse commit list
    commits = []
    with open(args.list, "r") as f:
        for line in f:
            parts = line.strip().split(None, 1)
            if len(parts) < 1:
                continue
            commit_id = parts[0]
            subject = parts[1] if len(parts) > 1 else ""
            commits.append({"id": commit_id, "subject": subject})

    # 2. Collect review data
    processed_data = []
    authors = set()
    
    repo = None
    commit_tree = None
    if args.git:
        import git
        try:
            repo = git.Repo(args.git)
        except Exception as e:
            print(f"Error: Could not open git repository '{args.git}': {e}")
            sys.exit(1)
        
        try:
            git_commit = args.git_commit if args.git_commit else "HEAD"
            commit_obj = repo.commit(git_commit)
            commit_tree = commit_obj.tree
        except Exception as e:
            print(f"Error: Could not find git commit '{args.git_commit}' in {args.git}: {e}")
            sys.exit(1)

    # Pre-resolve dataset trees/dirs
    dataset_sources = {}
    for model_dir_name in args.model:
        if repo:
            model_tree = get_git_tree_path(commit_tree, model_dir_name)
            if not model_tree:
                print(f"Error: Model directory '{model_dir_name}' not found in commit '{args.git_commit}'.")
                sys.exit(1)
            
            desc_blob = get_git_tree_path(commit_tree, f"{model_dir_name}/description")
            if not desc_blob:
                print(f"Error: Description file for model '{model_dir_name}' not found in commit '{args.git_commit}'.")
                sys.exit(1)
            
            model_name = desc_blob.data_stream.read().decode('utf-8').strip()
            dataset_sources[model_name] = model_tree
        else:
            model_path = os.path.join(args.dataset, model_dir_name)
            if not os.path.isdir(model_path):
                print(f"Error: Model directory '{model_path}' not found.")
                sys.exit(1)
            
            desc_path = os.path.join(model_path, "description")
            if not os.path.isfile(desc_path):
                print(f"Error: Description file '{desc_path}' not found.")
                sys.exit(1)
                
            with open(desc_path, "r", encoding="utf-8") as f:
                model_name = f.read().strip()
            
            dataset_sources[model_name] = model_path

    target_repo = None
    if args.target_git:
        import git
        try:
            target_repo = git.Repo(args.target_git)
        except Exception as e:
            print(f"Error: Could not open target git repository '{args.target_git}': {e}")
            sys.exit(1)

    for commit in commits:
        commit_reviews = {}
        has_any_review = False
        commit_full_id = None
        commit_diff = None
        
        for model_name, source in dataset_sources.items():
            # Try to resolve full ID if not already done
            if not commit_full_id:
                commit_full_id = resolve_full_id(source, commit["id"])
            
            if commit_full_id:
                data = get_review_data(source, commit_full_id)
                if data:
                    if target_repo:
                        if commit_diff is None:
                            commit_diff = get_commit_diff(target_repo, commit_full_id) or ""
                        if commit_diff:
                            data["diff"] = commit_diff
                    commit_reviews[model_name] = data
                    has_any_review = True
                    if "metadata" in data and "author" in data["metadata"]:
                        authors.add(data["metadata"]["author"])
        
        if has_any_review:
            processed_data.append({
                "id": commit["id"],
                "full_id": commit_full_id or commit["id"],
                "subject": commit["subject"],
                "reviews": commit_reviews
            })

    # 3. Generate HTML
    html_template = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <link rel="icon" href="data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20100%20100'%3E%3Crect%20width='100'%20height='100'%20rx='20'%20fill='%23007bff'/%3E%3Ctext%20x='50%25'%20y='50%25'%20dominant-baseline='central'%20text-anchor='middle'%20fill='white'%20font-size='60'%20font-family='sans-serif'%20font-weight='bold'%3EK%3C/text%3E%3C/svg%3E">
    <style>
        :root {{
            --bg-color: #f4f4f9;
            --text-color: #333;
            --table-bg: #fff;
            --table-border: #ddd;
            --header-bg: #f2f2f2;
            --dataset-header-bg: #e9ecef;
            --link-color: #0056b3;
            --btn-bg: #007bff;
            --btn-text: #fff;
            --modal-bg: rgba(0,0,0,0.5);
            --modal-content-bg: #fff;
            --pre-bg: #f8f9fa;
            --pre-border: #ddd;
            --diff-added-bg: #e6ffed;
            --diff-added-text: #28a745;
            --diff-removed-bg: #ffeef0;
            --diff-removed-text: #d73a49;
            --diff-header-bg: #f1f8ff;
            --diff-header-text: #005cc5;
            --diff-meta-text: #6a737d;
            --review-subject-bg: #f6f8fa;
            --review-subject-text: #24292e;
            --severity-high-bg: #ffcccc;
            --severity-high-text: #900;
            --severity-medium-bg: #fff3cd;
            --severity-medium-text: #856404;
            --severity-low-bg: #d4edda;
            --severity-low-text: #155724;
            --finding-item-bg: #f8f9fa;
            --code-block-bg: #f8f9fa;
            --code-block-border: #e1e4e8;
            --downstream-highlight-bg: #fff5b1;
            --pre-verification-bg: #e8e8e8;
        }}

        [data-theme="dark"] {{
            --bg-color: #1a1a1b;
            --text-color: #d7dadc;
            --table-bg: #1a1a1b;
            --table-border: #343536;
            --header-bg: #272729;
            --dataset-header-bg: #343536;
            --link-color: #d7dadc;
            --btn-bg: #343536;
            --btn-text: #d7dadc;
            --modal-bg: rgba(0,0,0,0.8);
            --modal-content-bg: #1a1a1b;
            --pre-bg: #272729;
            --pre-border: #343536;
            --diff-added-bg: #1c3321;
            --diff-added-text: #79c0ff;
            --diff-removed-bg: #351d22;
            --diff-removed-text: #ffa198;
            --diff-header-bg: #151d28;
            --diff-header-text: #79c0ff;
            --diff-meta-text: #8b949e;
            --review-subject-bg: #272729;
            --review-subject-text: #d7dadc;
            --severity-high-bg: #4c1a1a;
            --severity-high-text: #ff9999;
            --severity-medium-bg: #4c3e1a;
            --severity-medium-text: #ffcc66;
            --severity-low-bg: #1a4c2a;
            --severity-low-text: #99ff99;
            --finding-item-bg: #272729;
            --code-block-bg: #0d1117;
            --code-block-border: #30363d;
            --inline-view-bg: #1a1a1b;
            --downstream-highlight-bg: #443d00;
            --pre-verification-bg: #333333;
        }}

        [data-theme="psychedelic"] {{
            --bg-color: #2d004d;
            --text-color: #00ffcc;
            --table-bg: #3d0066;
            --table-border: #ff00ff;
            --header-bg: #4d0080;
            --dataset-header-bg: #5d0099;
            --link-color: #ffff00;
            --btn-bg: #ff00ff;
            --btn-text: #fff;
            --modal-bg: rgba(77,0,128,0.8);
            --modal-content-bg: #2d004d;
            --pre-bg: #1a0033;
            --pre-border: #ff00ff;
            --diff-added-bg: #004d00;
            --diff-added-text: #00ff00;
            --diff-removed-bg: #4d0000;
            --diff-removed-text: #ff0000;
            --diff-header-bg: #00004d;
            --diff-header-text: #00ffff;
            --diff-meta-text: #ff00ff;
            --review-subject-bg: #4d0080;
            --review-subject-text: #ffff00;
            --severity-high-bg: #ff0000;
            --severity-high-text: #fff;
            --severity-medium-bg: #ff8000;
            --severity-medium-text: #fff;
            --severity-low-bg: #00ff00;
            --severity-low-text: #000;
            --finding-item-bg: #3d0066;
            --code-block-bg: #1a0033;
            --code-block-border: #ff00ff;
            --inline-view-bg: #2d004d;
            --downstream-highlight-bg: #ff00ff;
            --pre-verification-bg: #4d0080;
        }}

        body {{ font-family: sans-serif; margin: 20px; background-color: var(--bg-color); color: var(--text-color); }}
        h1 {{ color: var(--text-color); }}
        table {{ border-collapse: collapse; width: 100%; background: var(--table-bg); margin-bottom: 20px; }}
        th, td {{ border: 1px solid var(--table-border); padding: 8px; text-align: left; }}
        th {{ background-color: var(--header-bg); }}
        .dataset-header {{ background-color: var(--dataset-header-bg); text-align: center; font-weight: bold; }}
        .issues-cell {{ cursor: pointer; color: var(--link-color); text-decoration: underline; }}
        .visited {{ opacity: 0.6; }}
        .has-pre-verification {{ background-color: var(--pre-verification-bg) !important; }}
        .has-downstream {{ background-color: var(--downstream-highlight-bg) !important; }}
        a {{ color: var(--link-color); }}
        .pagination {{ margin: 20px 0; display: flex; gap: 5px; }}
        .pagination button {{ padding: 5px 10px; cursor: pointer; border: 1px solid var(--table-border); background: var(--table-bg); color: var(--text-color); }}
        .pagination button.active {{ background-color: var(--btn-bg); color: var(--btn-text); border-color: var(--btn-bg); }}
        .pagination .ellipsis {{ padding: 5px 10px; color: var(--text-color); opacity: 0.6; cursor: pointer; }}
        .pagination .ellipsis:hover {{ opacity: 1; text-decoration: underline; }}
        
        .controls-container {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin: 20px 0;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .theme-switcher {{
            display: flex;
            gap: 20px;
            align-items: center;
        }}
        .filter-container {{ margin-bottom: 20px; }}
        .subject-cell {{ 
            max-width: 400px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        
        /* Modal styles */
        .modal {{ display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background-color: var(--modal-bg); }}
        .modal-content {{ background-color: var(--modal-content-bg); margin: 5% auto; padding: 20px; border: 1px solid var(--table-border); width: 80%; max-height: 80%; overflow-y: auto; position: relative; font-size: 16px; color: var(--text-color); }}
        .close {{ position: absolute; right: 20px; top: 10px; font-size: 28px; font-weight: bold; cursor: pointer; color: var(--text-color); }}
        .warning {{ color: red; font-weight: bold; margin-bottom: 10px; }}
        pre {{ background: var(--pre-bg); padding: 10px; border: 1px solid var(--pre-border); white-space: pre-wrap; word-wrap: break-word; font-size: 14px; color: var(--text-color); }}
        textarea {{ width: 100%; height: 400px; font-family: monospace; padding: 10px; box-sizing: border-box; font-size: 14px; background: var(--table-bg); color: var(--text-color); }}
        .btn-container {{ margin-top: 10px; display: flex; gap: 10px; }}
        .btn {{ padding: 8px 16px; cursor: pointer; border: none; background: var(--btn-bg); color: var(--btn-text); border-radius: 4px; }}
        .btn-secondary {{ background: #6c757d; }}
        .severity-high {{ background-color: var(--severity-high-bg); color: var(--severity-high-text); font-weight: bold; }}
        .severity-medium {{ background-color: var(--severity-medium-bg); color: var(--severity-medium-text); }}
        .severity-low {{ background-color: var(--severity-low-bg); color: var(--severity-low-text); }}
        .severity-none {{ color: #999; }}

        .finding-item {{ border-left: 4px solid var(--btn-bg); padding: 10px; margin-bottom: 10px; background: var(--finding-item-bg); }}
        .finding-category {{ font-weight: bold; color: var(--link-color); margin-bottom: 5px; font-size: 18px; }}
        .finding-label {{ font-weight: bold; width: 100px; display: inline-block; color: var(--text-color); opacity: 0.8; }}
        .finding-high {{ border-left-color: #d9534f; }}
        .finding-medium {{ border-left-color: #f0ad4e; }}
        .finding-low {{ border-left-color: #5cb85c; }}

        .finding-badge {{
            display: inline-block;
            padding: 2px 8px;
            font-size: 13px;
            font-weight: bold;
            border-radius: 4px;
            text-transform: uppercase;
            margin-left: 5px;
        }}
        .finding-badge-high {{
            background-color: var(--severity-high-bg);
            color: var(--severity-high-text);
            border: 1px solid var(--severity-high-text);
        }}
        .finding-badge-medium {{
            background-color: var(--severity-medium-bg);
            color: var(--severity-medium-text);
            border: 1px solid var(--severity-medium-text);
        }}
        .finding-badge-low {{
            background-color: var(--severity-low-bg);
            color: var(--severity-low-text);
            border: 1px solid var(--severity-low-text);
        }}
        .finding-badge-unknown {{
            background-color: var(--finding-item-bg);
            color: var(--text-color);
            border: 1px solid var(--table-border);
            opacity: 0.8;
        }}

        .inline-content {{ 
            line-height: 1.5; 
            white-space: pre-wrap;
            font-family: monospace;
            font-size: 15px;
            tab-size: 8;
            -moz-tab-size: 8;
            word-break: break-all;
        }}
        .pre-verification-content {{
            font-family: sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
        }}
        .finding-message, .finding-evidence {{
            font-family: monospace;
            font-size: 15px;
            tab-size: 8;
            -moz-tab-size: 8;
            background: var(--pre-bg);
            padding: 5px;
            margin-top: 5px;
        }}
        .diff-added {{ color: var(--diff-added-text); background-color: var(--diff-added-bg); min-width: fit-content; }}
        .diff-removed {{ color: var(--diff-removed-text); background-color: var(--diff-removed-bg); }}
        .diff-header {{ color: var(--diff-header-text); font-weight: bold; background-color: var(--diff-header-bg); }}
        .diff-meta {{ color: var(--diff-meta-text); }}
        .review-metadata {{ color: var(--diff-header-text); font-weight: bold; }}
        .review-subject {{ color: var(--review-subject-text); font-weight: bold; font-size: 1.1em; background-color: var(--review-subject-bg); padding: 5px; border-radius: 3px; display: block; margin: 5px 0; }}
        .review-link {{ text-decoration: underline; color: var(--link-color); }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    
    <div class="filter-container">
        <label for="authorFilter">Filter by Author:</label>
        <select id="authorFilter" onchange="applyFilter()" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
            <option value="All Authors">All Authors</option>
            {author_options}
        </select>

        <label for="severityFilter" style="margin-left: 20px;">Severity:</label>
        <select id="severityFilter" onchange="applyFilter()" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
            <option value="all">All Issues</option>
            <option value="low">Low+</option>
            <option value="medium">Medium+</option>
            <option value="high">High</option>
        </select>

        <label for="subjectSearch" style="margin-left: 20px;">Search Subject:</label>
        <input type="text" id="subjectSearch" oninput="applyFilter()" placeholder="Search..." style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border); padding: 4px;">

        {branch_switcher_html}
    </div>

    <div id="modelToggleContainer" class="filter-container"></div>

    <div class="controls-container">
        <div id="paginationContainerTop" class="pagination"></div>
        
        <div class="theme-switcher">
            <span>Theme:</span>
            <select class="themeSelect" onchange="setTheme(this.value)" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
                <option value="light">Light</option>
                <option value="dark">Dark</option>
                <option value="psychedelic">Psychedelic</option>
            </select>

            <span style="margin-left: 20px;">Rows:</span>
            <select class="rowsPerPageSelect" onchange="setRowsPerPage(this.value)" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
                <option value="20">20</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="200">200</option>
                <option value="500">500</option>
            </select>
        </div>
    </div>

    <div id="tableContainer"></div>

    <div class="controls-container">
        <div id="paginationContainerBottom" class="pagination"></div>
        
        <div class="theme-switcher">
            <span>Theme:</span>
            <select class="themeSelect" onchange="setTheme(this.value)" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
                <option value="light">Light</option>
                <option value="dark">Dark</option>
                <option value="psychedelic">Psychedelic</option>
            </select>

            <span style="margin-left: 20px;">Rows:</span>
            <select class="rowsPerPageSelect" onchange="setRowsPerPage(this.value)" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
                <option value="20">20</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="200">200</option>
                <option value="500">500</option>
            </select>
        </div>
    </div>

    <!-- Modals -->
    <div id="reviewModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('reviewModal')">&times;</span>
            <h2 id="modalTitle">Review Results</h2>
            <div id="modalBody"></div>
            <div class="btn-container">
                <button class="btn" onclick="saveContent()">Save</button>
                <button id="preVerifyBtn" class="btn btn-secondary" style="display:none">Pre-Verified Issues</button>
                <button class="btn btn-secondary" onclick="closeModal('reviewModal')">Close</button>
            </div>
        </div>
    </div>

    <div id="preVerifyModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('preVerifyModal')">&times;</span>
            <h2>Pre-Verified Issues</h2>
            <p class="warning">Warning: may contain false-positives</p>
            <div id="preVerifyBody"></div>
            <div class="btn-container">
                <button class="btn" onclick="savePreVerifyContent()">Save</button>
                <button class="btn btn-secondary" onclick="closeModal('preVerifyModal')">Close</button>
            </div>
        </div>
    </div>

    <div id="fixPatchModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal('fixPatchModal')">&times;</span>
            <h2>Fix Patch</h2>
            <p class="warning">Warning: Patches can be bogus, use only as a reference</p>
            <div id="fixPatchBody" style="margin-bottom: 10px; border: 1px solid var(--table-border); padding: 10px; background: var(--inline-view-bg); max-height: 500px; overflow-y: auto;"></div>
            <div class="btn-container">
                <button class="btn" onclick="saveFixPatch()">Save</button>
                <button class="btn btn-secondary" onclick="closeModal('fixPatchModal')">Close</button>
            </div>
        </div>
    </div>

    <script>
        let data = [];
        let datasets = [];
        let visibleDatasets = [];
        let rowsPerPage = {rows_per_page};
        let useKernCVS = {use_kerncvs};
        let commitBaseUrl = "";
        let ksBaseUrl = "";
        let currentPage = 1;
        let filteredData = [];
        let activeReview = null;
        let visitedReviews = new Set(JSON.parse(localStorage.getItem('visitedReviews') || '[]'));
        let commitStates = JSON.parse(localStorage.getItem('commitStates') || '{{}}');
        let showReviewTime = {show_review_time};

        function toggleCommitState(commitId, event) {{
            if (event) event.stopPropagation();
            const currentState = commitStates[commitId] || 'unreviewed';
            let newState = 'ok';
            if (currentState === 'unreviewed') newState = 'ok';
            else if (currentState === 'ok') newState = 'bad';
            else if (currentState === 'bad') newState = 'unreviewed';
            
            if (newState === 'unreviewed') {{
                delete commitStates[commitId];
            }} else {{
                commitStates[commitId] = newState;
            }}
            localStorage.setItem('commitStates', JSON.stringify(commitStates));
            
            const icon = newState === 'ok' ? '✅' : (newState === 'bad' ? '❌' : '');
            document.querySelectorAll(`td.state-cell[data-commit-id="${{commitId}}"]`).forEach(el => {{
                el.innerText = icon;
                el.title = newState;
            }});
        }}

        function toggleCommitDiff() {{
            const container = document.getElementById('commitDiffContainer');
            const arrow = document.getElementById('commitDiffArrow');
            if (!container) return;
            if (container.style.display === 'none') {{
                container.style.display = 'block';
                if (arrow) arrow.innerText = '▼';
                const inlineView = document.getElementById('inlineView');
                if (inlineView) {{
                    setTimeout(() => {{
                        inlineView.scrollTo({{
                            top: inlineView.scrollHeight,
                            behavior: 'smooth'
                        }});
                    }}, 50);
                }}
            }} else {{
                container.style.display = 'none';
                if (arrow) arrow.innerText = '▶';
            }}
        }}

        function markVisited(commitId, dsName) {{
            const key = `${{commitId}}-${{dsName}}`;
            if (!visitedReviews.has(key)) {{
                visitedReviews.add(key);
                localStorage.setItem('visitedReviews', JSON.stringify([...visitedReviews]));
                document.querySelectorAll(`td[data-review-id="${{key}}"]`).forEach(el => el.classList.add('visited'));
            }}
        }}

        async function init() {{
            const compressed = "{compressed_json}";
            const binary = atob(compressed);
            const bytes = new Uint8Array(binary.length);
            for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
            
            const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('deflate'));
            const text = await new Response(stream).text();
            data = JSON.parse(text);
            datasets = {datasets_list};
            visibleDatasets = [...datasets];
            filteredData = data;

            const urlParams = new URLSearchParams(window.location.search);

            // Initialize models/datasets visibility from URL or localStorage
            const urlModels = urlParams.get('models') || urlParams.get('datasets');
            if (urlModels) {{
                const selected = urlModels.split(',');
                visibleDatasets = datasets.filter(ds => selected.includes(ds));
            }} else {{
                const savedModels = localStorage.getItem('visibleDatasets');
                if (savedModels) {{
                    try {{
                        const parsed = JSON.parse(savedModels);
                        if (Array.isArray(parsed)) {{
                            visibleDatasets = datasets.filter(ds => parsed.includes(ds));
                        }}
                    }} catch (e) {{
                        // ignore
                    }}
                }}
            }}

            // Initialize review-time visibility from URL or localStorage
            const urlShowReviewTime = urlParams.get('review_time') || urlParams.get('review-time');
            if (urlShowReviewTime !== null) {{
                showReviewTime = (urlShowReviewTime === 'true' || urlShowReviewTime === '1');
            }} else {{
                const savedShowReviewTime = localStorage.getItem('showReviewTime');
                if (savedShowReviewTime !== null) {{
                    showReviewTime = (savedShowReviewTime === 'true');
                }}
            }}

            renderModelToggles();

            commitBaseUrl = useKernCVS ? "https://kerncvs.suse.de/gitweb/?p=kernel.git;a=commit;h=" : "https://github.com/SUSE/kernel/commit/";
            ksBaseUrl = useKernCVS ? "https://kerncvs.suse.de/gitweb/?p=kernel-source.git;a=commit;h=" : "https://github.com/SUSE/kernel-source/commit/";

            // Initialize theme
            let savedTheme = urlParams.get('theme') || localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            setTheme(savedTheme);

            rowsPerPage = parseInt(urlParams.get('rows')) || parseInt(localStorage.getItem('rowsPerPage')) || rowsPerPage;
            document.querySelectorAll('.rowsPerPageSelect').forEach(s => s.value = rowsPerPage);

            const initialSearch = urlParams.get('search') || "";
            if (initialSearch) {{
                document.getElementById('subjectSearch').value = initialSearch;
            }}

            const initialAuthor = urlParams.get('author') || localStorage.getItem('authorFilter');
            if (initialAuthor) {{
                const filter = document.getElementById('authorFilter');
                let option = [...filter.options].find(o => o.value === initialAuthor);
                if (!option) {{
                    const lowerSearch = initialAuthor.toLowerCase();
                    option = [...filter.options].find(o => o.value.toLowerCase().includes(lowerSearch));
                }}
                if (option) filter.value = option.value;
            }}

            const initialSeverity = urlParams.get('severity') || localStorage.getItem('severityFilter');
            if (initialSeverity) {{
                const filter = document.getElementById('severityFilter');
                if ([...filter.options].some(o => o.value === initialSeverity)) {{
                    filter.value = initialSeverity;
                }}
            }}

            // Re-apply theme to ensure all instances are synchronized
            setTheme(document.documentElement.getAttribute('data-theme') || savedTheme);

            applyFilter();
        }}

        function renderModelToggles() {{
            const container = document.getElementById('modelToggleContainer');
            if (!container) return;
            let html = '<label style="margin-right: 10px; font-weight: bold;">Models:</label>';
            datasets.forEach(ds => {{
                const checked = visibleDatasets.includes(ds) ? 'checked' : '';
                html += `<label style="margin-right: 15px; cursor: pointer;">
                            <input type="checkbox" value="${{ds}}" ${{checked}} onchange="toggleModel(this.value, this.checked)" style="vertical-align: middle; margin-right: 4px;">
                            ${{ds}}
                         </label>`;
            }});

            const reviewTimeChecked = showReviewTime ? 'checked' : '';
            html += `<span style="margin-left: 15px; margin-right: 15px; border-left: 1px solid var(--table-border); height: 1.2em; display: inline-block; vertical-align: middle;"></span>`;
            html += `<label style="cursor: pointer; font-weight: bold;">
                        <input type="checkbox" id="reviewTimeToggle" ${{reviewTimeChecked}} onchange="toggleReviewTime(this.checked)" style="vertical-align: middle; margin-right: 4px;">
                        Show Review Time
                     </label>`;

            container.innerHTML = html;
        }}

        function toggleReviewTime(visible) {{
            showReviewTime = visible;
            localStorage.setItem('showReviewTime', showReviewTime);
            renderTable();
        }}

        function toggleModel(ds, isVisible) {{
            if (isVisible) {{
                if (!visibleDatasets.includes(ds)) {{
                    visibleDatasets.push(ds);
                    visibleDatasets.sort((a, b) => datasets.indexOf(a) - datasets.indexOf(b));
                }}
            }} else {{
                visibleDatasets = visibleDatasets.filter(d => d !== ds);
            }}
            localStorage.setItem('visibleDatasets', JSON.stringify(visibleDatasets));
            renderTable();
        }}

        function setTheme(theme) {{
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
            document.querySelectorAll('.themeSelect').forEach(s => s.value = theme);
        }}

        function setRowsPerPage(value) {{
            rowsPerPage = parseInt(value);
            localStorage.setItem('rowsPerPage', value);
            document.querySelectorAll('.rowsPerPageSelect').forEach(s => s.value = value);
            currentPage = 1;
            renderTable();
        }}

        function applyFilter() {{
            const author = document.getElementById('authorFilter').value;
            const severityThreshold = document.getElementById('severityFilter').value;
            const searchText = document.getElementById('subjectSearch').value.toLowerCase();

            localStorage.setItem('authorFilter', author);
            localStorage.setItem('severityFilter', severityThreshold);

            const severityMap = {{ "none": 0, "low": 1, "medium": 2, "high": 3 }};
            const thresholdValue = severityMap[severityThreshold] || 0;

            filteredData = data.filter(item => {{
                const reviews = Object.values(item.reviews);
                
                const matchesAuthor = (author === "All Authors") || 
                    reviews.some(r => r.metadata && r.metadata.author === author);
                
                const matchesSeverity = (severityThreshold === "all") ||
                    reviews.some(r => {{
                        if (!r.metadata) return false;
                        const score = (r.metadata['issue-severity-score'] || "none").toString().toLowerCase();
                        return (severityMap[score] || 0) >= thresholdValue;
                    }});

                const matchesSubject = item.subject.toLowerCase().includes(searchText);
                
                return matchesAuthor && matchesSeverity && matchesSubject;
            }});
            currentPage = 1;
            renderTable();
        }}

        function renderTable() {{
            const start = (currentPage - 1) * rowsPerPage;
            const end = start + rowsPerPage;
            const pageItems = filteredData.slice(start, end);

            let html = '<table><thead><tr>';
            html += '<th rowspan="2" style="width: 50px;">State</th>';
            html += '<th rowspan="2">Subject</th>';
            html += '<th rowspan="2">Commit ID</th>';
            html += '<th rowspan="2">kernel-source</th>';
            const colSpan = showReviewTime ? 3 : 2;
            visibleDatasets.forEach(name => {{
                html += `<th colspan="${{colSpan}}" class="dataset-header">${{name}}</th>`;
            }});
            html += '</tr><tr>';
            visibleDatasets.forEach(() => {{
                if (showReviewTime) {{
                    html += '<th>Issues</th><th>Severity</th><th>Review Time</th>';
                }} else {{
                    html += '<th>Issues</th><th>Severity</th>';
                }}
            }});
            html += '</tr></thead><tbody>';

            pageItems.forEach((item, idx) => {{
                const stateStr = commitStates[item.id] || 'unreviewed';
                let stateIcon = '';
                if (stateStr === 'ok') stateIcon = '✅';
                else if (stateStr === 'bad') stateIcon = '❌';

                html += '<tr>';
                html += `<td class="state-cell" data-commit-id="${{item.id}}" title="${{stateStr}}" style="cursor: pointer; text-align: center; user-select: none;" onclick="toggleCommitState('${{item.id}}', event)">${{stateIcon}}</td>`;
                html += `<td class="subject-cell" title="${{escapeHtml(item.subject)}}">${{item.subject}}</td>`;
                html += `<td><a href="${{commitBaseUrl}}${{item.id}}" target="_blank">${{item.id.substring(0, 12)}}</a></td>`;

                
                // Get kernel-source ID from the first dataset that has it
                let ksId = "";
                for (let ds of datasets) {{
                    if (item.reviews[ds] && item.reviews[ds].metadata) {{
                        ksId = item.reviews[ds].metadata['suse-commit'] || item.reviews[ds].metadata['distro-commit'] || "";
                        break;
                    }}
                }}
                html += `<td>${{ksId ? `<a href="${{ksBaseUrl}}${{ksId}}" target="_blank">${{ksId.substring(0, 12)}}</a>` : ""}}</td>`;

                visibleDatasets.forEach(dsName => {{
                    const review = item.reviews[dsName];
                    if (review && review.metadata) {{
                        const metadata = review.metadata;
                        const hasPre = review.pre_verification ? "*" : "";
                        const preClass = review.pre_verification ? "has-pre-verification" : "";
                        const severity = (metadata['issue-severity-score'] || "none").toString().toLowerCase();
                        const severityClass = `severity-${{severity}}`;
                        const clickAction = `onclick="openReview('${{item.id}}', '${{dsName}}')"`;
                        const reviewKey = `${{item.id}}-${{dsName}}`;
                        const visitedClass = visitedReviews.has(reviewKey) ? " visited" : "";
                        
                        let issuesText = `${{metadata['issues-found']}}${{hasPre}}`;
                        let dsClass = "";
                        if (review.downstream_only) {{
                            issuesText += ` [${{review.downstream_only}}]`;
                            if (metadata['issues-found'] > 0) {{
                                dsClass = "has-downstream";
                            }}
                        }}

                        html += `<td class="issues-cell ${{dsClass}} ${{preClass}}${{visitedClass}}" data-review-id="${{reviewKey}}" ${{clickAction}}>${{issuesText}}</td>`;
                        html += `<td class="${{severityClass}} issues-cell${{visitedClass}}" data-review-id="${{reviewKey}}" ${{clickAction}}>${{metadata['issue-severity-score']}}</td>`;
                        if (showReviewTime) {{
                            html += `<td>${{metadata['review-time-seconds']}}s</td>`;
                        }}
                    }} else {{
                        if (showReviewTime) {{
                            html += '<td></td><td></td><td></td>';
                        }} else {{
                            html += '<td></td><td></td>';
                        }}
                    }}
                }});

                html += '</tr>';
            }});

            html += '</tbody></table>';
            document.getElementById('tableContainer').innerHTML = html;
            renderPagination();
        }}

        function renderPagination() {{
            const totalPages = Math.ceil(filteredData.length / rowsPerPage);
            let html = '';
            if (totalPages > 1) {{
                // Previous button
                html += `<button onclick="goToPage(${{Math.max(1, currentPage - 1)}})" title="Previous Page">&lt;</button>`;

                const delta = 2; // Number of pages to show around current page
                let pages = [];
                for (let i = 1; i <= totalPages; i++) {{
                    if (i === 1 || i === totalPages || (i >= currentPage - delta && i <= currentPage + delta)) {{
                        pages.push(i);
                    }}
                }}

                let lastPage = null;
                for (let p of pages) {{
                    if (lastPage !== null) {{
                        if (p - lastPage === 2) {{
                            const activeClass = (lastPage + 1) === currentPage ? 'active' : '';
                            html += `<button class="${{activeClass}}" onclick="goToPage(${{lastPage + 1}})">${{lastPage + 1}}</button>`;
                        }} else if (p - lastPage > 2) {{
                            html += `<span class="ellipsis" onclick="jumpToPage()" title="Jump to page">...</span>`;
                        }}
                    }}
                    const activeClass = p === currentPage ? 'active' : '';
                    html += `<button class="${{activeClass}}" onclick="goToPage(${{p}})">${{p}}</button>`;
                    lastPage = p;
                }}

                // Next button
                html += `<button onclick="goToPage(${{Math.min(totalPages, currentPage + 1)}})" title="Next Page">&gt;</button>`;
            }}
            const top = document.getElementById('paginationContainerTop');
            const bottom = document.getElementById('paginationContainerBottom');
            if (top) top.innerHTML = html;
            if (bottom) bottom.innerHTML = html;
        }}

        function goToPage(p) {{
            currentPage = p;
            renderTable();
        }}

        function jumpToPage() {{
            const totalPages = Math.ceil(filteredData.length / rowsPerPage);
            const p = prompt(`Enter page number (1-${{totalPages}}):`, currentPage);
            if (p !== null) {{
                const pageNum = parseInt(p);
                if (!isNaN(pageNum) && pageNum >= 1 && pageNum <= totalPages) {{
                    goToPage(pageNum);
                }} else {{
                    alert("Invalid page number.");
                }}
            }}
        }}

        function formatMarkdown(text, isInline) {{
            if (!text) return "";
            
            // Handle code blocks first
            let processedText = text;
            const codeBlocks = [];
            processedText = processedText.replace(/```(\\w+)?([\\s\\S]*?)```/g, (match, lang, code) => {{
                const id = `__CODE_BLOCK_${{codeBlocks.length}}__`;
                codeBlocks.push(`<div style="background: var(--code-block-bg); border: 1px solid var(--code-block-border); border-left: 4px solid var(--btn-bg); padding: 12px; border-radius: 4px; margin: 10px 0; overflow-x: auto; font-family: monospace; color: var(--text-color);">${{escapeHtml(code.trim())}}</div>`);
                return id;
            }});

            const lines = processedText.split('\\n');
            let authorFound = false;
            let subjectFound = false;

            let formattedLines = lines.map((line, idx) => {{
                if (line.startsWith('__CODE_BLOCK_') && line.endsWith('__')) {{
                    const index = parseInt(line.replace('__CODE_BLOCK_', '').replace('__', ''));
                    return codeBlocks[index];
                }}

                let cleanLine = line;
                let prefixHtml = "";
                if (line.startsWith('> ')) {{
                    prefixHtml = '<span style="color: #888;">&gt; </span>';
                    cleanLine = line.substring(2);
                }}

                // Handle inline code `...`
                let content = escapeHtml(cleanLine)
                    .replace(/`([^`]+)`/g, '<code style="background: var(--table-bg); border: 1px solid var(--table-border); padding: 1px 4px; border-radius: 3px; font-family: monospace; color: var(--diff-removed-text);">$1</code>')
                    .replace(/\\*\\*([^\\*]+)\\*\\*/g, '<strong>$1</strong>')
                    .replace(/\\*([^\\*]+)\\*/g, '<em>$1</em>');
                
                let className = "";
                if (cleanLine.startsWith('+++') || cleanLine.startsWith('---')) className = "diff-meta";
                else if (cleanLine.startsWith('+')) className = "diff-added";
                else if (cleanLine.startsWith('-')) className = "diff-removed";
                else if (cleanLine.startsWith('@@')) className = "diff-header";
                else if (cleanLine.startsWith('diff --git') || cleanLine.startsWith('index ')) className = "diff-meta";
                else if (cleanLine.startsWith('#')) className = "diff-meta";

                if (isInline) {{
                    const trimmed = cleanLine.trim();
                    if (trimmed.startsWith('commit ')) {{
                        const id = trimmed.substring(7).trim();
                        if (/^[0-9a-f]{{7,}}$/.test(id)) {{
                             return `<span class="review-metadata">commit <a href="${{commitBaseUrl}}${{id}}" target="_blank" class="review-link">${{id}}</a></span>\\n`;
                        }}
                    }}
                    if (trimmed.startsWith('Author: ')) {{
                        authorFound = true;
                        return `<span class="review-metadata">${{content}}</span>\\n`;
                    }}
                    if (trimmed.startsWith('suse-commit: ')) {{
                        const id = trimmed.substring(13).trim();
                        return `<span class="review-metadata">suse-commit: <a href="${{ksBaseUrl}}${{id}}" target="_blank" class="review-link">${{id}}</a></span>\\n`;
                    }}
                    if (trimmed.startsWith('distro-commit: ')) {{
                        const id = trimmed.substring(15).trim();
                        return `<span class="review-metadata">distro-commit: <a href="${{ksBaseUrl}}${{id}}" target="_blank" class="review-link">${{id}}</a></span>\\n`;
                    }}
                    if (trimmed.startsWith('Git-commit: ')) {{
                        const id = trimmed.substring(12).trim();
                        return `<span class="review-metadata">Git-commit: <a href="https://github.com/torvalds/linux/commit/${{id}}" target="_blank" class="review-link">${{id}}</a></span>\\n`;
                    }}
                    if (trimmed.startsWith('Verified-against: ')) {{
                        const id = trimmed.substring(18).trim();
                        return `<span class="review-metadata">Verified-against: <a href="https://github.com/torvalds/linux/commit/${{id}}" target="_blank" class="review-link">${{id}}</a></span>\\n`;
                    }}
                    
                    const metaPrefixes = [
                        'Upstream-subject: ',
                        'Findings-in-upstream: ',
                        'Findings-downstream-only: ',
                        'Review-time: ',
                        'Review-model: ',
                        'Input-tokens: ',
                        'Output-tokens: ',
                        'Total-tokens: '
                    ];
                    if (metaPrefixes.some(p => trimmed.startsWith(p))) {{
                        return `<span class="review-metadata">${{content}}</span>\\n`;
                    }}

                    // Subject detection: after Author: and between blank lines
                    if (authorFound && !subjectFound && trimmed !== "") {{
                        const prevLine = idx > 0 ? lines[idx-1].trim() : "";
                        const nextLine = idx < lines.length - 1 ? lines[idx+1].trim() : "";
                        if (prevLine === "" && (nextLine === "" || nextLine.startsWith('suse-commit:') || nextLine.startsWith('distro-commit:'))) {{
                            subjectFound = true;
                            return `<span class="review-subject">${{content}}</span>\\n`;
                        }}
                    }}
                }}
                
                if (className) {{
                    return `<span class="${{className}}">${{prefixHtml}}${{content}}</span>\\n`;
                }}
                
                return `${{prefixHtml}}${{content}}\\n`;
            }});

            return `<div class="inline-content">` + formattedLines.join('') + '</div>';
        }}

        function formatInline(text) {{
            return formatMarkdown(text, true);
        }}

        function renderPreVerification(jsonStr) {{
            try {{
                const data = JSON.parse(jsonStr);
                let html = '<div class="pre-verification-content">';
                
                if (data.findings && Array.isArray(data.findings)) {{
                    data.findings.forEach(f => {{
                        const sevClass = f.severity ? `finding-${{f.severity.toString().toLowerCase()}}` : "";
                        html += `<div class="finding-item ${{sevClass}}">`;
                        html += `<div class="finding-category">${{escapeHtml(f.category || "General")}} - ${{escapeHtml(f.type || "Issue")}}</div>`;
                        const sev = (f.severity || "N/A").toString().toLowerCase();
                        const sevBadgeClass = ["high", "medium", "low"].includes(sev) ? `finding-badge-${{sev}}` : "finding-badge-unknown";
                        html += `<div><span class="finding-label">Severity:</span> <span class="finding-badge ${{sevBadgeClass}}">${{escapeHtml(f.severity || "N/A")}}</span></div>`;
                        html += `<div><span class="finding-label">Status:</span> ${{escapeHtml(f.upstream_status || "N/A")}}</div>`;
                        html += `<div style="margin-top:5px;"><strong>Message:</strong></div>`;
                        html += `<div class="finding-message">${{formatMarkdown(f.message || "", false)}}</div>`;
                        if (f.evidence) {{
                            html += `<div style="margin-top:5px;"><strong>Evidence:</strong></div>`;
                            html += `<div class="finding-evidence">${{formatMarkdown(f.evidence, false)}}</div>`;
                        }}
                        html += '</div>';
                    }});
                }} else {{
                    html += `<pre>${{escapeHtml(jsonStr)}}</pre>`;
                }}
                html += '</div>';
                return html;
            }} catch (e) {{
                return `<pre>${{escapeHtml(jsonStr)}}</pre>`;
            }}
        }}

        function escapeHtml(text) {{
            if (!text) return "";
            const map = {{ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }};
            return text.toString().replace(/[&<>"']/g, function(m) {{ return map[m]; }});
        }}

        function renderInlineJson(jsonStr, diffText) {{
            try {{
                const data = JSON.parse(jsonStr);
                let html = '<div class="inline-json-content">';
                
                // Metadata block
                html += '<div style="margin-bottom: 15px; padding-bottom: 10px; border-bottom: 1px solid var(--table-border); line-height: 1.5;">';
                if (data.commit) {{
                    html += `<div><span class="review-metadata">commit <a href="${{commitBaseUrl}}${{data.commit}}" target="_blank" class="review-link">${{escapeHtml(data.commit)}}</a></span></div>`;
                }}
                if (data.author) {{
                    html += `<div><span class="review-metadata">Author: ${{escapeHtml(data.author)}}</span></div>`;
                }}
                if (data.subject) {{
                    html += `<div style="margin-top: 5px;"><span class="review-subject">${{escapeHtml(data.subject)}}</span></div>`;
                }}
                if (data['distro-commit']) {{
                    html += `<div><span class="review-metadata">distro-commit: <a href="${{ksBaseUrl}}${{data['distro-commit']}}" target="_blank" class="review-link">${{escapeHtml(data['distro-commit'])}}</a></span></div>`;
                }}
                if (data['upstream-commit']) {{
                    html += `<div><span class="review-metadata">Git-commit: <a href="https://github.com/torvalds/linux/commit/${{data['upstream-commit']}}" target="_blank" class="review-link">${{escapeHtml(data['upstream-commit'])}}</a></span></div>`;
                }} else if (data['upstream_commit']) {{
                    html += `<div><span class="review-metadata">Git-commit: <a href="https://github.com/torvalds/linux/commit/${{data['upstream_commit']}}" target="_blank" class="review-link">${{escapeHtml(data['upstream_commit'])}}</a></span></div>`;
                }}
                
                // Backport info
                if (data.backport) {{
                    const bp = data.backport;
                    html += '<div style="margin-top: 10px; padding: 8px; background: var(--table-bg); border: 1px solid var(--table-border); border-radius: 4px;">';
                    html += `<strong>Backport Info:</strong><br>`;
                    if (bp.upstream) {{
                        html += `Upstream: <a href="https://github.com/torvalds/linux/commit/${{bp.upstream}}" target="_blank" class="review-link">${{escapeHtml(bp.upstream)}}</a><br>`;
                    }}
                    if (bp.status) {{
                        html += `Status: ${{escapeHtml(bp.status)}}<br>`;
                    }}
                    if (bp.summary) {{
                        html += `Summary: ${{escapeHtml(bp.summary)}}`;
                    }}
                    html += '</div>';
                }}
                
                // Summary block
                if (data.summary) {{
                    html += `<div style="margin-top: 10px; font-style: italic;">${{formatMarkdown(data.summary, false)}}</div>`;
                }}
                
                // Review system stats
                html += '<div style="margin-top: 10px; font-size: 0.9em; opacity: 0.7;">';
                if (data['review-time-seconds']) {{
                    html += `Review-time: ${{escapeHtml(data['review-time-seconds'])}} seconds<br>`;
                }}
                if (data.model) {{
                    html += `Review-model: ${{escapeHtml(data.model)}}<br>`;
                }}
                if (data['input-tokens']) {{
                    html += `Input-tokens: ${{escapeHtml(data['input-tokens'])}}<br>`;
                }}
                if (data['output-tokens']) {{
                    html += `Output-tokens: ${{escapeHtml(data['output-tokens'])}}<br>`;
                }}
                if (data['total-tokens']) {{
                    html += `Total-tokens: ${{escapeHtml(data['total-tokens'])}}<br>`;
                }}
                html += '</div>';
                html += '</div>'; // End metadata block

                // Diff block
                if (diffText) {{
                    html += '<div style="margin-top: 15px; margin-bottom: 5px;"><strong>Commit Diff:</strong></div>';
                    html += `<div style="max-height: 400px; overflow-y: auto; border: 1px solid var(--table-border); padding: 10px; background: var(--code-block-bg); border-radius: 4px;">`;
                    html += formatInline(diffText);
                    html += '</div>';
                }}

                // Findings
                if (data.findings && Array.isArray(data.findings) && data.findings.length > 0) {{
                    html += '<div style="margin-top: 15px;"><strong>Findings:</strong></div>';
                    data.findings.forEach((f, idx) => {{
                        const sevClass = f.severity ? `finding-${{f.severity.toString().toLowerCase()}}` : "";
                        html += `<div class="finding-item ${{sevClass}}" style="margin-top: 10px;">`;
                        html += `<div class="finding-category">[Finding ${{idx + 1}}] - ${{escapeHtml(f.category || "General")}} - ${{escapeHtml(f.type || "Issue")}}</div>`;
                        const sev = (f.severity || "N/A").toString().toLowerCase();
                        const conf = (f.confidence || "N/A").toString().toLowerCase();
                        const sevBadgeClass = ["high", "medium", "low"].includes(sev) ? `finding-badge-${{sev}}` : "finding-badge-unknown";
                        const confBadgeClass = ["high", "medium", "low"].includes(conf) ? `finding-badge-${{conf}}` : "finding-badge-unknown";
                        html += `<div><span class="finding-label">Severity:</span> <span class="finding-badge ${{sevBadgeClass}}">${{escapeHtml(f.severity || "N/A")}}</span></div>`;
                        html += `<div><span class="finding-label">Confidence:</span> <span class="finding-badge ${{confBadgeClass}}">${{escapeHtml(f.confidence || "N/A")}}</span></div>`;
                        html += `<div style="margin-top:5px;"><strong>Message:</strong></div>`;
                        html += `<div class="finding-message">${{formatMarkdown(f.message || "", false)}}</div>`;
                        if (f.evidence) {{
                            html += `<div style="margin-top:5px;"><strong>Evidence:</strong></div>`;
                            html += `<div style="background: var(--code-block-bg); border: 1px solid var(--code-block-border); border-left: 4px solid var(--btn-bg); padding: 12px; border-radius: 4px; margin: 10px 0; overflow-x: auto; font-family: monospace; color: var(--text-color); white-space: pre-wrap; word-wrap: break-word; tab-size: 8; -moz-tab-size: 8;">${{escapeHtml(f.evidence)}}</div>`;
                        }}
                        html += '</div>';
                    }});
                }}
                
                html += '</div>';
                return html;
            }} catch (e) {{
                return `<pre>${{escapeHtml(jsonStr)}}</pre>`;
            }}
        }}

        function openReview(commitId, dsName) {{
            markVisited(commitId, dsName);
            const item = data.find(i => i.id === commitId);
            const review = item.reviews[dsName];
            activeReview = {{ commitId, dsName, item, review }};

            document.getElementById('modalTitle').innerText = `${{dsName}} Review - ${{item.id.substring(0, 12)}}`;
            const body = document.getElementById('modalBody');
            let contentHtml = "";
            if (review.inline) {{
                if (review.inline_is_json) {{
                    contentHtml = renderInlineJson(review.inline, null);
                }} else {{
                    contentHtml = formatInline(review.inline);
                }}
            }} else {{
                contentHtml = "No inline review content.";
            }}

            let diffHtml = "";
            if (review.diff) {{
                diffHtml = `
                    <div style="margin-top: 15px; margin-bottom: 5px;">
                        <strong onclick="toggleCommitDiff()" style="cursor: pointer; color: var(--link-color); user-select: none;">
                            <span id="commitDiffArrow">▶</span> Commit Diff
                        </strong>
                    </div>
                    <div id="commitDiffContainer" style="display: none; max-height: 400px; overflow-y: auto; border: 1px solid var(--table-border); padding: 10px; background: var(--code-block-bg); border-radius: 4px;">
                        ${{formatInline(review.diff)}}
                    </div>
                `;
            }}

            body.innerHTML = `
                <div style="margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid var(--table-border); padding-bottom: 10px;">
                    Subject: ${{escapeHtml(item.subject)}}
                </div>
                <div id="inlineView" style="margin-bottom: 10px; border: 1px solid var(--table-border); padding: 10px; background: var(--inline-view-bg); max-height: 500px; overflow-y: auto;">
                    ${{contentHtml}}
                    ${{diffHtml}}
                </div>
            `;

            const preBtn = document.getElementById('preVerifyBtn');
            if (review.pre_verification) {{
                preBtn.style.display = 'block';
                preBtn.onclick = () => openPreVerify(commitId, dsName);
            }} else {{
                preBtn.style.display = 'none';
            }}

            const fixBtn = document.getElementById('fixPatchBtn');
            if (review.fix_patches && review.metadata && review.metadata['issues-found'] > 0) {{
                if (!fixBtn) {{
                    const btnContainer = document.querySelector('#reviewModal .btn-container');
                    const newBtn = document.createElement('button');
                    newBtn.id = 'fixPatchBtn';
                    newBtn.className = 'btn btn-secondary';
                    newBtn.innerText = 'Fix Patch';
                    newBtn.onclick = () => openFixPatch(commitId, dsName);
                    btnContainer.insertBefore(newBtn, preBtn);
                }} else {{
                    fixBtn.style.display = 'block';
                    fixBtn.className = 'btn btn-secondary';
                    fixBtn.onclick = () => openFixPatch(commitId, dsName);
                }}
            }} else if (fixBtn) {{
                fixBtn.style.display = 'none';
            }}

            document.getElementById('reviewModal').style.display = 'block';
        }}


        function openPreVerify(commitId, dsName) {{
            const item = data.find(i => i.id === commitId);
            const review = item.reviews[dsName];
            const body = document.getElementById('preVerifyBody');
            body.innerHTML = renderPreVerification(review.pre_verification);
            document.getElementById('preVerifyModal').style.display = 'block';
        }}

        function openFixPatch(commitId, dsName) {{
            const item = data.find(i => i.id === commitId);
            const review = item.reviews[dsName];
            const body = document.getElementById('fixPatchBody');
            body.innerHTML = formatMarkdown(review.fix_patches, false);
            document.getElementById('fixPatchModal').style.display = 'block';
        }}

        function closeModal(id) {{
            document.getElementById(id).style.display = 'none';
        }}

        function saveContent() {{
            if (!activeReview || !activeReview.review.inline) return;
            const content = activeReview.review.inline;
            const isJson = activeReview.review.inline_is_json;
            const mimeType = isJson ? 'application/json' : 'text/plain';
            const fileName = isJson ? 'review-inline.json' : 'review-inline.txt';
            const blob = new Blob([content], {{ type: mimeType }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = fileName;
            a.click();
            URL.revokeObjectURL(url);
        }}

        function savePreVerifyContent() {{
            if (!activeReview || !activeReview.review.pre_verification) return;
            const content = activeReview.review.pre_verification;
            const blob = new Blob([content], {{ type: 'application/json' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'review-pre-verification.json';
            a.click();
            URL.revokeObjectURL(url);
        }}

        function saveFixPatch() {{
            if (!activeReview || !activeReview.review.fix_patches) return;
            const content = activeReview.review.fix_patches;
            const blob = new Blob([content], {{ type: 'text/plain' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'review-fix-patches.diff';
            a.click();
            URL.revokeObjectURL(url);
        }}

        window.onclick = function(event) {{
            if (event.target.className === 'modal') {{
                event.target.style.display = "none";
            }}
        }}

        window.onkeydown = function(event) {{
            if (event.key === "Escape") {{
                closeModal('reviewModal');
                closeModal('preVerifyModal');
                closeModal('fixPatchModal');
            }}
        }}

        init();
    </script>
</body>
</html>
"""

    author_options = "".join([f'<option value="{html.escape(a)}">{html.escape(a)}</option>' for a in sorted(authors)])
    
    branch_switcher_html = ""
    if branch_links:
        options_html = '<option value="" disabled selected style="display:none;">Switch Branch...</option>'
        for name, url in branch_links.items():
            options_html += f'<option value="{html.escape(url)}">{html.escape(name)}</option>'
        branch_switcher_html = f"""
        <span class="branch-switcher" style="margin-left: 20px;">
            <label for="branchSelect">Branch:</label>
            <select id="branchSelect" onchange="if(this.value) window.location.href=this.value;" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border); padding: 4px;">
                {options_html}
            </select>
        </span>
        """

    datasets_list = list(dataset_sources.keys())
    
    json_data = json.dumps(processed_data, separators=(',', ':'))
    compressed_data = base64.b64encode(zlib.compress(json_data.encode('utf-8'))).decode('ascii')

    full_html = html_template.format(
        title=html.escape(args.title),
        author_options=author_options,
        branch_switcher_html=branch_switcher_html,
        compressed_json=compressed_data,
        datasets_list=json.dumps(datasets_list),
        rows_per_page=args.rows,
        use_kerncvs="true" if args.kerncvs else "false",
        show_review_time="true" if args.show_review_time else "false"
    )

    with open(args.output, "w") as f:
        f.write(full_html)
    
    print(f"Report generated: {args.output}")

if __name__ == "__main__":
    main()
