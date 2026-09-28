# Curious Agent Studio

The operator's interface to Curious Agent: setup, adding agents, settings,
instructions, extensions and statistics, in one place, at one address.
Each operator runs their own copy on Vercel's free plan, and only they can
open it: Vercel's own sign-in is the lock. The design is in the working
record, `engineering_context/proposals/30-operator-dashboard.md` and
`31-dashboard-first-install.md`; the build is
`briefs/2026-09-28-studio-setup.md`.

**What is here now is the foundation.** The Studio checks it is locked,
knows its GitHub key, and can seal a secret in the browser. Setting up an
agent comes next.

## Keeping it private

A new Vercel project is **not** locked: its production address answers
anyone. So the Studio checks for itself, before every server function does
anything. It asks its own production address for the page with no sign-in;
a locked Studio sends that request to Vercel's sign-in. Anything else, an
error included, counts as open, and then:

- every server function answers `423` and `{"locked": false}`, and nothing
  else;
- the page shows only **Keep your agent private**, with the four clicks that
  lock it in Vercel (Settings → Deployment Protection → Vercel
  Authentication → Require Log In, **All Deployments** → Save), and
  **Check again**.

A locked answer is remembered for a minute at most, so a Studio switched
back to Standard Protection closes itself again within that minute.

When Vercel's sign-in lapses, the page's calls are sent to the sign-in and
fail. The page reloads once ("Signing you in again…"), which signs in again;
if that fails too, it asks you to sign in to Vercel and reload.

## The GitHub key

`GITHUB_TOKEN`, a Vercel environment variable: the one value asked for when
the Studio is deployed. Only the server functions read it; it is sent only
to GitHub and never to the browser, and no answer ever contains it.

Setup will need a fine-grained key on **All repositories** (the agent's
repositories do not exist yet), with, **to be confirmed when setup is
built**: Administration, Contents, Secrets, Actions, Workflows and Pages,
read and write; Metadata, read-only.

## Secrets are sealed in the browser

An agent's secrets (its model key, its mail password) are sealed in the
page with the repository's public key, exactly as `gh secret set` does,
using libsodium from `vendor/`. The Studio's server passes on what it
cannot read, and only the four secrets setup asks for. Nothing the Studio
runs logs a request.

## Files

| File | What it does |
| :--- | :--- |
| `index.html`, `studio.css`, `studio.js` | The page. It checks, then shows either the lock screen or the Studio |
| `api/status.py` | Is the Studio locked, and whose is its GitHub key |
| `api/secret_key.py`, `api/secret.py` | A repository's public key; store a secret the page has sealed |
| `api/_lock.py` | The lock check every function makes first |
| `api/_studio.py` | What every function shares: the lock, JSON, no caching, no logging |
| `api/_github.py` | The GitHub client, standard library only |
| `vendor/` | libsodium, kept here so the Studio loads nothing from elsewhere (its `README.md` has the hashes) |
| `vercel.json` | The security policy for every page, and what the functions leave out |
| `manifest.webmanifest`, `apple-touch-icon.png`, `icon-512.png` | The home-screen icon and name |
| `tests/` | `python3 -m unittest discover -s studio/tests` |

A file in `api/` whose name starts with `_` is shared code; Vercel does
not serve it as a function of its own.

**The security policy** allows scripts, styles, images and calls from the
Studio itself only, plus `'wasm-unsafe-eval'`, which lets libsodium compile
its WebAssembly and allows no `eval`. Nothing an agent wrote is ever put
into the page as HTML.

## Trying it before launch

Vercel's Deploy link copies only a public repository, so until launch it
points at the public mirror, `getcuriousagent/studio-preview`:

https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Fgetcuriousagent%2Fstudio-preview&env=GITHUB_TOKEN&envDescription=Your%20GitHub%20key&project-name=curious-agent-studio&repository-name=curious-agent-studio

A Studio made this way does not update itself yet: a change here is also
copied into the mirror and into the operator's own copy, and pushed.
