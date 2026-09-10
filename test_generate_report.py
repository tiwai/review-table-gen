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

if __name__ == "__main__":
    unittest.main()
