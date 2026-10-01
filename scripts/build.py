#!/usr/bin/env python3
"""Builds updates.wirelab.pl into a folder (default _site). Standard library only.

  python3 scripts/build.py [--out _site] [--catalog products.yml]

Public products (source: npm): versions and dates from registry.npmjs.org, release notes from
CHANGELOG.md in the public GitHub repo (raw.githubusercontent.com). Private and manual products:
version and date from products.yml only; nothing is fetched for them.

Output: index.html, api/<id>.json, api/index.json, feed.xml, assets/. If a public source cannot be
read after retries, the build fails and nothing is deployed, so the live site keeps the last good data.
"""

import argparse
import datetime as dt
import html
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = "wirelab-updates-build (+https://updates.wirelab.pl)"
MAX_BODY = 8 * 1024 * 1024
OLDER_SHOWN = 8
FEED_ITEMS = 40

TYPE_LABEL = {
    "nodebb-plugin": {"pl": "Plugin NodeBB", "en": "NodeBB plugin"},
    "chrome-extension": {"pl": "Rozszerzenie Chrome", "en": "Chrome extension"},
    "android-apk": {"pl": "Aplikacja Android", "en": "Android app"},
    "gateway": {"pl": "Brama", "en": "Gateway"},
}
HOST_LABEL = {"nodebb-plugin": "NodeBB", "chrome-extension": "Chrome", "android-apk": "Android", "gateway": ""}


# ---------------------------------------------------------------- network

def fetch(url, accept="application/json", tries=3):
    last = None
    for attempt in range(tries):
        if attempt:
            time.sleep(2 * attempt)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                body = r.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise ValueError(f"{url}: response too large")
                return body.decode("utf-8")
        except urllib.error.HTTPError as e:
            last = e
            if 400 <= e.code < 500 and e.code != 429:
                break
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            last = e
    raise RuntimeError(f"{url}: {last}")


# ---------------------------------------------------------------- changelog and markdown

HEAD_RE = re.compile(r"^##\s+\[?v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]?(?:\s*[-–—]\s*(\d{4}-\d{2}-\d{2}))?\s*$")


def parse_changelog(text):
    """'## [1.2.0] - 2026-10-01' or '## 1.2.0' sections -> {version: {"date", "md"}}."""
    out, cur, buf = {}, None, []

    def flush():
        if cur:
            out[cur[0]] = {"date": cur[1], "md": "\n".join(buf).strip() or None}

    for line in (text or "").splitlines():
        if line.startswith("## "):
            flush()
            m = HEAD_RE.match(line.strip())
            cur, buf = ((m.group(1), m.group(2)) if m else None), []
        elif cur:
            buf.append(line.rstrip())
    flush()
    return out


def _inline(text):
    """Escapes text and renders `code`, **bold** and [links](https://...)."""
    out, pos = [], 0
    pattern = re.compile(r"`([^`]+)`|\*\*(.+?)\*\*|\[([^\]]+)\]\((https?://[^\s)]+)\)")
    for m in pattern.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f"<code>{html.escape(m.group(1))}</code>")
        elif m.group(2) is not None:
            out.append(f"<strong>{_inline(m.group(2))}</strong>")
        else:
            href = html.escape(m.group(4), quote=True)
            out.append(f'<a href="{href}" rel="nofollow noopener">{html.escape(m.group(3))}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def render_md(md):
    """Markdown subset used in Keep a Changelog files: ### headings, - lists (wrapped lines), paragraphs."""
    if not md:
        return ""
    out, para, item, in_list = [], [], None, False

    def end_item():
        nonlocal item
        if item is not None:
            out.append(f"<li>{_inline(' '.join(item))}</li>")
            item = None

    def end_list():
        nonlocal in_list
        end_item()
        if in_list:
            out.append("</ul>")
            in_list = False

    def end_para():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para.clear()

    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            end_para()
            end_item()
            continue
        m = re.match(r"^#{3,6}\s+(.*)$", line)
        if m:
            end_para()
            end_list()
            out.append(f"<h4>{_inline(m.group(1))}</h4>")
        elif re.match(r"^[-*]\s+", line) and not raw.startswith("    "):
            end_para()
            end_item()
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = [re.sub(r"^[-*]\s+", "", line)]
        elif item is not None:
            item.append(line)
        else:
            end_list()
            para.append(line)
    end_para()
    end_list()
    return "\n".join(out)


# ---------------------------------------------------------------- data

def iso_date(value):
    return value[:10] if isinstance(value, str) and catalog.DATE_RE.match(value[:10]) else None


def resolve(product, get=fetch):
    """Returns (releases newest first, min_host_version). A release: {version, date, published, notes_md}."""
    if product["source"] == "none":
        return [], product["min_host_version"]
    if product["source"] == "manual":
        return [{"version": product["version"], "date": product["date"],
                 "published": product["date"] + "T00:00:00Z", "notes_md": None}], product["min_host_version"]

    name = product["npm"]
    doc = json.loads(get("https://registry.npmjs.org/" + urllib.parse.quote(name, safe="@")))
    latest = (doc.get("dist-tags") or {}).get("latest")
    versions = doc.get("versions") or {}
    if not catalog.parse_semver(latest) or latest not in versions:
        raise RuntimeError(f"{name}: no valid 'latest' on npm")
    times = doc.get("time") or {}
    meta = versions[latest] or {}
    min_host = product["min_host_version"] or catalog.min_from_range((meta.get("nbbpm") or {}).get("compatibility"))

    url = f"https://raw.githubusercontent.com/{product['repo']}/{product['branch']}/{product['changelog']}"
    notes = parse_changelog(get(url, accept="text/plain"))

    stable = [v for v in versions if catalog.parse_semver(v) and catalog.parse_semver(v)[3] is None
              and catalog.semver_key(v) <= catalog.semver_key(latest) and not (versions[v] or {}).get("deprecated")]
    if latest not in stable:
        stable.append(latest)
    releases = []
    for v in sorted(stable, key=catalog.semver_key, reverse=True):
        published = times.get(v) if isinstance(times.get(v), str) else None
        date = iso_date(published) or (notes.get(v) or {}).get("date")
        releases.append({"version": v, "date": date, "published": published,
                         "notes_md": (notes.get(v) or {}).get("md")})
    return releases, min_host


def api_doc(product, site, releases, min_host):
    private = product["visibility"] == "private"
    top = releases[0] if releases else {}
    has_page = product["status"] != "planned"
    return {
        "schema": 1,
        "id": product["id"],
        "name": product["name"],
        "type": product["type"],
        "channel": product["channel"],
        "status": product["status"],
        "private": private,
        "version": top.get("version"),
        "date": top.get("date"),
        "notes_md": None if private else top.get("notes_md"),
        "notes_url": None if private or not has_page else f"{site}/#{product['id']}",
        "npm": None if private else product["npm"],
        "repo": None if private or not product["repo"] else f"https://github.com/{product['repo']}",
        "min_host_version": min_host,
        # filled in steps 2-3 (signed artefacts); null until then
        "sha256": None,
        "signature": None,
        "pubkey_id": None,
    }


# ---------------------------------------------------------------- output

def t2(pl, en):
    """Both languages in the markup; CSS shows the one matching <html lang>."""
    return f'<span lang="pl" data-l="pl">{pl}</span><span lang="en" data-l="en">{en}</span>'


def fmt_date(iso, lang):
    if not iso:
        return "–"
    d = dt.date.fromisoformat(iso)
    if lang == "pl":
        months = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
                  "września", "października", "listopada", "grudnia"]
        return f"{d.day} {months[d.month - 1]} {d.year}"
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December"]
    return f"{d.day} {months[d.month - 1]} {d.year}"


def card(product, doc, releases):
    e = html.escape
    pid = product["id"]
    private = doc["private"]
    name = t2(e(product["name"]["pl"]), e(product["name"]["en"]))
    chips = [f'<span class="chip">{t2(*(e(x) for x in TYPE_LABEL[product["type"]].values()))}</span>']
    if private:
        chips.append(f'<span class="chip chip-private">{t2("prywatny", "private")}</span>')
    if product["status"] == "soon":
        chips.append(f'<span class="chip chip-soon">{t2("wkrótce", "coming soon")}</span>')
    version = e(doc["version"] or "–")
    date_html = (f'<time datetime="{e(doc["date"])}">{t2(fmt_date(doc["date"], "pl"), fmt_date(doc["date"], "en"))}</time>'
                 if doc["date"] else "")
    parts = [f'<article class="prod" id="{e(pid)}" aria-labelledby="{e(pid)}-h">',
             '<div class="prod-head">',
             f'<div><h2 id="{e(pid)}-h">{name}</h2><p class="pkg">{e(pid)}</p></div>',
             f'<div class="ver"><span class="ver-num">{version}</span>{date_html}</div>',
             '</div>',
             f'<p class="chips">{"".join(chips)}</p>']
    if product["summary"]:
        parts.append(f'<p class="summary">{t2(e(product["summary"]["pl"]), e(product["summary"]["en"]))}</p>')
    if private:
        parts.append(f'<p class="private-note">{t2("Prywatny, aktualizacja skryptem wirelab.", "Private, updated with the wirelab deployment script.")}</p>')
    if doc["min_host_version"] and HOST_LABEL[product["type"]]:
        host = f'{HOST_LABEL[product["type"]]} {e(doc["min_host_version"])}+'
        parts.append(f'<p class="host">{t2("Wymaga", "Requires")}: {host}</p>')

    if not private and product["status"] == "released":
        latest = releases[0] if releases else None
        if latest and latest["notes_md"]:
            parts.append(f'<div class="notes" lang="en"><h3 class="notes-h">{t2("Co nowego w", "What&#8217;s new in")} {e(latest["version"])}</h3>{render_md(latest["notes_md"])}</div>')
        older = releases[1:1 + OLDER_SHOWN]
        if older:
            parts.append(f'<details class="older"><summary>{t2("Wcześniejsze wydania", "Earlier releases")} ({len(older)})</summary>')
            for r in older:
                when = f' <span class="dim">· {t2(fmt_date(r["date"], "pl"), fmt_date(r["date"], "en"))}</span>' if r["date"] else ""
                body = render_md(r["notes_md"]) if r["notes_md"] else f'<p class="dim">{t2("Brak opisu w CHANGELOG.md.", "No entry in CHANGELOG.md.")}</p>'
                parts.append(f'<section class="rel" id="{e(pid)}-{e(r["version"])}"><h3>{e(r["version"])}{when}</h3><div class="notes" lang="en">{body}</div></section>')
            parts.append("</details>")

    links = []
    if doc["npm"]:
        links.append(f'<a href="https://www.npmjs.com/package/{e(doc["npm"])}" rel="noopener">npm</a>')
    if doc["repo"]:
        links.append(f'<a href="{e(doc["repo"])}" rel="noopener">GitHub</a>')
        links.append(f'<a href="{e(doc["repo"])}/blob/{e(product["branch"])}/{e(product["changelog"])}" rel="noopener">CHANGELOG</a>')
    links.append(f'<a href="api/{e(pid)}.json">JSON</a>')
    parts.append(f'<p class="links">{" · ".join(links)}</p>')
    parts.append("</article>")
    return "\n".join(parts)


def page(site, shown, generated):
    gen_iso = generated.strftime("%Y-%m-%dT%H:%M:%SZ")
    gen_text = generated.strftime("%Y-%m-%d %H:%M UTC")
    cards = "\n".join(card(p, d, r) for p, d, r in shown)
    with open(os.path.join(ROOT, "scripts", "page.html"), encoding="utf-8") as f:
        tpl = f.read()
    return (tpl.replace("{{CARDS}}", cards)
               .replace("{{GENERATED_ISO}}", gen_iso)
               .replace("{{GENERATED}}", gen_text)
               .replace("{{SITE}}", html.escape(site)))


def rfc822(published, date):
    value = published or (date + "T00:00:00Z" if date else None)
    if not value:
        return None
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc)


def feed(site, resolved, generated):
    e = html.escape
    items = []
    for product, doc, releases in resolved:
        if product["status"] != "released":
            continue
        rels = releases if not doc["private"] else releases[:1]
        for r in rels:
            when = rfc822(r["published"], r["date"])
            if not when:
                continue
            if doc["private"]:
                desc = "Prywatny plugin, aktualizacja skryptem wirelab. / Private plugin, updated with the wirelab deployment script."
                link = f"{site}/#{product['id']}"
            else:
                desc = render_md(r["notes_md"]) or "Bez opisu. / No release notes."
                link = f"{site}/#{product['id']}" if r is releases[0] else f"{site}/#{product['id']}-{r['version']}"
            items.append((when, product, r, desc, link))
    items.sort(key=lambda x: (x[0], x[2]["version"]), reverse=True)
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
           "<channel>",
           "<title>wirelab: wydania / releases</title>",
           f"<link>{e(site)}/</link>",
           f'<atom:link href="{e(site)}/feed.xml" rel="self" type="application/rss+xml"/>',
           "<description>Nowe wersje pluginów i aplikacji wirelab. New versions of wirelab plugins and apps.</description>",
           "<language>pl</language>",
           f"<lastBuildDate>{generated.strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>",
           "<ttl>360</ttl>"]
    for when, product, r, desc, link in items[:FEED_ITEMS]:
        out += ["<item>",
                f"<title>{e(product['name']['pl'])} {e(r['version'])}</title>",
                f"<link>{e(link)}</link>",
                f'<guid isPermaLink="false">{e(product["id"])}@{e(r["version"])}</guid>',
                f"<pubDate>{when.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>",
                f"<category>{e(product['type'])}</category>",
                f"<description>{e(desc)}</description>",
                "</item>"]
    out += ["</channel>", "</rss>", ""]
    return "\n".join(out)


def write_json(path, value):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def build(out, catalog_path, get=fetch, now=None):
    site, products = catalog.load(catalog_path)
    generated = (now or dt.datetime.now(dt.timezone.utc)).replace(microsecond=0)
    resolved = []
    for p in products:
        releases, min_host = resolve(p, get)
        resolved.append((p, api_doc(p, site, releases, min_host), releases))

    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, "api"))
    for p, doc, _ in resolved:
        write_json(os.path.join(out, "api", f"{p['id']}.json"), doc)
    write_json(os.path.join(out, "api", "index.json"), {
        "schema": 1,
        "generated_at": generated.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "products": [{k: d[k] for k in ("id", "name", "type", "channel", "status", "private", "version", "date")}
                     | {"url": f"{site}/api/{d['id']}.json"} for _, d, _ in resolved],
    })
    with open(os.path.join(out, "feed.xml"), "w", encoding="utf-8") as f:
        f.write(feed(site, resolved, generated))
    shown = [x for x in resolved if x[0]["status"] != "planned"]
    shown.sort(key=lambda x: (x[0]["status"] != "released", x[1]["private"]))
    with open(os.path.join(out, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(site, shown, generated))
    shutil.copytree(os.path.join(ROOT, "assets"), os.path.join(out, "assets"))
    with open(os.path.join(out, ".nojekyll"), "w") as f:
        f.write("")
    return resolved


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--catalog", default=os.path.join(ROOT, "products.yml"))
    args = ap.parse_args()
    try:
        resolved = build(args.out, args.catalog)
    except (catalog.CatalogError, RuntimeError, ValueError) as e:
        print(f"::error::{e}", file=sys.stderr)
        return 1
    for p, d, _ in resolved:
        print(f"{p['id']:<34} {d['version'] or '-':<10} {d['date'] or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
