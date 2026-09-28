"""Store one Actions secret that the page has already sealed.

POST `/api/secret` with `{"repo", "name", "key_id", "encrypted_value"}`.
The page sealed the value with the repository's public key, so the Studio
cannot read it: it checks the shape and passes it to GitHub. Only the
secrets setup asks for can be set here.
"""

import base64
import binascii
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _github  # noqa: E402
from _studio import StudioHandler  # noqa: E402

# The runner's secrets, as setup.py's REQUIRED_SECRETS names them.
SETUP_SECRETS = ("LLM_API_KEY", "MY_GITHUB_TOKEN", "GMAIL_APP_PASSWORD", "OPERATOR_EMAIL")
KEY_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SEALED_OVERHEAD = 48  # a sealed box adds a 32-byte key and a 16-byte tag
MAX_SEALED = 8 * 1024


def _is_sealed(value):
    if not isinstance(value, str) or len(value) > MAX_SEALED:
        return False
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return False
    return len(raw) > SEALED_OVERHEAD


class handler(StudioHandler):

    def post(self, body):
        name = body.get("name")
        if name not in SETUP_SECRETS:
            return 400, {"error": "The Studio only sets the secrets setup asks for."}
        if not isinstance(body.get("key_id"), str) or not KEY_ID_RE.match(body["key_id"]):
            return 400, {"error": "The secret's key id is missing."}
        if not _is_sealed(body.get("encrypted_value")):
            return 400, {"error": "The secret was not sealed by the page. Reload and try again."}
        _github.put_secret(body.get("repo", ""), name, body["encrypted_value"], body["key_id"])
        return 200, {"set": name}
