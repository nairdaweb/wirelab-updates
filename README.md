# wirelab updates

Source of [updates.wirelab.pl](https://updates.wirelab.pl): a static release catalogue for wirelab
plugins and apps, built by GitHub Actions and served by GitHub Pages.

## How it works

- `products.yml` is the hand-edited catalogue: id, Polish and English names, type, channel, status,
  visibility and where the version comes from.
- `.github/workflows/build.yml` runs every 6 hours, on every push to `main` and on demand. It runs the
  tests and `scripts/build.py` (Python standard library only), then deploys `_site` to Pages.
- Public products (`source: npm`): versions and dates from `https://registry.npmjs.org/<name>`, release
  notes from `CHANGELOG.md` in the public GitHub repo (Keep a Changelog sections `## [x.y.z] - date`).
  Pre-releases and deprecated versions are skipped.
- Private products (`visibility: private`, `source: manual`): only the version number and date from
  `products.yml`. Nothing is fetched for them and no notes or repository links are published. Update
  them with `python3 scripts/bump.py <id> <version> [--date YYYY-MM-DD]` and push.
- `status: soon` products are listed with the version from `products.yml`; `status: planned` ones are
  only placeholders (JSON with `version: null`, not shown on the page).
- If any public source cannot be read, the run fails and nothing is deployed, so the site keeps the
  last good data.

## Output

| Path | Content |
|---|---|
| `/` | Release list, Polish and English, light and dark theme, no third-party requests |
| `/api/<id>.json` | Latest release of one product |
| `/api/index.json` | All products with their latest version |
| `/feed.xml` | RSS 2.0, newest releases first |

`/api/<id>.json`:

```json
{
  "schema": 1,
  "id": "nodebb-plugin-topic-icons",
  "name": { "pl": "Ikony tematów", "en": "Topic icons" },
  "type": "nodebb-plugin",
  "channel": "stable",
  "status": "released",
  "private": false,
  "version": "1.2.0",
  "date": "2026-10-01",
  "notes_md": "### Added\n- ...",
  "notes_url": "https://updates.wirelab.pl/#nodebb-plugin-topic-icons",
  "npm": "nodebb-plugin-topic-icons",
  "repo": "https://github.com/nairdaweb/nodebb-plugin-topic-icons",
  "min_host_version": "4.15.0",
  "sha256": null,
  "signature": null,
  "pubkey_id": null
}
```

Private products have `notes_md`, `notes_url`, `npm` and `repo` set to `null`. `sha256`, `signature`
and `pubkey_id` are reserved for signed artefacts and are `null` for now. Clients must ignore unknown
fields.

## Update checks in the plugins

The NodeBB plugins fetch `/api/<id>.json` at most once a day (and when their ACP page is opened, from a
cache) with a plain `GET`: no query string, no cookies, a `User-Agent` of `<plugin>/<version>`. They
can be switched off in each plugin's ACP page. GitHub, which hosts this site, sees the forum server's
IP address, as for any web request.

## Development

```sh
python3 -m unittest discover -s tests
python3 scripts/build.py --out _site    # needs network access to npm and GitHub
python3 -m http.server -d _site 8000
```

`products.yml` uses a small YAML subset (see `scripts/catalog.py`); quote versions and dates.
