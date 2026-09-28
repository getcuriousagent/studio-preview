"""The first thing the Studio's page asks: is it locked, and does its GitHub
key work?

`/api/status`. Unlocked, it answers 423 and `{"locked": false}` and nothing
else, as every function does. Locked, it answers with the account the key
belongs to, or why the key did not work.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _github  # noqa: E402
from _studio import StudioHandler  # noqa: E402


class handler(StudioHandler):

    def get(self, query):
        try:
            github = {"ok": True, "login": _github.whoami()}
        except _github.GitHubError as e:
            github = {"ok": False, "error": e.sentence}
        return 200, {"locked": True, "github": github}
