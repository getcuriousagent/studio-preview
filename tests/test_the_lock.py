"""The Studio counts itself locked only when its own production address
sends a stranger to Vercel's sign-in. Anything else, including an error,
is not locked."""

import io
import os
import unittest
import urllib.error
from email.message import Message
from unittest import mock

import studio_harness  # noqa: F401  (puts api/ on the path)
import _lock

SIGN_IN = "https://vercel.com/sso-api?url=https%3A%2F%2Fstudio.example.vercel.app%2F&nonce=abc"


def _headers(location):
    m = Message()
    if location is not None:
        m["Location"] = location
    return m


class _Answer:
    """What the opener does: raise a redirect, return a page, or fail."""

    def __init__(self, status=None, location=None, error=None):
        self.status, self.location, self.error = status, location, error
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        if self.error:
            raise self.error
        if self.status in _lock.REDIRECTS:
            raise urllib.error.HTTPError(request.full_url, self.status, "Found",
                                         _headers(self.location), io.BytesIO(b""))
        if self.status >= 400:
            raise urllib.error.HTTPError(request.full_url, self.status, "No",
                                         _headers(None), io.BytesIO(b""))
        response = mock.MagicMock()
        response.status = self.status
        response.headers = _headers(self.location)
        response.__enter__.return_value = response
        return response


class TheLockCheck(unittest.TestCase):

    def setUp(self):
        studio_harness.restore_lock()
        self.env = mock.patch.dict(os.environ, {"VERCEL_PROJECT_PRODUCTION_URL": "studio.example.vercel.app"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        studio_harness.restore_lock()

    def ask(self, answer):
        with mock.patch.object(_lock.urllib.request, "build_opener", return_value=answer):
            return _lock.check_now()

    def test_a_redirect_to_vercels_sign_in_is_locked(self):
        for status in (302, 307):
            self.assertTrue(self.ask(_Answer(status, SIGN_IN)), status)

    def test_the_page_itself_is_not_locked(self):
        self.assertFalse(self.ask(_Answer(200)))

    def test_a_redirect_anywhere_else_is_not_locked(self):
        for location in ("https://example.com/login", "https://vercel.com/login",
                         "https://vercel.com/sso-api.example.com/", "", None):
            self.assertFalse(self.ask(_Answer(302, location)), location)

    def test_an_error_is_not_locked(self):
        self.assertFalse(self.ask(_Answer(error=urllib.error.URLError("down"))))
        self.assertFalse(self.ask(_Answer(error=TimeoutError())))
        self.assertFalse(self.ask(_Answer(500)))
        self.assertFalse(self.ask(_Answer(401)))

    def test_no_address_or_a_strange_one_is_not_locked_and_asks_nobody(self):
        for host in ("", "evil.example/path", "studio.example.vercel.app:8080", "a b"):
            answer = _Answer(302, SIGN_IN)
            with mock.patch.dict(os.environ, {"VERCEL_PROJECT_PRODUCTION_URL": host}):
                self.assertFalse(self.ask(answer), host)
            self.assertEqual(answer.requests, [], host)

    def test_it_asks_its_own_production_address_with_no_sign_in(self):
        answer = _Answer(302, SIGN_IN)
        self.ask(answer)
        (request,) = answer.requests
        self.assertEqual(request.full_url, "https://studio.example.vercel.app/")
        sent = {k.lower() for k, _ in request.header_items()}
        self.assertFalse(sent & {"cookie", "authorization"})

    def test_redirects_are_not_followed(self):
        handler = _lock._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, SIGN_IN))


class TheAnswerIsRememberedOnlyWhenLocked(unittest.TestCase):

    def setUp(self):
        studio_harness.restore_lock()
        self.calls = 0

    def tearDown(self):
        studio_harness.restore_lock()

    def counting(self, result):
        def check():
            self.calls += 1
            return result
        return check

    def test_locked_is_remembered_for_a_minute_then_asked_again(self):
        _lock.check_now = self.counting(True)
        with mock.patch.object(_lock.time, "monotonic", return_value=1000.0):
            self.assertTrue(_lock.is_locked())
            self.assertTrue(_lock.is_locked())
        self.assertEqual(self.calls, 1)
        with mock.patch.object(_lock.time, "monotonic", return_value=1000.0 + _lock.REMEMBER_SECONDS + 0.1):
            self.assertTrue(_lock.is_locked())
        self.assertEqual(self.calls, 2)
        self.assertLessEqual(_lock.REMEMBER_SECONDS, 60)

    def test_not_locked_is_asked_every_time(self):
        _lock.check_now = self.counting(False)
        self.assertFalse(_lock.is_locked())
        self.assertFalse(_lock.is_locked())
        self.assertEqual(self.calls, 2)


if __name__ == "__main__":
    unittest.main()
