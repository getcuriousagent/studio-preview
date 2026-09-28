// Curious Agent Studio's page. Everything it shows comes from the Studio's
// own server functions, and anything an agent wrote is set as text, never
// as HTML.
"use strict";

const Studio = (() => {
  const REAUTH = "studio-signing-in-again";
  const CHECKED_AGAIN = "studio-checked-again";
  const HOME_SCREEN_DISMISSED = "studio-home-screen-dismissed";

  const $ = (id) => document.getElementById(id);
  const session = {
    get: (k) => { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set: (k, v) => { try { sessionStorage.setItem(k, v); } catch (e) { /* private mode */ } },
    del: (k) => { try { sessionStorage.removeItem(k); } catch (e) { /* private mode */ } },
  };

  // Thrown after the page has taken over the screen (not locked, or signing
  // in again), so whatever asked stops quietly.
  class Stopped extends Error {}

  function show(id) {
    for (const s of ["checking", "private", "signin", "ready"]) $(s).hidden = s !== id;
  }

  function showPrivate() {
    show("private");
    if (session.get(CHECKED_AGAIN)) $("still-open").hidden = false;
    session.del(CHECKED_AGAIN);
  }

  // A call that is redirected, or fails outright, means Vercel's sign-in
  // pass has lapsed (or the page was loaded before the lock). Reloading
  // signs in again; once only, so a real failure does not loop.
  function signInAgain() {
    show("signin");
    if (navigator.onLine === false) {
      $("signin-text").textContent = "You seem to be offline. Reload this page when you are connected.";
      return;
    }
    if (session.get(REAUTH)) {
      session.del(REAUTH);
      $("signin-text").textContent = "Please sign in to Vercel, then reload this page.";
      return;
    }
    session.set(REAUTH, "1");
    $("signin-text").textContent = "Signing you in again…";
    location.reload();
  }

  async function api(path, options = {}) {
    let response;
    try {
      response = await fetch(path, {
        cache: "no-store", credentials: "same-origin", redirect: "manual", ...options,
        headers: { "X-Studio": "1", ...(options.headers || {}) },
      });
    } catch (e) {
      signInAgain();
      throw new Stopped();
    }
    const json = (response.headers.get("Content-Type") || "").startsWith("application/json");
    if (response.type === "opaqueredirect" || response.status === 0 || !json) {
      signInAgain();
      throw new Stopped();
    }
    const body = await response.json().catch(() => ({}));
    if (response.status === 423 || body.locked === false) {
      showPrivate();
      throw new Stopped();
    }
    session.del(REAUTH);
    return { ok: response.ok, status: response.status, body };
  }

  // libsodium is loaded only when a secret is about to be set.
  let sodium = null;
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("Could not load " + src));
      document.head.append(s);
    });
  }
  function loadSodium() {
    if (!sodium) {
      sodium = loadScript("/vendor/libsodium.js")
        .then(() => loadScript("/vendor/libsodium-wrappers.js"))
        .then(() => window.sodium.ready)
        .then(() => window.sodium);
    }
    return sodium;
  }

  // Seal a secret with the repository's public key, as `gh secret set`
  // does, and send only the sealed value. The readable value never leaves
  // this page.
  async function setSecret(repo, name, value) {
    const key = await api("/api/secret_key?repo=" + encodeURIComponent(repo));
    if (!key.ok) return key;
    const na = await loadSodium();
    const b64 = na.base64_variants.ORIGINAL;
    const sealed = na.crypto_box_seal(na.from_string(value), na.from_base64(key.body.key, b64));
    return api("/api/secret", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo, name, key_id: key.body.key_id, encrypted_value: na.to_base64(sealed, b64) }),
    });
  }

  // Add to Home Screen. iPhone Safari has no prompt of its own, so it gets
  // a note; Android offers one, which gets a button.
  let installPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    installPrompt = e;
    if (!$("ready").hidden) $("install").hidden = false;
  });

  function offerHomeScreen() {
    const iPhone = navigator.standalone === false && navigator.maxTouchPoints > 1;
    let dismissed = false;
    try { dismissed = localStorage.getItem(HOME_SCREEN_DISMISSED) === "1"; } catch (e) { /* private mode */ }
    if (iPhone && !dismissed) $("home-screen").hidden = false;
    if (installPrompt) $("install").hidden = false;
  }

  async function start() {
    $("check-again").addEventListener("click", () => {
      session.set(CHECKED_AGAIN, "1");
      location.reload();
    });
    $("home-screen-close").addEventListener("click", () => {
      $("home-screen").hidden = true;
      try { localStorage.setItem(HOME_SCREEN_DISMISSED, "1"); } catch (e) { /* private mode */ }
    });
    $("install-button").addEventListener("click", async () => {
      if (!installPrompt) return;
      installPrompt.prompt();
      await installPrompt.userChoice.catch(() => null);
      installPrompt = null;
      $("install").hidden = true;
    });

    let status;
    try {
      status = await api("/api/status");
    } catch (e) {
      if (e instanceof Stopped) return;
      throw e;
    }
    session.del(CHECKED_AGAIN);
    const line = $("github-line");
    if (status.ok && status.body.github && status.body.github.ok) {
      line.textContent = "Its GitHub key belongs to " + status.body.github.login + ".";
    } else {
      line.className = "warn";
      line.textContent = (status.body.github && status.body.github.error) || status.body.error || "The Studio could not check its GitHub key.";
    }
    show("ready");
    offerHomeScreen();
  }

  document.addEventListener("DOMContentLoaded", start);
  return { api, setSecret, Stopped };
})();
