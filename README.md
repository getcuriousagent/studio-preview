# Curious Agent Studio — preview

A preview of Curious Agent Studio, used to test its setup on Vercel before
Curious Agent's public release. It is one page and two small server
functions. It reads a few settings from one agent's profile through GitHub,
using a read-only key held as a Vercel secret, and changes nothing.

Curious Agent is free and open source. Its public release, and the Studio
itself, are not out yet; this repository will be retired when they are.

| File | What it does |
| :--- | :--- |
| `index.html` | Shows four settings, and buttons that measure how long one request may run |
| `api/profile.py` | Reads `agent_profile.md` from the repository in `AGENT_RUNNER_REPO`, with the key in `GITHUB_TOKEN` |
| `api/wait.py` | Waits the number of seconds asked, up to 900 |
| `manifest.webmanifest`, `apple-touch-icon.png` | Let a phone add it to the home screen |
