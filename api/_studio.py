"""What every Studio server function shares.

A function subclasses `StudioHandler` and defines `get(query)` and/or
`post(body)`, each returning `(status, payload)`. The handler checks the
lock first, answers in JSON, never caches, and logs nothing about a request:
a request body may hold a sealed secret, and a query may name a repository.
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _github  # noqa: E402
import _lock  # noqa: E402

MAX_BODY = 64 * 1024
NOT_LOCKED = {"locked": False}


class StudioHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def send_json(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _answer(self, method):
        if not _lock.is_locked():
            self.send_json(423, NOT_LOCKED)
            return
        if not hasattr(self, method):
            self.send_json(405, {"error": "This address does not take that kind of request."})
            return
        try:
            if method == "get":
                query = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
                status, payload = self.get(query)
            else:
                body = self._read_json()
                if body is None:
                    return
                status, payload = self.post(body)
        except _github.GitHubError as e:
            status, payload = e.status, {"error": e.sentence}
        except Exception:
            status, payload = 500, {"error": "Something went wrong inside the Studio."}
        self.send_json(status, payload)

    def _read_json(self):
        """The body of a POST, or None after answering 400.

        A POST must carry `X-Studio: 1` and a JSON content type. A page on
        another site cannot send either without the browser first asking
        this Studio's permission, which it never gives."""
        if self.headers.get("X-Studio") != "1":
            self.send_json(400, {"error": "The request did not come from the Studio's own page."})
            return None
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            self.send_json(400, {"error": "The request was not JSON."})
            return None
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self.send_json(400, {"error": "The request was too large."})
            return None
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            self.send_json(400, {"error": "The request was not JSON."})
            return None
        if not isinstance(body, dict):
            self.send_json(400, {"error": "The request was not a JSON object."})
            return None
        return body

    def do_GET(self):
        self._answer("get")

    def do_POST(self):
        self._answer("post")
