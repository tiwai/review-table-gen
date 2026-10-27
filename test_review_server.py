import unittest
import json
import logging
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request

import review_server

TEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test")
SHA = "27bff05802f55fb805a5fe10b80d37f4fddb9729"

class TestReviewServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        config_path = os.path.join(cls.tmpdir.name, "server.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({
                "dataset": os.path.join(TEST_DIR, "data"),
                "branches": {
                    "test": {"list": os.path.join(TEST_DIR, "list-test"),
                             "models": ["gemma-4", "qwen3.6-q4"],
                             "title": "Test Report"},
                    "other": {"list": os.path.join(TEST_DIR, "list-test"),
                              "models": ["gemma-4"]},
                },
            }, f)
        config = review_server.load_config(config_path)
        cls.server = review_server.make_server(config, "127.0.0.1", 0, 60)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmpdir.cleanup()

    def get(self, path):
        try:
            with urllib.request.urlopen(self.base + path) as resp:
                return resp.status, resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8")

    def test_root_lists_branches(self):
        status, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertIn('href="/b/test/"', body)
        self.assertIn('href="/b/other/"', body)

    def test_index_page(self):
        status, body = self.get("/b/test/")
        self.assertEqual(status, 200)
        self.assertIn("<title>Test Report</title>", body)
        self.assertIn('id="branchSelect"', body)
        self.assertIn('<option value="/b/other/">other</option>', body)

    def test_branch_without_slash_redirects(self):
        # urllib follows the redirect to the index page
        status, body = self.get("/b/test")
        self.assertEqual(status, 200)
        self.assertIn("<title>Test Report</title>", body)

    def test_api_json(self):
        status, body = self.get("/api/test.json")
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data), 3)
        item = next(i for i in data if i["full_id"] == SHA)
        self.assertEqual(set(item["reviews"]), {"Gemma-4-26B-A4B", "Qwen3.6-35B-A3B"})
        self.assertEqual(item["reviews"]["Gemma-4-26B-A4B"]["url"],
                         f"reviews/gemma-4/27/{SHA}/review.html")

    def test_review_page(self):
        status, body = self.get(f"/b/test/reviews/gemma-4/27/{SHA}/review.html")
        self.assertEqual(status, 200)
        self.assertIn('href="/b/test/"', body)
        self.assertIn(f'"commit_id": "{SHA}"', body)

    def test_review_model_not_in_branch(self):
        status, _ = self.get(f"/b/other/reviews/qwen3.6-q4/27/{SHA}/review.html")
        self.assertEqual(status, 404)

    def test_invalid_requests(self):
        self.assertEqual(self.get("/b/unknown/")[0], 404)
        self.assertEqual(self.get("/api/unknown.json")[0], 404)
        self.assertEqual(self.get("/b/test/reviews/gemma-4/27/27bff058/review.html")[0], 400)
        self.assertEqual(self.get(f"/b/test/reviews/gemma-4/28/{SHA}/review.html")[0], 400)
        self.assertEqual(self.get("/b/test/reviews/gemma-4/00/" + "0" * 40 + "/review.html")[0], 404)
        self.assertEqual(self.get("/b/test/reviews/..%2F..%2Fetc/27/" + SHA + "/review.html")[0], 404)
        self.assertEqual(self.get("/b/test/other")[0], 404)

class TestLogging(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_file = os.path.join(self.tmpdir.name, "server.log")
        config = {"branches": {"test": {"list": os.path.join(TEST_DIR, "list-test"),
                                        "models": ["gemma-4"],
                                        "dataset": os.path.join(TEST_DIR, "data")}}}
        self.server = review_server.make_server(config, "127.0.0.1", 0, 60)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for handler in review_server.log.handlers[:]:
            review_server.log.removeHandler(handler)
            handler.close()
        review_server.log.setLevel(logging.NOTSET)
        self.tmpdir.cleanup()

    def read_log_after_request(self, level):
        review_server.setup_logging(self.log_file, level)
        urllib.request.urlopen(self.base + "/b/test/?reload=1").read()
        with open(self.log_file, encoding="utf-8") as f:
            return f.read()

    def test_warning_level_hides_access_log(self):
        self.assertEqual(self.read_log_after_request("warning"), "")

    def test_info_level_logs_access(self):
        log = self.read_log_after_request("info")
        self.assertIn('INFO 127.0.0.1 "GET /b/test/?reload=1 HTTP/1.1" 200', log)
        self.assertNotIn("DEBUG", log)

    def test_debug_level_logs_rebuild(self):
        log = self.read_log_after_request("debug")
        self.assertIn("DEBUG rebuilt branch test: 3 commits", log)

@unittest.skipUnless(shutil.which("openssl"), "openssl not available")
class TestReviewServerHTTPS(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cert = os.path.join(self.tmpdir.name, "cert.pem")
        self.key = os.path.join(self.tmpdir.name, "key.pem")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "1", "-subj", "/CN=localhost",
                        "-keyout", self.key, "-out", self.cert],
                       check=True, capture_output=True,
                       # don't depend on the system openssl config
                       env=dict(os.environ, OPENSSL_CONF=os.devnull))
        config = {"branches": {"test": {"list": os.path.join(TEST_DIR, "list-test"),
                                        "models": ["gemma-4"],
                                        "dataset": os.path.join(TEST_DIR, "data")}}}
        self.server = review_server.make_server(config, "127.0.0.1", 0, 60,
                                                self.cert, self.key)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmpdir.cleanup()

    def test_https_index(self):
        ctx = ssl.create_default_context(cafile=self.cert)
        ctx.check_hostname = False
        with urllib.request.urlopen(f"https://127.0.0.1:{self.port}/b/test/",
                                    context=ctx) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn('id="branchSelect"', resp.read().decode("utf-8"))

    def test_plain_http_on_same_port(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/b/test/",
                                    timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn('id="branchSelect"', resp.read().decode("utf-8"))

    def test_idle_connection_does_not_block(self):
        # A client that connects but sends nothing must not stall others
        with socket.create_connection(("127.0.0.1", self.port)):
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/",
                                        timeout=5) as resp:
                self.assertEqual(resp.status, 200)

if __name__ == "__main__":
    unittest.main()
