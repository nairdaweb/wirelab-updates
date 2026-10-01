import datetime as dt
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import build  # noqa: E402
import bump  # noqa: E402
import catalog  # noqa: E402

CATALOG = """schema: 1
site: https://updates.example.test
products:
  - id: pub  # public plugin
    name:
      pl: Publiczny
      en: Public
    summary:
      pl: Opis
      en: Summary
    type: nodebb-plugin
    channel: stable
    status: released
    visibility: public
    source: npm
    npm: nodebb-plugin-pub
    repo: owner/nodebb-plugin-pub
  - id: priv
    name:
      pl: Prywatny
      en: Private
    type: nodebb-plugin
    channel: stable
    status: released
    visibility: private
    source: manual
    version: "1.1.0"   # bump.py edits this
    date: "2026-10-01"
  - id: later
    name:
      pl: Potem
      en: Later
    type: android-apk
    channel: stable
    status: planned
    visibility: public
    source: none
"""

NPM = {
    "dist-tags": {"latest": "1.2.0"},
    "versions": {"1.0.0": {}, "1.1.0": {}, "1.2.0": {"nbbpm": {"compatibility": "^4.15.0"}}, "2.0.0-beta.1": {}},
    "time": {"1.0.0": "2026-09-01T10:00:00.000Z", "1.1.0": "2026-09-15T10:00:00.000Z", "1.2.0": "2026-10-01T10:00:00.000Z"},
}
CHANGELOG = """# Changelog

## [1.2.0] - 2026-10-01

### Added
- Update notices with `code` and a [link](https://example.test/x)
  continued on a second line.
- <script>alert(1)</script>

## 1.1.0
Plain paragraph.
"""


def fake_get(url, accept="application/json"):
    if url.startswith("https://registry.npmjs.org/"):
        assert url.endswith("/nodebb-plugin-pub"), url
        return json.dumps(NPM)
    if url == "https://raw.githubusercontent.com/owner/nodebb-plugin-pub/main/CHANGELOG.md":
        return CHANGELOG
    raise AssertionError("unexpected fetch: " + url)


class YamlSubset(unittest.TestCase):
    def test_parses_nested_blocks_and_scalars(self):
        data = catalog.parse_yaml(CATALOG)
        self.assertEqual(data["schema"], 1)
        self.assertEqual(data["products"][0]["name"], {"pl": "Publiczny", "en": "Public"})
        self.assertEqual(data["products"][1]["version"], "1.1.0")
        self.assertEqual(data["products"][0]["id"], "pub")

    def test_matches_pyyaml_on_products_yml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        with open(os.path.join(ROOT, "products.yml"), encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(catalog.parse_yaml(text), yaml.safe_load(text))

    def test_rejects_unsupported_syntax(self):
        for bad in ("a: [1, 2]\n", "a:\n\tb: 1\n", "a: 1\na: 2\n", "a: 1\n   b: 2\n", "just text\n"):
            with self.assertRaises(catalog.CatalogError, msg=bad):
                catalog.parse_yaml(bad)

    def test_validation(self):
        site, products = catalog.validate(catalog.parse_yaml(CATALOG))
        self.assertEqual(site, "https://updates.example.test")
        self.assertEqual([p["id"] for p in products], ["pub", "priv", "later"])
        bad = CATALOG.replace("    source: manual\n", "    source: npm\n")
        with self.assertRaises(catalog.CatalogError):
            catalog.validate(catalog.parse_yaml(bad))
        unquoted = CATALOG.replace('version: "1.1.0"', "version: 1")
        with self.assertRaises(catalog.CatalogError):
            catalog.validate(catalog.parse_yaml(unquoted))

    def test_real_catalog_is_valid(self):
        catalog.load(os.path.join(ROOT, "products.yml"))


class Semver(unittest.TestCase):
    def test_order(self):
        versions = ["1.10.0", "1.2.0", "1.2.0-beta.2", "1.2.0-beta.10", "1.2.0-alpha", "0.9.9"]
        self.assertEqual(sorted(versions, key=catalog.semver_key),
                         ["0.9.9", "1.2.0-alpha", "1.2.0-beta.2", "1.2.0-beta.10", "1.2.0", "1.10.0"])

    def test_min_from_range(self):
        self.assertEqual(catalog.min_from_range("^4.15.0"), "4.15.0")
        self.assertEqual(catalog.min_from_range(">=4.x"), "4.0.0")
        self.assertIsNone(catalog.min_from_range(None))


class Notes(unittest.TestCase):
    def test_changelog_sections(self):
        notes = build.parse_changelog(CHANGELOG)
        self.assertEqual(notes["1.2.0"]["date"], "2026-10-01")
        self.assertIn("### Added", notes["1.2.0"]["md"])
        self.assertEqual(notes["1.1.0"], {"date": None, "md": "Plain paragraph."})

    def test_markdown_is_escaped(self):
        out = build.render_md(build.parse_changelog(CHANGELOG)["1.2.0"]["md"])
        self.assertIn("<h4>Added</h4>", out)
        self.assertIn("<code>code</code>", out)
        self.assertIn('<a href="https://example.test/x" rel="nofollow noopener">link</a> continued', out)
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertNotIn("href=\"javascript", build.render_md("- [x](javascript:alert(1))"))


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.cat = os.path.join(self.tmp, "products.yml")
        with open(self.cat, "w", encoding="utf-8") as f:
            f.write(CATALOG)
        self.out = os.path.join(self.tmp, "site")
        build.build(self.out, self.cat, get=fake_get, now=dt.datetime(2026, 10, 2, 8, 0, tzinfo=dt.timezone.utc))

    def read(self, *parts):
        with open(os.path.join(self.out, *parts), encoding="utf-8") as f:
            return f.read()

    def test_public_api(self):
        doc = json.loads(self.read("api", "pub.json"))
        for key in ("id", "version", "date", "notes_md", "notes_url", "npm", "repo", "min_host_version",
                    "sha256", "signature", "pubkey_id"):
            self.assertIn(key, doc)
        self.assertEqual(doc["version"], "1.2.0")
        self.assertEqual(doc["date"], "2026-10-01")
        self.assertEqual(doc["notes_url"], "https://updates.example.test/#pub")
        self.assertEqual(doc["repo"], "https://github.com/owner/nodebb-plugin-pub")
        self.assertEqual(doc["min_host_version"], "4.15.0")
        self.assertIsNone(doc["signature"])

    def test_private_api_has_no_notes_or_links(self):
        doc = json.loads(self.read("api", "priv.json"))
        self.assertEqual((doc["version"], doc["date"], doc["private"]), ("1.1.0", "2026-10-01", True))
        for key in ("notes_md", "notes_url", "npm", "repo"):
            self.assertIsNone(doc[key])

    def test_index_feed_and_page(self):
        index = json.loads(self.read("api", "index.json"))
        self.assertEqual([p["id"] for p in index["products"]], ["pub", "priv", "later"])
        feed = self.read("feed.xml")
        self.assertIn("<title>Publiczny 1.2.0</title>", feed)
        self.assertIn("<title>Prywatny 1.1.0</title>", feed)
        self.assertNotIn("Potem", feed)
        self.assertNotIn("2.0.0-beta.1", feed)
        page = self.read("index.html")
        self.assertIn('id="pub"', page)
        self.assertIn('id="pub-1.1.0"', page)
        self.assertNotIn('id="later"', page)
        self.assertNotIn("{{", page)
        self.assertTrue(os.path.exists(os.path.join(self.out, "assets", "style.css")))


class Bump(unittest.TestCase):
    def test_bump_keeps_comments(self):
        out = bump.bump(CATALOG, "priv", "1.2.0", "2026-10-15")
        self.assertIn('version: "1.2.0"   # bump.py edits this', out)
        self.assertIn('date: "2026-10-15"', out)
        self.assertEqual(out.replace('"1.2.0"', '"1.1.0"').replace("2026-10-15", "2026-10-01"), CATALOG)

    def test_bump_refuses(self):
        for args in (("priv", "1.0.0", "2026-10-15"), ("pub", "9.0.0", "2026-10-15"),
                     ("nope", "1.0.0", "2026-10-15"), ("priv", "1.2", "2026-10-15"), ("priv", "1.2.0", "15.10.2026")):
            with self.assertRaises(catalog.CatalogError, msg=args):
                bump.bump(CATALOG, *args)


if __name__ == "__main__":
    unittest.main()
