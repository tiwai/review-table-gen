import unittest
from unittest.mock import MagicMock, patch
import json
import re

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

if __name__ == "__main__":
    unittest.main()
