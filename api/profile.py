"""Read one agent's settings from GitHub and return a few of them.

A first test of Curious Agent Studio on Vercel. It reads `agent_profile.md`
from the runner repository named in AGENT_RUNNER_REPO, using the token in
GITHUB_TOKEN, and returns four settings as JSON. It writes nothing.

Both values are Vercel environment variables: set once, in Vercel, and
never sent to the browser.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

SHOWN = ["agent_name", "model_name", "monthly_limit", "dress_rehearsal"]
REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")


def parse_profile(text):
    """The engine's own reading of `agent_profile.md`: `Key: value` lines,
    the key lower-cased with spaces as underscores. Headings, quotes and
    table rows are skipped."""
    settings = {}
    for line in text.splitlines():
        if ": " not in line or line.startswith(("#", ">", "|", "-", "*")):
            continue
        key, value = line.split(": ", 1)
        settings[key.strip().lower().replace(" ", "_")] = value.strip()
    return settings


def fetch_profile(repo, token):
    url = f"https://api.github.com/repos/{repo}/contents/agent_profile.md"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "curious-agent-studio",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.load(resp)
    return base64.b64decode(body["content"]).decode("utf-8")


class handler(BaseHTTPRequestHandler):

    def _send(self, status, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        repo = os.environ.get("AGENT_RUNNER_REPO", "")
        token = os.environ.get("GITHUB_TOKEN", "")
        if not REPO_RE.match(repo):
            self._send(500, {"error": "AGENT_RUNNER_REPO is not set to owner/repository in Vercel."})
            return
        if not token:
            self._send(500, {"error": "GITHUB_TOKEN is not set in Vercel."})
            return
        try:
            settings = parse_profile(fetch_profile(repo, token))
        except urllib.error.HTTPError as e:
            self._send(502, {"error": f"GitHub answered {e.code} for {repo}. Check the token can read that repository."})
            return
        except Exception as e:
            self._send(502, {"error": f"Could not read the profile: {type(e).__name__}."})
            return
        self._send(200, {"repository": repo,
                         "settings": {k: settings.get(k) for k in SHOWN}})
