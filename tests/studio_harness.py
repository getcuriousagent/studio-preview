"""Load the Studio's server functions and call them without a server.

`call(name, method, ...)` builds a request in memory, runs the function's
handler on it, and returns (status, headers, body_text).
"""

import importlib.util
import io
import os
import sys
from email.message import Message

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(STUDIO, "api")
if API not in sys.path:
    sys.path.insert(0, API)

import _github  # noqa: E402
import _lock  # noqa: E402
import _studio  # noqa: E402

_loaded = {}


def function_names():
    return sorted(f[:-3] for f in os.listdir(API)
                  if f.endswith(".py") and not f.startswith("_"))


def load(name):
    if name not in _loaded:
        spec = importlib.util.spec_from_file_location(f"studio_api_{name}", os.path.join(API, f"{name}.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _loaded[name] = module
    return _loaded[name]


def call(name, method="GET", path=None, body=b"", headers=None):
    cls = load(name).handler
    h = cls.__new__(cls)
    h.rfile = io.BytesIO(body)
    h.wfile = io.BytesIO()
    h.path = path or f"/api/{name}"
    h.command = method
    h.request_version = "HTTP/1.1"
    h.requestline = f"{method} {h.path} HTTP/1.1"
    h.client_address = ("127.0.0.1", 0)
    h.close_connection = True
    message = Message()
    for k, v in (headers or {}).items():
        message[k] = v
    if body and "Content-Length" not in (headers or {}):
        message["Content-Length"] = str(len(body))
    h.headers = message
    getattr(h, f"do_{method}")()
    raw = h.wfile.getvalue().decode("utf-8")
    head, _, text = raw.partition("\r\n\r\n")
    lines = head.split("\r\n")
    status = int(lines[0].split()[1])
    response_headers = dict(line.split(": ", 1) for line in lines[1:])
    return status, response_headers, text


def set_locked(locked):
    """Make the lock check answer `locked` without asking Vercel."""
    _lock._locked_until = 0.0
    _lock.check_now = (lambda: True) if locked else (lambda: False)


_real_check_now = _lock.check_now


def restore_lock():
    _lock.check_now = _real_check_now
    _lock._locked_until = 0.0
