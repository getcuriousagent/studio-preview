# vendor

libsodium, which seals each secret in the browser before it is sent. It is
kept here rather than loaded from a CDN, so the Studio fetches nothing
executable from anyone else, and its security policy allows scripts from
itself only. The page loads it only when a secret is about to be set.

| File | From | sha256 |
| :--- | :--- | :--- |
| `libsodium.js` | npm `libsodium@0.8.4`, `dist/modules/libsodium.js` | `9d9731995989ac2d7c73ba4fb6717e43cd2a4a4299c442b710c2d9e5065b14d1` |
| `libsodium-wrappers.js` | npm `libsodium-wrappers@0.8.4`, `dist/modules/libsodium-wrappers.js` | `d015a93315140974698318d94274ff63c6d22530d8b0e3f3770d9bfeadc7eb60` |
| `LICENSE` | the same in both packages (ISC) | |

Both files are copied unchanged. `npm pack` checked each package against
the registry's integrity hash when it was fetched (2026-09-28). The library
runs as WebAssembly, which is why the policy allows `'wasm-unsafe-eval'`:
that permits compiling WebAssembly and nothing else, not `eval`.

To update: `npm pack libsodium@<v> libsodium-wrappers@<v>` into a scratch
folder, copy the same two files, and replace the hashes above;
`tests/test_the_page.py` checks them.
