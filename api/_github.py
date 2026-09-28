"""A small GitHub client for the Studio's server functions.

Standard library only. The key is the Vercel environment variable
GITHUB_TOKEN; it is read here, sent only to api.github.com, and never put
in an answer. When GitHub refuses, the Studio says so in a plain sentence
and GitHub's status, never with the key or the request's headers.
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
PATH_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")
SECRET_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,99}$")
WORKFLOW_RE = re.compile(r"^[A-Za-z0-9._-]+\.ya?ml$")
REF_RE = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")
TIMEOUT = 20


class GitHubError(Exception):
    """GitHub's status and a sentence an operator can act on."""

    def __init__(self, status, sentence):
        super().__init__(sentence)
        self.status = status
        self.sentence = sentence


def _token():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise GitHubError(500, "The Studio has no GitHub key. Add GITHUB_TOKEN in Vercel, then redeploy.")
    return token


def check_repo(repo):
    if not isinstance(repo, str) or not REPO_RE.match(repo) or ".." in repo:
        raise GitHubError(400, "That is not a repository name of the form owner/name.")
    return repo


def _check_path(path):
    if (not isinstance(path, str) or not PATH_RE.match(path)
            or any(part in (".", "..") for part in path.split("/"))):
        raise GitHubError(400, "That is not a file path inside a repository.")
    return path


def _refused(status, what, github_message):
    if status == 401:
        return "GitHub did not accept the Studio's key. It may have expired or been deleted; make a new one and put it in Vercel."
    if status == 403:
        return f"GitHub refused {what}: the key does not have permission for it."
    if status == 404:
        return f"GitHub found nothing at {what}, or the key cannot see it."
    if status in (409, 422) and github_message:
        return f"GitHub refused {what}: {github_message}"
    return f"GitHub answered {status} for {what}."


def _github_message(error):
    """GitHub's own one-line reason, if it gave one. It never contains the
    key, but it is cut short and kept to printable characters anyway."""
    try:
        message = json.loads(error.read().decode("utf-8")).get("message", "")
    except Exception:
        return ""
    message = "".join(c for c in str(message) if c.isprintable())
    return message[:200]


def request(method, path, what, body=None):
    """One call to the GitHub API. Returns the decoded JSON, or None when
    GitHub answers with no body."""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": f"Bearer {_token()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "curious-agent-studio",
        **({"Content-Type": "application/json"} if data is not None else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read()
    except urllib.error.HTTPError as e:
        raise GitHubError(e.code, _refused(e.code, what, _github_message(e))) from None
    except Exception:
        raise GitHubError(502, "The Studio could not reach GitHub. Try again in a minute.") from None
    return json.loads(raw) if raw else None


def whoami():
    """The login of the account the key belongs to."""
    return request("GET", "/user", "the key's own account")["login"]


def get_file(repo, path):
    """(text, sha) of a file, or (None, None) if it does not exist."""
    check_repo(repo)
    _check_path(path)
    try:
        body = request("GET", f"/repos/{repo}/contents/{urllib.parse.quote(path)}", f"{repo}/{path}")
    except GitHubError as e:
        if e.status == 404:
            return None, None
        raise
    return base64.b64decode(body["content"]).decode("utf-8"), body["sha"]


def put_file(repo, path, text, message, sha=None):
    """Create a file, or replace one whose current sha is given."""
    check_repo(repo)
    _check_path(path)
    body = {"message": str(message)[:200],
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii")}
    if sha:
        body["sha"] = sha
    return request("PUT", f"/repos/{repo}/contents/{urllib.parse.quote(path)}", f"{repo}/{path}", body)


def create_repo(name, private, description=""):
    """A new repository on the key's own account."""
    if not isinstance(name, str) or not NAME_RE.match(name) or name in (".", ".."):
        raise GitHubError(400, "That is not a repository name GitHub accepts.")
    body = {"name": name, "private": bool(private), "description": str(description)[:350],
            "auto_init": False}
    return request("POST", "/user/repos", f"a new repository called {name}", body)


def list_repos(limit=500):
    """The repositories the key's account owns, as {name, private}."""
    repos, page = [], 1
    while len(repos) < limit:
        batch = request("GET", f"/user/repos?affiliation=owner&per_page=100&page={page}",
                        "the list of your repositories")
        if not batch:
            break
        repos += [{"name": r["full_name"], "private": r["private"]} for r in batch]
        if len(batch) < 100:
            break
        page += 1
    return repos[:limit]


def get_secrets_key(repo):
    """The repository's public key for Actions secrets: {key_id, key}."""
    check_repo(repo)
    body = request("GET", f"/repos/{repo}/actions/secrets/public-key", f"{repo}'s secrets key")
    return {"key_id": body["key_id"], "key": body["key"]}


def put_secret(repo, name, encrypted_value, key_id):
    """Store a secret the browser has already sealed. The Studio cannot
    read it; it only passes it on."""
    check_repo(repo)
    if not SECRET_NAME_RE.match(name) or name.upper().startswith("GITHUB_"):
        raise GitHubError(400, "That is not a secret name GitHub accepts.")
    request("PUT", f"/repos/{repo}/actions/secrets/{name}", f"the secret {name} in {repo}",
            {"encrypted_value": encrypted_value, "key_id": key_id})


def dispatch_workflow(repo, workflow, ref="main", inputs=None):
    """Start a workflow that has a workflow_dispatch trigger."""
    check_repo(repo)
    if not WORKFLOW_RE.match(workflow) or not REF_RE.match(ref):
        raise GitHubError(400, "That is not a workflow file name.")
    body = {"ref": ref}
    if inputs:
        body["inputs"] = {str(k): str(v) for k, v in inputs.items()}
    request("POST", f"/repos/{repo}/actions/workflows/{workflow}/dispatches",
            f"the {workflow} workflow in {repo}", body)
