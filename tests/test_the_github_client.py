"""The Studio's GitHub client: the key goes only to GitHub, names are
checked before they are used, and a refusal is a plain sentence."""

import base64
import io
import json
import os
import unittest
import urllib.error
from unittest import mock

import studio_harness  # noqa: F401  (puts api/ on the path)
import _github

TOKEN = "github_pat_NEVER_SHOWN_1234567890"


class _Response:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode() if payload is not None else b""

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _refusal(code, message=""):
    body = json.dumps({"message": message}).encode()
    return urllib.error.HTTPError("https://api.github.com/x", code, "No", {}, io.BytesIO(body))


class TheClient(unittest.TestCase):

    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"GITHUB_TOKEN": TOKEN})
        self.env.start()
        self.requests = []

    def tearDown(self):
        self.env.stop()

    def github(self, answer):
        def urlopen(request, timeout=None):
            self.requests.append(request)
            if isinstance(answer, Exception):
                raise answer
            return _Response(answer)
        return mock.patch.object(_github.urllib.request, "urlopen", urlopen)

    def test_the_key_goes_to_githubs_api_and_nowhere_else(self):
        with self.github({"login": "an-operator"}):
            self.assertEqual(_github.whoami(), "an-operator")
        (request,) = self.requests
        self.assertTrue(request.full_url.startswith("https://api.github.com/"))
        self.assertEqual(request.get_header("Authorization"), f"Bearer {TOKEN}")

    def test_a_refusal_is_a_sentence_without_the_key(self):
        for code in (401, 403, 404, 409, 422, 500):
            with self.github(_refusal(code, "name already exists on this account")):
                with self.assertRaises(_github.GitHubError) as caught:
                    _github.get_secrets_key("someone/runner")
            self.assertEqual(caught.exception.status, code)
            self.assertNotIn(TOKEN, caught.exception.sentence)
            self.assertNotIn("Bearer", caught.exception.sentence)
        with self.github(_refusal(422, "name already exists on this account")):
            with self.assertRaises(_github.GitHubError) as caught:
                _github.create_repo("my-agent", private=False)
        self.assertIn("name already exists", caught.exception.sentence)

    def test_github_out_of_reach_is_a_sentence(self):
        with self.github(urllib.error.URLError("no route")):
            with self.assertRaises(_github.GitHubError) as caught:
                _github.whoami()
        self.assertEqual(caught.exception.status, 502)
        self.assertIn("could not reach GitHub", caught.exception.sentence)

    def test_no_key_is_said_plainly(self):
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": ""}), self.github({"login": "x"}):
            with self.assertRaises(_github.GitHubError) as caught:
                _github.whoami()
        self.assertIn("GITHUB_TOKEN", caught.exception.sentence)
        self.assertEqual(self.requests, [])

    def test_names_are_checked_before_anything_is_sent(self):
        with self.github({}):
            for repo in ("../x", "a/b/c", "a b/c", "someone/..", "", None, "someone/runner?x=1"):
                with self.assertRaises(_github.GitHubError, msg=repo):
                    _github.get_secrets_key(repo)
            for path in ("../x", "/etc/passwd", "a/../b", "a//b", "a/./b", ""):
                with self.assertRaises(_github.GitHubError, msg=path):
                    _github.get_file("someone/runner", path)
            for name in ("GITHUB_TOKEN", "github_x", "1ABC", "A-B", ""):
                with self.assertRaises(_github.GitHubError, msg=name):
                    _github.put_secret("someone/runner", name, "x", "1")
            for workflow in ("../x.yml", "run.sh", "a/b.yml"):
                with self.assertRaises(_github.GitHubError, msg=workflow):
                    _github.dispatch_workflow("someone/runner", workflow)
            for name in ("a/b", "..", "", "x" * 101):
                with self.assertRaises(_github.GitHubError, msg=name):
                    _github.create_repo(name, private=True)
        self.assertEqual(self.requests, [])

    def test_a_file_is_read_and_written_with_its_sha(self):
        content = base64.b64encode("Agent name: Test\n".encode()).decode()
        with self.github({"content": content, "sha": "abc123"}):
            self.assertEqual(_github.get_file("someone/runner", "agent_profile.md"),
                             ("Agent name: Test\n", "abc123"))
        with self.github({"content": {}}):
            _github.put_file("someone/runner", "agent_profile.md", "Agent name: New\n", "Setup", sha="abc123")
        sent = json.loads(self.requests[-1].data)
        self.assertEqual(sent["sha"], "abc123")
        self.assertEqual(base64.b64decode(sent["content"]).decode(), "Agent name: New\n")
        self.assertEqual(self.requests[-1].get_method(), "PUT")

    def test_a_missing_file_is_none(self):
        with self.github(_refusal(404)):
            self.assertEqual(_github.get_file("someone/runner", "nothing.md"), (None, None))

    def test_repositories_are_listed_across_pages(self):
        pages = [[{"full_name": f"someone/r{i}", "private": i % 2 == 0} for i in range(100)],
                 [{"full_name": "someone/last", "private": True}]]

        def urlopen(request, timeout=None):
            self.requests.append(request)
            return _Response(pages[len(self.requests) - 1])
        with mock.patch.object(_github.urllib.request, "urlopen", urlopen):
            repos = _github.list_repos()
        self.assertEqual(len(repos), 101)
        self.assertEqual(repos[-1], {"name": "someone/last", "private": True})

    def test_a_workflow_is_started_on_a_branch(self):
        with self.github(None):
            _github.dispatch_workflow("someone/runner", "agent.yml", inputs={"dress_rehearsal": True})
        request = self.requests[-1]
        self.assertTrue(request.full_url.endswith("/repos/someone/runner/actions/workflows/agent.yml/dispatches"))
        self.assertEqual(json.loads(request.data), {"ref": "main", "inputs": {"dress_rehearsal": "True"}})


if __name__ == "__main__":
    unittest.main()
