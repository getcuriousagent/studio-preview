"""Wait a given number of seconds, then say how long it waited.

A first test of Curious Agent Studio on Vercel: it measures how long one
request may run on the plan in use, which a live chat reply will need to
know. `/api/wait?seconds=30`. Capped at 900.
"""

import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse


class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        try:
            seconds = max(0, min(900, int(query.get("seconds", ["0"])[0])))
        except ValueError:
            seconds = 0
        start = time.monotonic()
        time.sleep(seconds)
        data = json.dumps({"asked": seconds,
                           "waited": round(time.monotonic() - start, 1)}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)
