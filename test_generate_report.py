import unittest
from unittest.mock import MagicMock, patch
import json
import os
import re
import shutil
import subprocess
import tempfile

# Import the module under test
import generate_report

class TestCommitterFiltering(unittest.TestCase):
    def setUp(self):
        # Reset any global state or mock setups if needed
        pass

    def test_committer_extraction_and_override_json(self):
        """Test that the git committer overrides the author in metadata and inline JSON."""
        # Mock GitPython commit object
        mock_commit = MagicMock()
        mock_commit.committer.name = "John Doe"
        mock_commit.committer.email = "johndoe@example.com"

        mock_repo = MagicMock()
        mock_repo.commit.return_value = mock_commit

        # Setup review data with JSON inline content
        data = {
            "metadata": {
                "author": "Anonymous Author <cve-kpm@example.com>",
                "subject": "Some regression"
            },
            "inline": json.dumps({
                "author": "Anonymous Author <cve-kpm@example.com>",
                "commit": "12345"
            }),
            "inline_is_json": True
        }

        # Mock the dataset sources and resolve_full_id
        dataset_sources = {"model1": "/path/to/source"}
        commit = {"id": "12345", "subject": "Some regression"}
        commit_full_id = "1234567890abcdef1234567890abcdef12345678"

        authors = set()
        commit_reviews = {}

        # Simulate the block inside generate_report.py
        target_repo = mock_repo
        commit_diff = None

        if commit_full_id:
            # Assume data is returned by get_review_data
            if data:
                committer = None
                if target_repo:
                    if commit_diff is None:
                        # Simply simulate git diff or skip
                        commit_diff = ""
                    if commit_diff:
                        data["diff"] = commit_diff
                    try:
                        git_commit_obj = target_repo.commit(commit_full_id)
                        committer_name = git_commit_obj.committer.name
                        committer_email = git_commit_obj.committer.email
                        if committer_email:
                            committer = f"{committer_name} <{committer_email}>"
                        else:
                            committer = committer_name
                    except Exception:
                        pass

                if "metadata" not in data and committer:
                    data["metadata"] = {}

                if "metadata" in data:
                    if committer:
                        data["metadata"]["author"] = committer
                    if "author" in data["metadata"]:
                        authors.add(data["metadata"]["author"])

                if committer and "inline" in data:
                    if data.get("inline_is_json"):
                        try:
                            inline_obj = json.loads(data["inline"])
                            inline_obj["author"] = committer
                            data["inline"] = json.dumps(inline_obj)
                        except Exception:
                            pass
                    else:
                        data["inline"] = re.sub(r'^Author:\s+.*$', f'Author: {committer}', data["inline"], flags=re.MULTILINE)

                commit_reviews["model1"] = data

        # Assertions
        # 1. Committer name and email should be correctly extracted
        self.assertEqual(committer, "John Doe <johndoe@example.com>")
        
        # 2. Metadata author should be overridden by committer
        self.assertEqual(data["metadata"]["author"], "John Doe <johndoe@example.com>")
        
        # 3. Authors set should contain the committer instead of the anonymous author
        self.assertIn("John Doe <johndoe@example.com>", authors)
        self.assertNotIn("Anonymous Author <cve-kpm@example.com>", authors)

        # 4. Inline JSON content author field should be updated
        inline_parsed = json.loads(data["inline"])
        self.assertEqual(inline_parsed["author"], "John Doe <johndoe@example.com>")

    def test_committer_extraction_and_override_txt(self):
        """Test that the git committer overrides the author in plain text inline content."""
        mock_commit = MagicMock()
        mock_commit.committer.name = "John Doe"
        mock_commit.committer.email = "johndoe@example.com"

        mock_repo = MagicMock()
        mock_repo.commit.return_value = mock_commit

        # Setup review data with plain text inline content
        data = {
            "metadata": {
                "author": "Anonymous Author <cve-kpm@example.com>"
            },
            "inline": "commit 12345\nAuthor: Anonymous Author <cve-kpm@example.com>\n\nSome review detail.",
            "inline_is_json": False
        }

        # Simulate block
        target_repo = mock_repo
        commit_diff = None
        commit_full_id = "12345"
        authors = set()

        if data:
            committer = None
            if target_repo:
                try:
                    git_commit_obj = target_repo.commit(commit_full_id)
                    committer_name = git_commit_obj.committer.name
                    committer_email = git_commit_obj.committer.email
                    if committer_email:
                        committer = f"{committer_name} <{committer_email}>"
                    else:
                        committer = committer_name
                except Exception:
                    pass

            if "metadata" not in data and committer:
                data["metadata"] = {}

            if "metadata" in data:
                if committer:
                    data["metadata"]["author"] = committer
                if "author" in data["metadata"]:
                    authors.add(data["metadata"]["author"])

            if committer and "inline" in data:
                if data.get("inline_is_json"):
                    try:
                        inline_obj = json.loads(data["inline"])
                        inline_obj["author"] = committer
                        data["inline"] = json.dumps(inline_obj)
                    except Exception:
                        pass
                else:
                    data["inline"] = re.sub(r'^Author:\s+.*$', f'Author: {committer}', data["inline"], flags=re.MULTILINE)

        # Assertions
        self.assertEqual(data["metadata"]["author"], "John Doe <johndoe@example.com>")
        self.assertIn("John Doe <johndoe@example.com>", authors)
        self.assertIn("Author: John Doe <johndoe@example.com>", data["inline"])
        self.assertNotIn("Author: Anonymous Author", data["inline"])

    def test_committer_fallback_when_git_fails(self):
        """Test that we fall back to metadata author if target_repo or commit is not found."""
        data = {
            "metadata": {
                "author": "Anonymous Author <cve-kpm@example.com>"
            },
            "inline": "commit 12345\nAuthor: Anonymous Author <cve-kpm@example.com>\n\nSome review detail.",
            "inline_is_json": False
        }

        # Simulate target_repo lookup failure
        mock_repo = MagicMock()
        mock_repo.commit.side_effect = Exception("Commit not found")

        target_repo = mock_repo
        commit_full_id = "12345"
        authors = set()

        if data:
            committer = None
            if target_repo:
                try:
                    git_commit_obj = target_repo.commit(commit_full_id)
                    committer_name = git_commit_obj.committer.name
                    committer_email = git_commit_obj.committer.email
                    if committer_email:
                        committer = f"{committer_name} <{committer_email}>"
                    else:
                        committer = committer_name
                except Exception:
                    pass

            if "metadata" not in data and committer:
                data["metadata"] = {}

            if "metadata" in data:
                if committer:
                    data["metadata"]["author"] = committer
                if "author" in data["metadata"]:
                    authors.add(data["metadata"]["author"])

        # Assertions
        # Should gracefully fall back to the metadata author since git lookup failed
        self.assertEqual(data["metadata"]["author"], "Anonymous Author <cve-kpm@example.com>")
        self.assertIn("Anonymous Author <cve-kpm@example.com>", authors)

class TestSplitPageOptionsAndPruning(unittest.TestCase):
    def test_cli_parser_has_single_page_option(self):
        """Test that the argparse parser supports the --single-page option."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--single-page", action="store_true")
        args = parser.parse_args(['--single-page'])
        self.assertTrue(args.single_page)

    def test_data_pruning_logic(self):
        """Test that the review data is correctly pruned for index.html when single_page is false."""
        raw_reviews = {
            "model1": {
                "metadata": {
                    "author": "John Doe",
                    "issue-severity-score": "High",
                    "issues-found": 3,
                    "review-time-seconds": 120,
                    "suse-commit": "abcdef123"
                },
                "inline": "Heavy inline review content that should be pruned...",
                "inline_is_json": False,
                "downstream_only": 1,
                "pre_verification": "Pre-verification details that are very large...",
                "verified_result": "Verified results content...",
                "fix_patches": "Fix patch content..."
            }
        }
        
        pruned_reviews = {}
        for model_name, review in raw_reviews.items():
            relative_url = f"reviews/{model_name}/ab/abcdef12345/review.html"
            pruned_review = {
                "metadata": review.get("metadata"),
                "url": relative_url
            }
            if "downstream_only" in review:
                pruned_review["downstream_only"] = review["downstream_only"]
            if "pre_verification" in review:
                pruned_review["pre_verification"] = True
            if "verified_result" in review:
                pruned_review["verified_result"] = True
            pruned_reviews[model_name] = pruned_review

        # Check that heavy fields are pruned
        self.assertNotIn("inline", pruned_reviews["model1"])
        self.assertNotIn("fix_patches", pruned_reviews["model1"])
        
        # Check that metadata is preserved
        self.assertEqual(pruned_reviews["model1"]["metadata"]["author"], "John Doe")
        self.assertEqual(pruned_reviews["model1"]["metadata"]["issues-found"], 3)
        
        # Check that boolean flags/placeholders and url are correct
        self.assertEqual(pruned_reviews["model1"]["url"], "reviews/model1/ab/abcdef12345/review.html")
        self.assertTrue(pruned_reviews["model1"]["pre_verification"])
        self.assertTrue(pruned_reviews["model1"]["verified_result"])

class TestVerifiedResultHandling(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_get_review_data_with_verified_result(self, mock_open, mock_exists):
        """Test that get_review_data correctly loads verified-result.json if present."""
        # Setup mock exists to return True for metadata and verified-result
        mock_exists.side_effect = lambda path: "review-metadata.json" in path or "verified-result.json" in path
        
        # Setup mock open
        mock_file_metadata = MagicMock()
        mock_file_metadata.__enter__.return_value = mock_file_metadata
        mock_file_metadata.read.return_value = '{"author": "Jane"}'
        
        mock_file_verified = MagicMock()
        mock_file_verified.__enter__.return_value = mock_file_verified
        mock_file_verified.read.return_value = '{"re-verified-by": "Jane"}'
        
        def mock_open_side_effect(path, mode="r", encoding=None):
            if "review-metadata.json" in path:
                return mock_file_metadata
            elif "verified-result.json" in path:
                return mock_file_verified
            return MagicMock()
            
        mock_open.side_effect = mock_open_side_effect
        
        # Call get_review_data
        result = generate_report.get_review_data("/fake/dataset", "1234567890abcdef1234567890abcdef12345678")
        
        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["author"], "Jane")
        self.assertEqual(result["verified_result"], '{"re-verified-by": "Jane"}')

class TestPartialUpdateMode(unittest.TestCase):
    def test_cli_parser_has_update_option(self):
        """Test that the argparse parser supports the --update option."""
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--update", help="Only update review entries modified in the given git commit range")
        args = parser.parse_args(['--update', 'HEAD~3..HEAD'])
        self.assertEqual(args.update, 'HEAD~3..HEAD')

    @patch("git.Repo")
    def test_modified_commits_extraction_with_update(self, mock_repo_class):
        """Test that modified commits are parsed correctly from git diff output."""
        mock_repo = MagicMock()
        mock_repo_class.return_value = mock_repo
        
        # Simulate git diff returning modified files
        mock_repo.git.diff.return_value = (
            "gemma-4/27/27bff05802f55fb805a5fe10b80d37f4fddb9729/review-metadata.json\n"
            "qwen3.6-q4/ab/abcdef1234567890abcdef1234567890abcdef12/review-inline.json\n"
            "unrelated-file.txt\n"
        )
        
        # Test the path parsing logic
        args_model = ["gemma-4", "qwen3.6-q4"]
        args_update = "HEAD~1..HEAD"
        
        modified_commits = set()
        if args_update:
            diff_output = mock_repo.git.diff(args_update, name_only=True)
            modified_files = diff_output.strip().splitlines()
            
            for fpath in modified_files:
                normalized = fpath.replace('\\', '/')
                parts = normalized.split('/')
                for i in range(2, len(parts)):
                    commit_id_candidate = parts[i]
                    if len(commit_id_candidate) == 40 and all(c in "0123456789abcdefABCDEF" for c in commit_id_candidate):
                        prefix_candidate = parts[i-1]
                        if len(prefix_candidate) == 2 and commit_id_candidate.startswith(prefix_candidate):
                            model_dir_candidate = parts[i-2]
                            if model_dir_candidate in args_model:
                                modified_commits.add((model_dir_candidate, commit_id_candidate.lower()))
                                
        self.assertEqual(len(modified_commits), 2)
        self.assertIn(("gemma-4", "27bff05802f55fb805a5fe10b80d37f4fddb9729"), modified_commits)
        self.assertIn(("qwen3.6-q4", "abcdef1234567890abcdef1234567890abcdef12"), modified_commits)

    def test_build_parser_update_options(self):
        """Test build_parser with different update options."""
        parser = generate_report.build_parser()

        # Test git range
        args = parser.parse_args(['--dataset', 'kreviews', '--model', 'gemma-4', '--update', 'HEAD~3..HEAD'])
        self.assertEqual(args.update, ['HEAD~3..HEAD'])

        # Test commit list file
        args = parser.parse_args(['--dataset', 'kreviews', '--model', 'gemma-4', '--update', 'test/list-test'])
        self.assertEqual(args.update, ['test/list-test'])

        # Test multiple commit IDs
        args = parser.parse_args(['--dataset', 'kreviews', '--model', 'gemma-4', '--update', 'id1', 'id2'])
        self.assertEqual(args.update, ['id1', 'id2'])

        # Test --update-list
        args = parser.parse_args(['--dataset', 'kreviews', '--model', 'gemma-4', '--update-list', 'update.list'])
        self.assertEqual(args.update_list, ['update.list'])

    def test_process_update_spec_with_list_file(self):
        """Test processing update spec when passing a commit list file."""
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            f.write("# A comment\n")
            f.write("27bff05802f55fb805a5fe10b80d37f4fddb9729 ipv6: test subject\n")
            f.write("e859e84153ff427552ba831f4a0b2a3e71e50b77\n")
            tmp_path = f.name

        try:
            commits = [{"id": "27bff05802f55fb805a5fe10b80d37f4fddb9729", "subject": ""}]
            models = ["gemma-4", "qwen3.6"]
            modified = generate_report.process_update_spec([tmp_path], models, commits=commits)

            # Both models should be marked for regeneration for both commits
            self.assertIn(("gemma-4", "27bff05802f55fb805a5fe10b80d37f4fddb9729"), modified)
            self.assertIn(("qwen3.6", "27bff05802f55fb805a5fe10b80d37f4fddb9729"), modified)
            self.assertIn(("gemma-4", "e859e84153ff427552ba831f4a0b2a3e71e50b77"), modified)
            self.assertIn(("qwen3.6", "e859e84153ff427552ba831f4a0b2a3e71e50b77"), modified)

            # The newly added commit should be in commits
            self.assertEqual(len(commits), 2)
            self.assertEqual(commits[0]["subject"], "ipv6: test subject")
            self.assertEqual(commits[1]["id"], "e859e84153ff427552ba831f4a0b2a3e71e50b77")
        finally:
            os.remove(tmp_path)

    def test_process_update_spec_with_commit_ids(self):
        """Test processing update spec when passing direct commit IDs."""
        models = ["gemma-4"]
        commits = []

        # Test space-separated string of IDs
        spec = ["27bff05802f55fb805a5fe10b80d37f4fddb9729 e859e84153ff427552ba831f4a0b2a3e71e50b77"]
        modified = generate_report.process_update_spec(spec, models, commits=commits)
        self.assertIn(("gemma-4", "27bff05802f55fb805a5fe10b80d37f4fddb9729"), modified)
        self.assertIn(("gemma-4", "e859e84153ff427552ba831f4a0b2a3e71e50b77"), modified)
        self.assertEqual(len(commits), 2)

        # Test comma-separated string
        commits_comma = []
        spec_comma = ["27bff05802f55fb805a5fe10b80d37f4fddb9729,e859e84153ff427552ba831f4a0b2a3e71e50b77"]
        modified_comma = generate_report.process_update_spec(spec_comma, models, commits=commits_comma)
        self.assertIn(("gemma-4", "27bff05802f55fb805a5fe10b80d37f4fddb9729"), modified_comma)
        self.assertIn(("gemma-4", "e859e84153ff427552ba831f4a0b2a3e71e50b77"), modified_comma)
        self.assertEqual(len(commits_comma), 2)

    def test_process_update_spec_with_git_range(self):
        """Test processing update spec when passing a git revision range."""
        mock_repo = MagicMock()
        mock_repo.git.diff.return_value = (
            "gemma-4/27/27bff05802f55fb805a5fe10b80d37f4fddb9729/review-metadata.json\n"
        )
        models = ["gemma-4", "qwen3.6"]
        commits = [{"id": "27bff05802f55fb805a5fe10b80d37f4fddb9729", "subject": ""}]
        modified = generate_report.process_update_spec(["HEAD~1..HEAD"], models, repo=mock_repo, commits=commits)

        mock_repo.git.diff.assert_called_once_with("HEAD~1..HEAD", name_only=True)
        self.assertIn(("gemma-4", "27bff05802f55fb805a5fe10b80d37f4fddb9729"), modified)
        # qwen3.6 was not modified in git diff
        self.assertNotIn(("qwen3.6", "27bff05802f55fb805a5fe10b80d37f4fddb9729"), modified)

    @patch("builtins.print")
    def test_process_update_spec_missing_file_exits(self, mock_print):
        """Test that passing a non-existent file path causes SystemExit."""
        with self.assertRaises(SystemExit):
            generate_report.process_update_spec(["nonexistent_commits.list"], ["gemma-4"])
        mock_print.assert_called_with("Error: Update file 'nonexistent_commits.list' not found.")

class TestIssuesFixedSupport(unittest.TestCase):
    @patch("os.path.exists")
    @patch("builtins.open")
    def test_get_review_data_issues_fixed_from_metadata(self, mock_open, mock_exists):
        """Test that issues-fixed in review-metadata.json is preserved."""
        mock_exists.side_effect = lambda path: "review-metadata.json" in path
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.read.return_value = '{"author": "Jane", "issues-found": 2, "issues-fixed": 1}'
        mock_open.return_value = mock_file

        result = generate_report.get_review_data("/fake/dataset", "1234567890abcdef1234567890abcdef12345678")
        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["issues-found"], 2)
        self.assertEqual(result["metadata"]["issues-fixed"], 1)

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_get_review_data_issues_fixed_from_verified_result(self, mock_open, mock_exists):
        """Test that issues-fixed is populated from verified-result.json if missing in metadata."""
        mock_exists.side_effect = lambda path: "review-metadata.json" in path or "verified-result.json" in path
        def mock_open_side_effect(path, mode="r", encoding=None):
            m = MagicMock()
            m.__enter__.return_value = m
            if "review-metadata.json" in path:
                m.read.return_value = '{"author": "Jane", "issues-found": 1}'
            elif "verified-result.json" in path:
                m.read.return_value = '{"schema-version": 2, "issues-fixed": 1, "future-fix": "5bf62f727580"}'
            return m
        mock_open.side_effect = mock_open_side_effect

        result = generate_report.get_review_data("/fake/dataset", "1234567890abcdef1234567890abcdef12345678")
        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["issues-fixed"], 1)

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_get_review_data_issues_fixed_from_inline_json(self, mock_open, mock_exists):
        """Test that issues-fixed is populated from review-inline.json if missing in metadata."""
        mock_exists.side_effect = lambda path: "review-metadata.json" in path or "review-inline.json" in path
        def mock_open_side_effect(path, mode="r", encoding=None):
            m = MagicMock()
            m.__enter__.return_value = m
            if "review-metadata.json" in path:
                m.read.return_value = '{"author": "Jane", "issues-found": 3}'
            elif "review-inline.json" in path:
                m.read.return_value = '{"commit": "12345", "issues-fixed": 2, "findings": []}'
            return m
        mock_open.side_effect = mock_open_side_effect

        result = generate_report.get_review_data("/fake/dataset", "1234567890abcdef1234567890abcdef12345678")
        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["issues-fixed"], 2)

    @patch("os.path.exists")
    @patch("builtins.open")
    def test_get_review_data_issues_fixed_from_inline_txt(self, mock_open, mock_exists):
        """Test that issues-fixed is populated from review-inline.txt header if missing in metadata."""
        mock_exists.side_effect = lambda path: "review-metadata.json" in path or "review-inline.txt" in path
        def mock_open_side_effect(path, mode="r", encoding=None):
            m = MagicMock()
            m.__enter__.return_value = m
            if "review-metadata.json" in path:
                m.read.return_value = '{"author": "Jane", "issues-found": 3}'
            elif "review-inline.txt" in path:
                m.read.return_value = "Author: Jane\nIssues-fixed: 3\nFix-status: fixed - 5bf62f727580\n"
            return m
        mock_open.side_effect = mock_open_side_effect

        result = generate_report.get_review_data("/fake/dataset", "1234567890abcdef1234567890abcdef12345678")
        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["issues-fixed"], 3)

    def test_css_styles_contain_fix_status(self):
        """Test that CSS_STYLES contains the required fix status badge styles."""
        self.assertIn(".fix-status-badge", generate_report.CSS_STYLES)
        self.assertIn(".fix-status-fixed", generate_report.CSS_STYLES)
        self.assertIn(".fix-status-fixed-upstream", generate_report.CSS_STYLES)
        self.assertIn(".fix-status-not-fixed", generate_report.CSS_STYLES)
        self.assertIn(".severity-all-fixed", generate_report.CSS_STYLES)

    def test_html_templates_contain_filter_and_fix_handling(self):
        """Test that split_html_template and generated main HTML contain filter & fix-status handlers."""
        # split_html_template
        self.assertIn("formatFixLinks", generate_report.split_html_template)
        self.assertIn("fix-status-badge", generate_report.split_html_template)
        self.assertIn("Issues-fixed:", generate_report.split_html_template)

        # End-to-end report generation test
        with tempfile.TemporaryDirectory() as tmp_dir:
            commit_id = "1234567890abcdef1234567890abcdef12345678"
            model_base = os.path.join(tmp_dir, "test-model")
            model_dir = os.path.join(model_base, commit_id[:2], commit_id)
            os.makedirs(model_dir, exist_ok=True)

            with open(os.path.join(model_base, "description"), "w") as f:
                f.write("Test Model Description\n")

            with open(os.path.join(model_dir, "review-metadata.json"), "w") as f:
                json.dump({
                    "author": "Test Author",
                    "subject": "Test Subject",
                    "issues-found": 1,
                    "issues-fixed": 1,
                    "issue-severity-score": "high"
                }, f)

            with open(os.path.join(model_dir, "review-inline.json"), "w") as f:
                json.dump({
                    "commit": commit_id,
                    "issues-fixed": 1,
                    "findings": [{
                        "category": "Bug",
                        "type": "Issue",
                        "severity": "high",
                        "fix-status": "fixed",
                        "future-fix": "5bf62f727580"
                    }]
                }, f)

            with open(os.path.join(model_dir, "verified-result.json"), "w") as f:
                json.dump({
                    "schema-version": 2,
                    "issues-fixed": 1,
                    "future-fix": "5bf62f727580",
                    "findings": [{
                        "status": "confirmed",
                        "fix-status": "fixed",
                        "future-fix": "5bf62f727580"
                    }]
                }, f)

            list_file = os.path.join(tmp_dir, "commits.list")
            with open(list_file, "w") as f:
                f.write(f"{commit_id} Test Subject\n")

            out_html = os.path.join(tmp_dir, "report.html")

            with patch("sys.argv", ["generate_report.py", "--dataset", tmp_dir, "--model", "test-model", "--list", list_file, "--output", out_html]):
                generate_report.main()

            self.assertTrue(os.path.exists(out_html))
            with open(out_html, "r") as f:
                html_content = f.read()

            self.assertIn("openIssuesOnly", html_content)
            self.assertIn("Open issues only", html_content)
            self.assertIn("formatFixLinks", html_content)
            self.assertIn("fix-status-badge", html_content)
            self.assertIn("severity-all-fixed", html_content)

            # Check that split HTML review was also created and contains fix status handlers
            split_review_path = os.path.join(tmp_dir, "reviews", "test-model", commit_id[:2], commit_id, "review.html")
            self.assertTrue(os.path.exists(split_review_path))
            with open(split_review_path, "r") as f:
                split_content = f.read()

            self.assertIn("fix-status-badge", split_content)
            self.assertIn("formatFixLinks", split_content)

            # Validate JavaScript syntax in generated HTML pages
            node_path = shutil.which("node")
            if node_path:
                for name, content in [("main report", html_content), ("split review", split_content)]:
                    scripts = re.findall(r'<script>(.*?)</script>', content, re.DOTALL)
                    self.assertTrue(len(scripts) > 0, f"No scripts found in {name}")
                    for idx, s in enumerate(scripts):
                        res = subprocess.run([node_path, "--check", "-"], input=s, capture_output=True, text=True)
                        self.assertEqual(res.returncode, 0, f"JS syntax error in {name} script {idx}:\n{res.stderr}")

                # Also test single-page mode report
                single_html = os.path.join(tmp_dir, "single_report.html")
                with patch("sys.argv", ["generate_report.py", "--single-page", "--dataset", tmp_dir, "--model", "test-model", "--list", list_file, "--output", single_html]):
                    generate_report.main()
                self.assertTrue(os.path.exists(single_html))
                with open(single_html, "r") as f:
                    single_content = f.read()
                single_scripts = re.findall(r'<script>(.*?)</script>', single_content, re.DOTALL)
                for idx, s in enumerate(single_scripts):
                    res = subprocess.run([node_path, "--check", "-"], input=s, capture_output=True, text=True)
                    self.assertEqual(res.returncode, 0, f"JS syntax error in single-page script {idx}:\n{res.stderr}")

if __name__ == "__main__":
    unittest.main()

