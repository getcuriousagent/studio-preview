"""A repository's public key for Actions secrets, so the page can seal a
secret before it leaves the browser.

`/api/secret_key?repo=owner/name` answers `{"key_id": …, "key": …}`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _github  # noqa: E402
from _studio import StudioHandler  # noqa: E402


class handler(StudioHandler):

    def get(self, query):
        return 200, _github.get_secrets_key(query.get("repo", ""))
