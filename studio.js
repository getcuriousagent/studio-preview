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
    if (response.type === "opaqueredirect" || response.status === 0 || (!json && response.status < 400)) {
      signInAgain();
      throw new Stopped();
    }
    // Vercel's own failures (a function that crashed, or ran past its time)
    // are not JSON. They are not a lapsed sign-in, and reloading would lose
    // the page's work, so say what happened instead.
    if (!json) {
      return { ok: false, status: response.status,
        body: { error: "The Studio's server did not answer properly (" + response.status + "). Try again in a minute." } };
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
        .then(() => window.sodium)
        .catch((e) => { sodium = null; throw e; });  // try again next time
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
  // a note; Chrome, Brave and Edge offer one, which gets a button. On a
  // computer, installing gives the Studio its own window rather than a
  // home-screen icon, and the button says so.
  const COMPUTER_INSTALL = "Keep your Studio in its own window, with an icon in your Dock or taskbar.";
  const onPhone = () => Boolean((navigator.userAgentData && navigator.userAgentData.mobile)
    || matchMedia("(pointer: coarse)").matches);
  let installPrompt = null;
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    installPrompt = e;
    if (!$("ready").hidden) $("install").hidden = false;
  });

  // Which system the page is on, for the install and bookmark steps.
  function system() {
    const p = ((navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || "").toLowerCase();
    const ua = navigator.userAgent.toLowerCase();
    if (ua.includes("android")) return "android";
    if (/iphone|ipad|ipod/.test(ua) || (p.includes("mac") && navigator.maxTouchPoints > 1)) return "ios";
    if (p.includes("mac")) return "mac";
    if (p.includes("win")) return "windows";
    if (p.includes("cros") || p.includes("chrome os") || ua.includes("cros")) return "chromeos";
    return "other";
  }
  const INSTALLED = {
    mac: "Find it in Launchpad or your Applications folder. To keep it in your Dock: while it is open, right-click its icon in the Dock, then choose Options, then Keep in Dock.",
    windows: "Find it in the Start menu. To keep it on your taskbar: while it is open, right-click its icon on the taskbar, then choose Pin to taskbar.",
    chromeos: "Find it in your launcher. To keep it on your shelf: while it is open, right-click its icon on the shelf, then choose Pin.",
    android: "It is on your home screen and with your other apps.",
    other: "Find it with your other applications.",
  };
  const BOOKMARK = {
    mac: "To bookmark it, press ⌘D.",
    windows: "To bookmark it, press Ctrl+D.",
    chromeos: "To bookmark it, press Ctrl+D.",
    other: "To bookmark it, press Ctrl+D.",
    android: "To keep it on your home screen, use your browser's menu: Add to Home screen.",
    ios: "To keep it on your home screen, tap Share, then Add to Home Screen.",
  };
  const inApp = () => matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

  window.addEventListener("appinstalled", () => {
    installPrompt = null;
    $("install").hidden = true;
    $("installed-text").textContent = INSTALLED[system()] || INSTALLED.other;
    $("installed").hidden = false;
  });

  // How to get back here, always shown once the Studio is open: the page
  // cannot tell whether it was installed earlier, or on another device.
  function describeOpening() {
    $("opening-address").textContent = location.host;
    if (inApp()) {
      $("opening-text").textContent = "This is your Studio's app. It also opens in any browser, at:";
      $("opening-hint").textContent = "";
    } else {
      $("opening-text").textContent = "From its app icon, if you installed it, or in any browser at:";
      $("opening-hint").textContent = BOOKMARK[system()] || BOOKMARK.other;
    }
    if (!(navigator.clipboard && navigator.clipboard.writeText)) $("opening-copy").hidden = true;
    $("opening").hidden = false;
  }

  function offerHomeScreen() {
    const iPhone = navigator.standalone === false && navigator.maxTouchPoints > 1;
    let dismissed = false;
    try { dismissed = localStorage.getItem(HOME_SCREEN_DISMISSED) === "1"; } catch (e) { /* private mode */ }
    if (iPhone && !dismissed) $("home-screen").hidden = false;
    if (!onPhone()) $("install-text").textContent = COMPUTER_INSTALL;
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
    $("installed-close").addEventListener("click", () => { $("installed").hidden = true; });
    $("opening-copy").addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(location.origin);
        $("opening-copy").textContent = "Copied";
      } catch (e) {
        $("opening-copy").textContent = "Could not copy";
      }
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
    describeOpening();
  }

  document.addEventListener("DOMContentLoaded", start);
  return { api, setSecret, Stopped };
})();
