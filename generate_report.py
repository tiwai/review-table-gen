#!/usr/bin/env python3
#
# Copyright (c) 2025 Takashi Iwai
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
import html
import json
import os
import sys

def resolve_full_id(dataset_dir, commit_id):
    """If commit_id is short, find the full 40-char ID in the dataset."""
    if len(commit_id) == 40:
        return commit_id
    
    prefix = commit_id[:2]
    prefix_dir = os.path.join(dataset_dir, prefix)
    if not os.path.isdir(prefix_dir):
        return None
    
    matches = [d for d in os.listdir(prefix_dir) if d.startswith(commit_id)]
    if len(matches) == 1:
        return matches[0]
    return None

def get_review_data(dataset_dir, full_id):
    """Retrieve all review files for a given commit in a dataset."""
    commit_dir = os.path.join(dataset_dir, full_id[:2], full_id)
    if not os.path.isdir(commit_dir):
        return None
    
    data = {}
    metadata_path = os.path.join(commit_dir, "review-metadata.json")
    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            data["metadata"] = json.load(f)
    
    inline_path = os.path.join(commit_dir, "review-inline.txt")
    if os.path.exists(inline_path):
        with open(inline_path, "r") as f:
            data["inline"] = f.read()
            
    pre_verification_path = os.path.join(commit_dir, "review-pre-verification.json")
    if os.path.exists(pre_verification_path):
        with open(pre_verification_path, "r") as f:
            data["pre_verification"] = f.read() # Read as raw string for display/save
            
    return data

def main():
    parser = argparse.ArgumentParser(description="Generate kernel review report.")
    parser.add_argument("--list", required=True, help="Commit list file")
    parser.add_argument("--dataset", action="append", nargs=2, metavar=("NAME", "DIR"), help="Dataset name and directory")
    parser.add_argument("--branch", required=True, help="Branch name")
    parser.add_argument("--rows", type=int, default=50, help="Max rows per page")
    parser.add_argument("--kerncvs", action="store_true", help="Use kerncvs URLs instead of GitHub")
    parser.add_argument("--output", default="report.html", help="Output HTML file")
    
    args = parser.parse_args()
    
    if not args.dataset:
        print("Error: At least one dataset must be provided.")
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
    
    for commit in commits:
        commit_reviews = {}
        has_any_review = False
        commit_full_id = None
        
        for ds_name, ds_dir in args.dataset:
            # Try to resolve full ID if not already done
            if not commit_full_id:
                commit_full_id = resolve_full_id(ds_dir, commit["id"])
            
            if commit_full_id:
                data = get_review_data(ds_dir, commit_full_id)
                if data:
                    commit_reviews[ds_name] = data
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
    <title>Potential Regressions Found in {branch} Tree</title>
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
        }}

        body {{ font-family: sans-serif; margin: 20px; background-color: var(--bg-color); color: var(--text-color); }}
        h1 {{ color: var(--text-color); }}
        table {{ border-collapse: collapse; width: 100%; background: var(--table-bg); margin-bottom: 20px; }}
        th, td {{ border: 1px solid var(--table-border); padding: 8px; text-align: left; }}
        th {{ background-color: var(--header-bg); }}
        .dataset-header {{ background-color: var(--dataset-header-bg); text-align: center; font-weight: bold; }}
        .issues-cell {{ cursor: pointer; color: var(--link-color); text-decoration: underline; }}
        a {{ color: var(--link-color); }}
        .pagination {{ margin: 20px 0; display: flex; gap: 5px; }}
        .pagination button {{ padding: 5px 10px; cursor: pointer; border: 1px solid var(--table-border); background: var(--table-bg); color: var(--text-color); }}
        .pagination button.active {{ background-color: var(--btn-bg); color: var(--btn-text); border-color: var(--btn-bg); }}
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

        .theme-switcher {{
            margin-top: 50px;
            padding: 20px;
            border-top: 1px solid var(--table-border);
            display: flex;
            gap: 20px;
            align-items: center;
        }}
    </style>
</head>
<body>
    <h1>Potential Regressions Found in {branch} Tree</h1>
    
    <div class="filter-container">
        <label for="authorFilter">Filter by Author:</label>
        <select id="authorFilter" onchange="applyFilter()" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
            <option value="All Authors">All Authors</option>
            {author_options}
        </select>
    </div>

    <div id="paginationContainer" class="pagination"></div>
    <div id="tableContainer"></div>

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

    <div class="theme-switcher">
        <span>Theme:</span>
        <label>
            <input type="radio" name="theme" value="light" checked onclick="setTheme('light')"> Light
        </label>
        <label>
            <input type="radio" name="theme" value="dark" onclick="setTheme('dark')"> Dark
        </label>

        <span style="margin-left: 20px;">Rows per page:</span>
        <select id="rowsPerPageSelect" onchange="setRowsPerPage(this.value)" style="background: var(--table-bg); color: var(--text-color); border: 1px solid var(--table-border);">
            <option value="20">20</option>
            <option value="50">50</option>
            <option value="100">100</option>
            <option value="200">200</option>
            <option value="500">500</option>
        </select>
    </div>

    <script>
        function setTheme(theme) {{
            document.documentElement.setAttribute('data-theme', theme);
            localStorage.setItem('theme', theme);
        }}

        // Initialize theme
        const savedTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        setTheme(savedTheme);
        document.querySelector(`input[name="theme"][value="${{savedTheme}}"]`).checked = true;

        const data = {json_data};
        const datasets = {datasets_list};
        let rowsPerPage = {rows_per_page};
        const useKernCVS = {use_kerncvs};

        // Initialize rows per page select
        document.getElementById('rowsPerPageSelect').value = rowsPerPage;

        function setRowsPerPage(value) {{
            rowsPerPage = parseInt(value);
            currentPage = 1;
            renderTable();
        }}
        const commitBaseUrl = useKernCVS ? "https://kerncvs.suse.de/gitweb/?p=kernel.git;a=commit;h=" : "https://github.com/SUSE/kernel/commit/";
        const ksBaseUrl = useKernCVS ? "https://kerncvs.suse.de/gitweb/?p=kernel-source.git;a=commit;h=" : "https://github.com/SUSE/kernel-source/commit/";

        let currentPage = 1;
        let filteredData = data;
        let activeReview = null;

        function applyFilter() {{
            const author = document.getElementById('authorFilter').value;
            if (author === "All Authors") {{
                filteredData = data;
            }} else {{
                filteredData = data.filter(item => {{
                    return Object.values(item.reviews).some(r => r.metadata && r.metadata.author === author);
                }});
            }}
            currentPage = 1;
            renderTable();
        }}

        function renderTable() {{
            const start = (currentPage - 1) * rowsPerPage;
            const end = start + rowsPerPage;
            const pageItems = filteredData.slice(start, end);

            let html = '<table><thead><tr>';
            html += '<th rowspan="2">Subject</th>';
            html += '<th rowspan="2">Commit ID</th>';
            html += '<th rowspan="2">kernel-source</th>';
            datasets.forEach(name => {{
                html += `<th colspan="3" class="dataset-header">${{name}}</th>`;
            }});
            html += '</tr><tr>';
            datasets.forEach(() => {{
                html += '<th>Issues</th><th>Severity</th><th>Review Time</th>';
            }});
            html += '</tr></thead><tbody>';

            pageItems.forEach((item, idx) => {{
                html += '<tr>';
                html += `<td class="subject-cell" title="${{escapeHtml(item.subject)}}">${{item.subject}}</td>`;
                html += `<td><a href="${{commitBaseUrl}}${{item.id}}" target="_blank">${{item.id.substring(0, 12)}}</a></td>`;

                
                // Get kernel-source ID from the first dataset that has it
                let ksId = "";
                for (let ds of datasets) {{
                    if (item.reviews[ds] && item.reviews[ds].metadata) {{
                        ksId = item.reviews[ds].metadata['suse-commit'] || "";
                        break;
                    }}
                }}
                html += `<td>${{ksId ? `<a href="${{ksBaseUrl}}${{ksId}}" target="_blank">${{ksId.substring(0, 12)}}</a>` : ""}}</td>`;

                datasets.forEach(dsName => {{
                    const review = item.reviews[dsName];
                    if (review && review.metadata) {{
                        const metadata = review.metadata;
                        const hasPre = review.pre_verification ? "*" : "";
                        const severity = (metadata['issue-severity-score'] || "none").toLowerCase();
                        const severityClass = `severity-${{severity}}`;
                        const clickAction = `onclick="openReview('${{item.id}}', '${{dsName}}')"`;
                        html += `<td class="issues-cell" ${{clickAction}}>${{metadata['issues-found']}}${{hasPre}}</td>`;
                        html += `<td class="${{severityClass}} issues-cell" ${{clickAction}}>${{metadata['issue-severity-score']}}</td>`;
                        html += `<td>${{metadata['review-time-seconds']}}s</td>`;
                    }} else {{
                        html += '<td></td><td></td><td></td>';
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
                html += `<button onclick="goToPage(1)">&lt;&lt;</button>`;
                for (let i = 1; i <= totalPages; i++) {{
                    const activeClass = i === currentPage ? 'active' : '';
                    html += `<button class="${{activeClass}}" onclick="goToPage(${{i}})">${{i}}</button>`;
                }}
                html += `<button onclick="goToPage(${{totalPages}})">&gt;&gt;</button>`;
            }}
            document.getElementById('paginationContainer').innerHTML = html;
        }}

        function goToPage(p) {{
            currentPage = p;
            renderTable();
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
                        'Review-model: '
                    ];
                    if (metaPrefixes.some(p => trimmed.startsWith(p))) {{
                        return `<span class="review-metadata">${{content}}</span>\\n`;
                    }}

                    // Subject detection: after Author: and between blank lines
                    if (authorFound && !subjectFound && trimmed !== "") {{
                        const prevLine = idx > 0 ? lines[idx-1].trim() : "";
                        const nextLine = idx < lines.length - 1 ? lines[idx+1].trim() : "";
                        if (prevLine === "" && (nextLine === "" || nextLine.startsWith('suse-commit:'))) {{
                            subjectFound = true;
                            return `<span class="review-subject">${{content}}</span>\\n`;
                        }}
                    }}

                    let className = "";
                    if (cleanLine.startsWith('+++') || cleanLine.startsWith('---')) className = "diff-meta";
                    else if (cleanLine.startsWith('+')) className = "diff-added";
                    else if (cleanLine.startsWith('-')) className = "diff-removed";
                    else if (cleanLine.startsWith('@@')) className = "diff-header";
                    else if (cleanLine.startsWith('diff --git') || cleanLine.startsWith('index ')) className = "diff-meta";
                    
                    if (className) {{
                        return `<span class="${{className}}">${{prefixHtml}}${{content}}</span>\\n`;
                    }}
                }}
                
                return `${{prefixHtml}}${{content}}\\n`;
            }});

            const containerClass = isInline ? "inline-content" : "";
            return `<div class="${{containerClass}}">` + formattedLines.join('') + '</div>';
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
                        const sevClass = f.severity ? `finding-${{f.severity.toLowerCase()}}` : "";
                        html += `<div class="finding-item ${{sevClass}}">`;
                        html += `<div class="finding-category">${{escapeHtml(f.category || "General")}} - ${{escapeHtml(f.type || "Issue")}}</div>`;
                        html += `<div><span class="finding-label">Severity:</span> ${{escapeHtml(f.severity || "N/A")}}</div>`;
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

        function openReview(commitId, dsName) {{
            const item = data.find(i => i.id === commitId);
            const review = item.reviews[dsName];
            activeReview = {{ commitId, dsName, item, review }};

            document.getElementById('modalTitle').innerText = `${{dsName}} Review - ${{item.id.substring(0, 12)}}`;
            const body = document.getElementById('modalBody');
            body.innerHTML = `
                <div style="margin-bottom: 10px; font-weight: bold; border-bottom: 1px solid var(--table-border); padding-bottom: 10px;">
                    Subject: ${{escapeHtml(item.subject)}}
                </div>
                <div id="inlineView" style="margin-bottom: 10px; border: 1px solid var(--table-border); padding: 10px; background: var(--inline-view-bg); max-height: 500px; overflow-y: auto;">
                    ${{formatInline(review.inline || "No inline review content.")}}
                </div>
            `;

            const preBtn = document.getElementById('preVerifyBtn');
            if (review.pre_verification) {{
                preBtn.style.display = 'block';
                preBtn.onclick = () => openPreVerify(commitId, dsName);
            }} else {{
                preBtn.style.display = 'none';
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

        function closeModal(id) {{
            document.getElementById(id).style.display = 'none';
        }}

        function saveContent() {{
            if (!activeReview || !activeReview.review.inline) return;
            const content = activeReview.review.inline;
            const blob = new Blob([content], {{ type: 'text/plain' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'review-inline.txt';
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

        window.onclick = function(event) {{
            if (event.target.className === 'modal') {{
                event.target.style.display = "none";
            }}
        }}

        window.onkeydown = function(event) {{
            if (event.key === "Escape") {{
                closeModal('reviewModal');
                closeModal('preVerifyModal');
            }}
        }}

        renderTable();
    </script>
</body>
</html>
"""

    author_options = "".join([f'<option value="{html.escape(a)}">{html.escape(a)}</option>' for a in sorted(authors)])
    
    datasets_list = [d[0] for d in args.dataset]
    
    full_html = html_template.format(
        branch=html.escape(args.branch),
        author_options=author_options,
        json_data=json.dumps(processed_data),
        datasets_list=json.dumps(datasets_list),
        rows_per_page=args.rows,
        use_kerncvs="true" if args.kerncvs else "false"
    )

    with open(args.output, "w") as f:
        f.write(full_html)
    
    print(f"Report generated: {args.output}")

if __name__ == "__main__":
    main()
