"""Unlocked, every server function answers 423 and `{"locked": false}`,
and nothing else: no agent, no repository, nothing from the key. Locked,
they answer in JSON, uncached, and log nothing about a request."""

import base64
import contextlib
import io
import json
import os
import unittest
from unittest import mock

import studio_harness
from studio_harness import _github, _studio, call

TOKEN = "github_pat_NEVER_SHOWN_1234567890"
SEALED = base64.b64encode(b"x" * 61).decode()
JSON_POST = {"X-Studio": "1", "Content-Type": "application/json"}


def _no_github(*args, **kwargs):
    raise AssertionError("GitHub was asked while the Studio was not locked")


class Unlocked(unittest.TestCase):

    def setUp(self):
        studio_harness.set_locked(False)

    def tearDown(self):
        studio_harness.restore_lock()

    def test_there_are_functions_and_each_is_a_studio_handler(self):
        names = studio_harness.function_names()
        self.assertIn("status", names)
        for name in names:
            self.assertTrue(issubclass(studio_harness.load(name).handler, _studio.StudioHandler), name)

    def test_every_function_says_only_not_locked(self):
        body = json.dumps({"repo": "someone/runner", "name": "LLM_API_KEY",
                           "key_id": "1", "encrypted_value": SEALED}).encode()
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": TOKEN}), \
                mock.patch.object(_github, "request", _no_github):
            for name in studio_harness.function_names():
                for method, kwargs in (("GET", {"path": f"/api/{name}?repo=someone/runner"}),
                                       ("POST", {"body": body, "headers": JSON_POST})):
                    status, headers, text = call(name, method, **kwargs)
                    self.assertEqual(status, 423, (name, method))
                    self.assertEqual(text, '{"locked": false}', (name, method))
                    self.assertEqual(headers["Cache-Control"], "no-store")


class Locked(unittest.TestCase):

    def setUp(self):
        studio_harness.set_locked(True)
        self.env = mock.patch.dict(os.environ, {"GITHUB_TOKEN": TOKEN})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        studio_harness.restore_lock()

    def test_status_names_the_keys_account(self):
        with mock.patch.object(_github, "request", return_value={"login": "an-operator"}):
            status, headers, text = call("status")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(text), {"locked": True, "github": {"ok": True, "login": "an-operator"}})
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_status_says_why_the_key_did_not_work_without_the_key(self):
        refused = _github.GitHubError(401, _github._refused(401, "x", ""))
        with mock.patch.object(_github, "request", side_effect=refused):
            status, _, text = call("status")
        self.assertEqual(status, 200)
        body = json.loads(text)
        self.assertFalse(body["github"]["ok"])
        self.assertIn("did not accept", body["github"]["error"])
        self.assertNotIn(TOKEN, text)

    def test_an_unexpected_failure_says_nothing_about_itself(self):
        with mock.patch.object(_github, "request", side_effect=RuntimeError(TOKEN)):
            status, _, text = call("secret_key", path="/api/secret_key?repo=someone/runner")
        self.assertEqual(status, 500)
        self.assertNotIn(TOKEN, text)
        self.assertNotIn("RuntimeError", text)

    def test_a_github_refusal_keeps_githubs_status(self):
        with mock.patch.object(_github, "request", side_effect=_github.GitHubError(404, "Not there.")):
            status, _, text = call("secret_key", path="/api/secret_key?repo=someone/runner")
        self.assertEqual((status, json.loads(text)), (404, {"error": "Not there."}))

    def test_nothing_about_a_request_is_logged(self):
        stderr, stdout = io.StringIO(), io.StringIO()
        body = json.dumps({"repo": "someone/runner", "name": "LLM_API_KEY",
                           "key_id": "1", "encrypted_value": SEALED}).encode()
        with contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout), \
                mock.patch.object(_github, "request", return_value=None):
            call("secret", "POST", body=body, headers=JSON_POST)
            call("status", path="/api/status?repo=someone/runner")
        self.assertEqual(stderr.getvalue() + stdout.getvalue(), "")

    def test_a_function_without_that_method_says_so(self):
        status, _, text = call("status", "POST", body=b"{}", headers=JSON_POST)
        self.assertEqual(status, 405)
        self.assertIn("error", json.loads(text))


class ASecretIsOnlyPassedOn(unittest.TestCase):

    def setUp(self):
        studio_harness.set_locked(True)
        self.env = mock.patch.dict(os.environ, {"GITHUB_TOKEN": TOKEN})
        self.env.start()
        self.sent = []
        self.patch = mock.patch.object(_github, "request",
                                       side_effect=lambda *a, **k: self.sent.append((a, k)))
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.env.stop()
        studio_harness.restore_lock()

    def post(self, payload, headers=JSON_POST):
        return call("secret", "POST", body=json.dumps(payload).encode(), headers=headers)

    def good(self, **change):
        payload = {"repo": "someone/runner", "name": "LLM_API_KEY", "key_id": "568250167242549743",
                   "encrypted_value": SEALED}
        payload.update(change)
        return payload

    def test_a_sealed_secret_is_forwarded_as_it_came(self):
        status, _, text = self.post(self.good())
        self.assertEqual((status, json.loads(text)), (200, {"set": "LLM_API_KEY"}))
        ((args, kwargs),) = self.sent
        method, path, _what, body = args
        self.assertEqual((method, path), ("PUT", "/repos/someone/runner/actions/secrets/LLM_API_KEY"))
        self.assertEqual(body, {"encrypted_value": SEALED, "key_id": "568250167242549743"})

    def test_only_setups_secrets(self):
        for name in ("GITHUB_TOKEN", "ANYTHING", "", None):
            status, _, _ = self.post(self.good(name=name))
            self.assertEqual(status, 400, name)
        self.assertEqual(self.sent, [])

    def test_an_unsealed_value_is_refused(self):
        for value in ("sk-plain-api-key", "", base64.b64encode(b"short").decode(), 12, None, "a" * 9000):
            status, _, _ = self.post(self.good(encrypted_value=value))
            self.assertEqual(status, 400, value)
        self.assertEqual(self.sent, [])

    def test_a_bad_key_id_or_repository_is_refused(self):
        self.assertEqual(self.post(self.good(key_id="../x"))[0], 400)
        self.assertEqual(self.post(self.good(repo="../../user"))[0], 400)
        self.assertEqual(self.sent, [])

    def test_a_post_from_anywhere_but_the_page_is_refused(self):
        for headers in ({"Content-Type": "application/json"},
                        {"X-Studio": "1", "Content-Type": "text/plain"},
                        {"X-Studio": "1", "Content-Type": "application/x-www-form-urlencoded"}):
            status, _, _ = self.post(self.good(), headers=headers)
            self.assertEqual(status, 400, headers)
        self.assertEqual(self.sent, [])

    def test_a_body_that_is_not_an_object_or_too_large_is_refused(self):
        self.assertEqual(call("secret", "POST", body=b"[1]", headers=JSON_POST)[0], 400)
        self.assertEqual(call("secret", "POST", body=b"not json", headers=JSON_POST)[0], 400)
        big = {**JSON_POST, "Content-Length": str(_studio.MAX_BODY + 1)}
        self.assertEqual(call("secret", "POST", body=b"{}", headers=big)[0], 400)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
