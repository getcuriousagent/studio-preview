"""The page loads nothing from anyone else, runs no inline script, never
writes HTML from data, says "Keep your agent private" as written, and the
vendored library is the one recorded."""

import hashlib
import json
import os
import re
import unittest

from studio_harness import STUDIO


def _read(name):
    with open(os.path.join(STUDIO, name), encoding="utf-8") as f:
        return f.read()


def _policy():
    config = json.loads(_read("vercel.json"))
    for rule in config["headers"]:
        if rule["source"] == "/(.*)":
            for header in rule["headers"]:
                if header["key"] == "Content-Security-Policy":
                    return dict((d.split(" ", 1) + [""])[:2] for d in
                                (p.strip() for p in header["value"].split(";")) if d)
    raise AssertionError("no Content-Security-Policy for every page")


class ThePolicy(unittest.TestCase):

    def test_scripts_and_everything_else_come_from_the_studio_only(self):
        policy = _policy()
        self.assertEqual(policy["default-src"], "'self'")
        self.assertEqual(policy["script-src"], "'self' 'wasm-unsafe-eval'")
        self.assertEqual(policy["style-src"], "'self'")
        self.assertEqual(policy["connect-src"], "'self'")
        self.assertEqual(policy["img-src"], "'self' data:")
        self.assertEqual(policy["frame-ancestors"], "'none'")
        joined = " ".join(policy.values())
        self.assertNotIn("'unsafe-eval'", joined)
        self.assertNotIn("'unsafe-inline'", joined)
        self.assertNotIn("http", joined)

    def test_the_page_itself_is_never_cached(self):
        config = json.loads(_read("vercel.json"))
        sources = {r["source"] for r in config["headers"]
                   if {"key": "Cache-Control", "value": "no-store"} in r["headers"]}
        self.assertTrue({"/", "/index.html"} <= sources)


class ThePage(unittest.TestCase):

    def setUp(self):
        self.html = _read("index.html")
        self.js = _read("studio.js")

    def test_no_inline_script_or_style_and_nothing_from_elsewhere(self):
        for tag in re.findall(r"<script[^>]*>", self.html):
            self.assertRegex(tag, r'src="/[^/]')
        self.assertNotIn("<style", self.html)
        self.assertNotRegex(self.html, r"\sstyle=")
        self.assertNotRegex(self.html, r"\son[a-z]+=")
        self.assertNotRegex(self.html + _read("studio.css"), r"(src|href)=\"https?:|url\(\s*['\"]?https?:")

    def test_nothing_is_written_as_html(self):
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            self.assertNotIn(sink, self.js, sink)

    def test_keep_your_agent_private_is_as_written(self):
        text = re.sub(r"<[^>]+>", "", self.html)
        text = re.sub(r"\s+", " ", text)
        for line in (
            "Keep your agent private",
            "Your Studio is open to anyone who has its address. Lock it so only you can open it:",
            "In Vercel, open your project's Settings.",
            "Choose Deployment Protection.",
            "Under Vercel Authentication, turn on Require Log In and choose All Deployments.",
            "Click Save, then come back here.",
            "Check again",
        ):
            self.assertIn(line, text)

    def test_it_starts_by_checking_and_shows_nothing_else(self):
        visible = re.findall(r'<section id="([a-z-]+)"(?![^>]*hidden)', self.html)
        self.assertEqual(visible, ["checking"])

    def test_the_icons_are_inside_the_page(self):
        self.assertRegex(self.html, r'<link rel="apple-touch-icon" href="data:image/png;base64,')
        self.assertIn('<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">', self.html)


class TheVendoredLibrary(unittest.TestCase):

    def test_the_files_are_the_ones_recorded(self):
        readme = _read("vendor/README.md")
        for name in ("libsodium.js", "libsodium-wrappers.js"):
            with open(os.path.join(STUDIO, "vendor", name), "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            self.assertIn(f"`{name}` | npm", readme)
            self.assertIn(digest, readme, name)


if __name__ == "__main__":
    unittest.main()
