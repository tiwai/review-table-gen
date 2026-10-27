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

"""Minimal local web service rendering kernel review reports on demand."""

import argparse
import collections
import gzip
import hashlib
import html
import json
import logging
import logging.handlers
import os
import re
import socket
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit

import generate_report
from generate_report import (
    collect_review_data,
    get_review_data,
    load_model_sources,
    parse_commit_list,
    prune_for_index,
    render_index_html,
    render_review_html,
)

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LOG_LEVELS = ("debug", "info", "warning", "error")
DEFAULT_CACHE_DIR = "~/.cache/review_server"
DISK_CACHE_VERSION = 1      # bump when the on-disk format changes
PAGE_CACHE_SIZE = 128       # number of rendered review pages kept in memory

log = logging.getLogger("review_server")


def load_config(path):
    """Load and validate the server config file."""
    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)
    branches = config.get("branches")
    if not isinstance(branches, dict) or not branches:
        raise ValueError("config must contain a non-empty 'branches' object")
    # Relative paths are resolved against the config file location
    # (except for the list, see below)
    base = os.path.dirname(os.path.abspath(path))
    for name, branch in branches.items():
        if "list" not in branch or "models" not in branch:
            raise ValueError(f"branch '{name}' needs 'list' and 'models'")
        dataset = branch.get("dataset", config.get("dataset"))
        if not dataset:
            raise ValueError(f"no dataset given for branch '{name}'")
        # '~' is expanded; absolute paths are kept as they are
        dataset = os.path.join(base, os.path.expanduser(dataset))
        branch["dataset"] = dataset
        # The list is looked up in the dataset directory first (e.g.
        # "branches/<NAME>/list"), then relative to the config file
        list_path = os.path.expanduser(branch["list"])
        in_dataset = os.path.join(dataset, list_path)
        branch["list"] = in_dataset if os.path.exists(in_dataset) else os.path.join(base, list_path)
    return config


class ReportCache:
    """Per-branch cache of the collected review data and rendered index.

    A branch is rebuilt only when its fingerprint (see fingerprint()) changes.
    The check is done at most every 'ttl' seconds, and the rebuild runs in the
    background while the previous version keeps being served.  The result is
    also stored in 'cache_dir' (if given) to survive a server restart.
    """

    def __init__(self, config, ttl, cache_dir=None):
        self.config = config
        self.ttl = ttl
        self.cache_dir = os.path.expanduser(cache_dir) if cache_dir else None
        self.entries = {}
        self.locks = {name: threading.Lock() for name in config["branches"]}
        self.rebuilding = set()
        self.pages = collections.OrderedDict()
        self.pages_lock = threading.Lock()

    def option(self, branch, key, default):
        return branch.get(key, self.config.get(key, default))

    def branch_links(self):
        return {name: f"/b/{quote(name, safe='')}/" for name in self.config["branches"]}

    def list_stat(self, branch):
        st = os.stat(branch["list"])
        return (st.st_mtime_ns, st.st_size)

    def fingerprint(self, name, branch):
        """Cheap digest of everything that determines the rendered output.

        It covers the code, the config, the commit list, and the model
        directories.  The latter are checked by the mtimes of the description
        files and of the two-hex-digit prefix directories, so a new review is
        noticed without reading any review file.
        """
        h = hashlib.sha256()

        def add(*vals):
            h.update(repr(vals).encode("utf-8"))

        add(DISK_CACHE_VERSION, os.stat(generate_report.__file__).st_mtime_ns,
            os.stat(__file__).st_mtime_ns)
        add(json.dumps([name, branch, self.option(branch, "kerncvs", False),
                        self.option(branch, "rows", 50),
                        self.option(branch, "show_review_time", False),
                        self.branch_links()], sort_keys=True))
        add(self.list_stat(branch))
        for model in branch["models"]:
            path = os.path.join(branch["dataset"], model)
            try:
                add(model, os.stat(os.path.join(path, "description")).st_mtime_ns)
                with os.scandir(path) as it:
                    subdirs = sorted((e.name, e.stat().st_mtime_ns)
                                     for e in it if e.is_dir())
                add(subdirs)
            except OSError as e:
                add(model, str(e))
        return h.hexdigest()

    def get(self, name, force=False):
        branch = self.config["branches"][name]
        with self.locks[name]:
            entry = self.entries.get(name)
            if entry is None and not force:
                entry = self.load_from_disk(name)
                if entry:
                    self.entries[name] = entry
            if force or entry is None:
                entry = self.rebuild(name, branch)
                self.entries[name] = entry
                return entry
            if name not in self.rebuilding and self.is_due(entry, branch):
                entry["checked"] = time.monotonic()
                entry["list_stat"] = self.list_stat(branch)
                if self.fingerprint(name, branch) != entry["fingerprint"]:
                    self.rebuilding.add(name)
                    threading.Thread(target=self.rebuild_in_background,
                                     args=(name, branch), daemon=True).start()
            return entry

    def is_due(self, entry, branch):
        return (time.monotonic() - entry["checked"] > self.ttl or
                self.list_stat(branch) != entry["list_stat"])

    def rebuild_in_background(self, name, branch):
        try:
            entry = self.rebuild(name, branch)
            with self.locks[name]:
                self.entries[name] = entry
        except Exception:
            log.exception("background rebuild of branch %s failed", name)
        finally:
            with self.locks[name]:
                self.rebuilding.discard(name)

    def rebuild(self, name, branch):
        start = time.monotonic()
        # Taken before reading anything, so that a change made during the
        # build is noticed at the next check
        fingerprint = self.fingerprint(name, branch)
        entry = self.build(name, branch, fingerprint)
        log.debug("rebuilt branch %s: %d commits in %.2fs", name,
                  len(entry["commits"]), time.monotonic() - start)
        self.save_to_disk(name, entry)
        return entry

    def build(self, name, branch, fingerprint):
        list_stat = self.list_stat(branch)
        commits = parse_commit_list(branch["list"])
        dataset_sources, model_name_to_dir = load_model_sources(branch["dataset"], branch["models"])
        processed_data, authors = collect_review_data(commits, dataset_sources)
        index_data = prune_for_index(processed_data, model_name_to_dir)
        kerncvs = self.option(branch, "kerncvs", False)
        index_html = render_index_html(
            branch.get("title", f"{name} Potential Regressions"),
            authors, self.branch_links(), index_data, list(dataset_sources.keys()),
            self.option(branch, "rows", 50), kerncvs,
            self.option(branch, "show_review_time", False))
        return self.make_entry(
            fingerprint, list_stat, kerncvs, index_html.encode("utf-8"),
            json.dumps(index_data, separators=(",", ":")).encode("utf-8"),
            {d: (n, dataset_sources[n]) for n, d in model_name_to_dir.items()})

    def make_entry(self, fingerprint, list_stat, kerncvs, index_html, index_json, models):
        return {
            "checked": time.monotonic(),
            "fingerprint": fingerprint,
            "list_stat": list_stat,
            "kerncvs": kerncvs,
            "index_html": index_html,
            "index_json": index_json,
            "gzipped": {},      # compressed bodies, filled on demand
            "commits": {item["full_id"].lower(): item for item in json.loads(index_json)},
            "models": models,
        }

    def body(self, entry, key, compressed):
        """Return the 'index_html' or 'index_json' body, optionally gzipped."""
        if not compressed:
            return entry[key]
        if key not in entry["gzipped"]:
            entry["gzipped"][key] = gzip.compress(entry[key], 6)
        return entry["gzipped"][key]

    def disk_path(self, name):
        return os.path.join(self.cache_dir, quote(name, safe="") + ".json")

    def save_to_disk(self, name, entry):
        if not self.cache_dir:
            return
        path = self.disk_path(name)
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({
                    "version": DISK_CACHE_VERSION,
                    "fingerprint": entry["fingerprint"],
                    "list_stat": entry["list_stat"],
                    "kerncvs": entry["kerncvs"],
                    "models": entry["models"],
                    "index_html": entry["index_html"].decode("utf-8"),
                    "index_json": entry["index_json"].decode("utf-8"),
                }, f)
            os.replace(tmp, path)
        except OSError as e:
            log.warning("cannot write cache file %s: %s", path, e)
            try:
                os.unlink(tmp)
            except OSError:
                pass

    def load_from_disk(self, name):
        """Load a previously saved entry; it's treated as due for a check."""
        if not self.cache_dir:
            return None
        path = self.disk_path(name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data["version"] != DISK_CACHE_VERSION:
                return None
            entry = self.make_entry(
                data["fingerprint"], tuple(data["list_stat"]), data["kerncvs"],
                data["index_html"].encode("utf-8"), data["index_json"].encode("utf-8"),
                {d: tuple(v) for d, v in data["models"].items()})
        except FileNotFoundError:
            return None
        except (OSError, ValueError, KeyError, TypeError) as e:
            log.warning("ignoring unusable cache file %s: %s", path, e)
            return None
        entry["checked"] = float("-inf")
        log.debug("loaded branch %s from %s", name, path)
        return entry

    def get_page(self, key):
        with self.pages_lock:
            page = self.pages.get(key)
            if page is not None:
                self.pages.move_to_end(key)
            return page

    def put_page(self, key, page):
        with self.pages_lock:
            self.pages[key] = page
            self.pages.move_to_end(key)
            while len(self.pages) > PAGE_CACHE_SIZE:
                self.pages.popitem(last=False)


class Handler(BaseHTTPRequestHandler):
    server_version = "KernelReviewServer/1.0"
    cache = None    # set in make_server()

    def log_message(self, format, *args):
        # Access log lines
        log.info("%s %s", self.address_string(), format % args)

    def log_error(self, format, *args):
        # Malformed requests, timeouts and the like
        log.warning("%s %s", self.address_string(), format % args)

    def send_body(self, code, body, ctype="text/html; charset=utf-8", headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def send_cached(self, entry, key, ctype):
        """Send a cached index body with ETag and optional gzip encoding."""
        accepted = [t.split(";")[0].strip() for t in
                    self.headers.get("Accept-Encoding", "").split(",")]
        compressed = "gzip" in accepted
        etag = '"%s-%s%s"' % (entry["fingerprint"][:32], key, "-gz" if compressed else "")
        headers = {"ETag": etag, "Cache-Control": "no-cache", "Vary": "Accept-Encoding"}
        if etag in [t.strip() for t in self.headers.get("If-None-Match", "").split(",")]:
            return self.send_body(304, b"", ctype, headers)
        if compressed:
            headers["Content-Encoding"] = "gzip"
        self.send_body(200, self.cache.body(entry, key, compressed), ctype, headers)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def fail(self, code, message):
        self.send_body(code, f"<h1>{code}</h1><p>{html.escape(message)}</p>\n")

    def do_GET(self):
        url = urlsplit(self.path)
        force = "reload" in parse_qs(url.query)
        parts = [unquote(p) for p in url.path.split("/")]
        branches = self.cache.config["branches"]
        try:
            if url.path == "/":
                self.serve_root()
            elif len(parts) == 3 and parts[1] == "api" and parts[2].endswith(".json"):
                name = parts[2][:-len(".json")]
                if name not in branches:
                    return self.fail(404, f"Unknown branch '{name}'")
                self.send_cached(self.cache.get(name, force), "index_json",
                                 "application/json")
            elif len(parts) >= 3 and parts[1] == "b":
                name = parts[2]
                if name not in branches:
                    return self.fail(404, f"Unknown branch '{name}'")
                rest = parts[3:]
                if not rest:
                    self.redirect(f"/b/{quote(name, safe='')}/")
                elif rest == [""]:
                    self.send_cached(self.cache.get(name, force), "index_html",
                                     "text/html; charset=utf-8")
                elif len(rest) == 5 and rest[0] == "reviews" and rest[4] == "review.html":
                    self.serve_review(name, rest[1], rest[2], rest[3], force)
                else:
                    self.fail(404, "Not found")
            else:
                self.fail(404, "Not found")
        except Exception as e:
            log.exception("error serving %s", self.path)
            self.fail(500, str(e))

    def serve_root(self):
        names = list(self.cache.config["branches"])
        if len(names) == 1:
            return self.redirect(f"/b/{quote(names[0], safe='')}/")
        items = "".join('<li><a href="/b/%s/">%s</a></li>' % (quote(n, safe=""), html.escape(n))
                        for n in names)
        self.send_body(200, "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">"
                       "<title>Kernel Reviews</title></head><body>"
                       f"<h1>Kernel Reviews</h1><ul>{items}</ul></body></html>\n")

    def serve_review(self, name, model_dir, prefix, sha, force):
        sha = sha.lower()
        if not SHA_RE.match(sha) or prefix != sha[:2]:
            return self.fail(400, "Invalid commit ID")
        entry = self.cache.get(name, force)
        if model_dir not in entry["models"]:
            return self.fail(404, f"Unknown model '{model_dir}'")
        item = entry["commits"].get(sha)
        if item is None:
            return self.fail(404, f"Commit {sha} is not in branch '{name}'")
        model_name, model_path = entry["models"][model_dir]
        # Rendered pages are reused as long as the review files are untouched
        key = None
        try:
            review_dir = os.path.join(model_path, sha[:2], sha)
            key = (name, model_dir, sha, entry["fingerprint"],
                   os.stat(review_dir).st_mtime_ns,
                   os.stat(os.path.join(review_dir, "review-metadata.json")).st_mtime_ns)
        except OSError:
            pass
        page = self.cache.get_page(key) if key and not force else None
        if page is None:
            review = get_review_data(model_path, sha)
            if not review:
                return self.fail(404, f"No review of {sha} by {model_name}")
            page = render_review_html(model_name, item["id"], item["subject"], review,
                                      f"/b/{quote(name, safe='')}/",
                                      entry["kerncvs"]).encode("utf-8")
            if key:
                self.cache.put_page(key, page)
        self.send_body(200, page)


class ReviewHTTPServer(ThreadingHTTPServer):
    ssl_context = None      # set when HTTPS is enabled
    peek_timeout = 10       # seconds to wait for the first byte

    def finish_request(self, request, client_address):
        # This runs in the per-connection thread.  With HTTPS enabled, both
        # protocols are served on the same port: a TLS connection always
        # starts with a handshake record (0x16), which no HTTP request does.
        if self.ssl_context:
            request.settimeout(self.peek_timeout)
            try:
                first = request.recv(1, socket.MSG_PEEK)
            except OSError:
                return
            request.settimeout(None)
            if not first:
                return
            if first[0] == 0x16:
                request = self.ssl_context.wrap_socket(request, server_side=True)
                try:
                    super().finish_request(request, client_address)
                finally:
                    self.shutdown_request(request)
                return
        super().finish_request(request, client_address)

    def handle_error(self, request, client_address):
        # A failed TLS handshake or a dropped connection is worth a single
        # log line, not a traceback
        err = sys.exc_info()[1]
        if isinstance(err, (ssl.SSLError, ConnectionError)):
            log.info("%s connection error: %s", client_address[0], err)
        else:
            log.exception("error handling request from %s", client_address[0])


def make_server(config, host, port, ttl, certfile=None, keyfile=None, cache_dir=None):
    handler = type("ConfiguredHandler", (Handler,),
                   {"cache": ReportCache(config, ttl, cache_dir)})
    server = ReviewHTTPServer((host, port), handler)
    if certfile:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile, keyfile)
        server.ssl_context = ctx
    return server


def setup_logging(log_file, level):
    if log_file:
        # Reopens the file when it's rotated away (e.g. by logrotate)
        handler = logging.handlers.WatchedFileHandler(log_file)
    else:
        handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(level.upper())


def main():
    parser = argparse.ArgumentParser(description="Serve kernel review reports over HTTP(S).")
    parser.add_argument("--config", required=True, help="Server config JSON file")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--ttl", type=float, default=60,
                        help="Seconds between checks for changed data; a changed branch is "
                        "rebuilt in the background (default: 60)")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR,
                        help=f"Directory for the persistent cache (default: {DEFAULT_CACHE_DIR})")
    parser.add_argument("--no-disk-cache", action="store_true",
                        help="Do not keep the cache across restarts")
    parser.add_argument("--certfile", help="PEM certificate file; enables HTTPS in addition to HTTP")
    parser.add_argument("--keyfile", help="PEM private key file (if not included in --certfile)")
    parser.add_argument("--log-file", help="Write logs to this file instead of stderr")
    parser.add_argument("--log-level", choices=LOG_LEVELS, default="warning",
                        help="Minimum level to log; 'info' includes the access log (default: warning)")
    args = parser.parse_args()

    try:
        setup_logging(args.log_file, args.log_level)
    except OSError as e:
        print(f"Error: Could not open log file '{args.log_file}': {e}")
        sys.exit(1)

    if args.keyfile and not args.certfile:
        print("Error: --keyfile requires --certfile.")
        sys.exit(1)

    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error: Could not load config '{args.config}': {e}")
        sys.exit(1)

    try:
        server = make_server(config, args.host, args.port, args.ttl,
                             args.certfile, args.keyfile,
                             None if args.no_disk_cache else args.cache_dir)
    except (OSError, ssl.SSLError) as e:
        print(f"Error: Could not start server: {e}")
        sys.exit(1)
    schemes = ["http", "https"] if args.certfile else ["http"]
    urls = " and ".join(f"{s}://{args.host}:{server.server_address[1]}/" for s in schemes)
    print(f"Serving on {urls}", flush=True)
    log.info("serving on %s", urls)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
