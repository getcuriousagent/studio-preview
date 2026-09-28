"""Is this Studio locked? Asked before every server function does anything.

The Studio's lock is Vercel Authentication, which the operator turns on in
Vercel. A new project starts without it on its production address, so the
Studio checks for itself: it requests its own production address with no
sign-in and no redirects followed. A locked Studio answers with a redirect
to Vercel's sign-in; anything else, including an error, counts as not
locked, and the Studio shows nothing.

The file name starts with an underscore so Vercel does not serve it as a
function of its own.
"""

import os
import re
import time
import urllib.error
import urllib.request

SIGN_IN = "https://vercel.com/sso-api"
REDIRECTS = (301, 302, 303, 307, 308)
HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
REMEMBER_SECONDS = 60

# Only a locked answer is remembered, and only for a minute, so a Studio
# switched back to Standard Protection closes itself within that minute.
# An unlocked answer is asked again every time, so "Check again" works at
# once after the operator turns the lock on.
_locked_until = 0.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _is_sign_in(location):
    return (location == SIGN_IN
            or location.startswith(SIGN_IN + "?")
            or location.startswith(SIGN_IN + "/"))


def check_now():
    """Ask Vercel once. True only for a redirect to Vercel's sign-in."""
    host = os.environ.get("VERCEL_PROJECT_PRODUCTION_URL", "")
    if not HOST_RE.match(host):
        return False
    request = urllib.request.Request(f"https://{host}/", headers={
        "User-Agent": "curious-agent-studio-lock-check",
    })
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=8) as response:
            status, location = response.status, response.headers.get("Location", "")
    except urllib.error.HTTPError as e:
        status, location = e.code, (e.headers.get("Location", "") if e.headers else "")
    except Exception:
        return False
    return status in REDIRECTS and _is_sign_in(location or "")


def is_locked():
    global _locked_until
    if time.monotonic() < _locked_until:
        return True
    locked = check_now()
    _locked_until = time.monotonic() + REMEMBER_SECONDS if locked else 0.0
    return locked
