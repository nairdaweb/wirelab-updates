#!/usr/bin/env python3
"""Sets the version (and date) of a manual product in products.yml, keeping comments and layout.

  python3 scripts/bump.py nodebb-plugin-solved 1.2.0 [--date 2026-10-15] [--catalog products.yml]

For private products, whose versions cannot be read from GitHub in Actions (no token). The new
version must be higher than the current one. Commit and push products.yml afterwards; the
workflow rebuilds the site.
"""

import argparse
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bump(text, pid, version, date):
    if not catalog.parse_semver(version):
        raise catalog.CatalogError(f"not a semver version: {version}")
    if not catalog.DATE_RE.match(date):
        raise catalog.CatalogError(f"not a YYYY-MM-DD date: {date}")
    _, products = catalog.validate(catalog.parse_yaml(text))
    product = next((p for p in products if p["id"] == pid), None)
    if not product:
        raise catalog.CatalogError(f"unknown product: {pid}")
    if product["source"] != "manual":
        raise catalog.CatalogError(f"{pid} has source: {product['source']}; only manual products are bumped here")
    if catalog.semver_key(version) <= catalog.semver_key(product["version"]):
        raise catalog.CatalogError(f"{pid}: {version} is not newer than {product['version']}")

    lines = text.splitlines(keepends=True)
    start = next(i for i, line in enumerate(lines) if re.match(rf"^\s*-\s+id:\s*['\"]?{re.escape(pid)}['\"]?\s*(#.*)?$", line))
    item_indent = len(lines[start]) - len(lines[start].lstrip())
    end = start + 1
    while end < len(lines):
        s = lines[end]
        if s.strip() and not s.lstrip().startswith("#") and len(s) - len(s.lstrip()) <= item_indent:
            break
        end += 1
    done = set()
    for i in range(start, end):
        m = re.match(r"^(\s*)(version|date):\s*[^#\n]*?(\s*#.*)?(\r?\n)?$", lines[i])
        if m:
            value = version if m.group(2) == "version" else date
            lines[i] = f'{m.group(1)}{m.group(2)}: "{value}"{m.group(3) or ""}{m.group(4) or ""}'
            done.add(m.group(2))
    if done != {"version", "date"}:
        raise catalog.CatalogError(f"{pid}: 'version' and 'date' lines not found")
    out = "".join(lines)
    _, check = catalog.validate(catalog.parse_yaml(out))
    p = next(p for p in check if p["id"] == pid)
    if (p["version"], p["date"]) != (version, date):
        raise catalog.CatalogError(f"{pid}: edit did not apply")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("id")
    ap.add_argument("version")
    ap.add_argument("--date", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument("--catalog", default=os.path.join(ROOT, "products.yml"))
    args = ap.parse_args()
    with open(args.catalog, encoding="utf-8") as f:
        text = f.read()
    try:
        out = bump(text, args.id, args.version, args.date)
    except catalog.CatalogError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    with open(args.catalog, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"{args.id}: {args.version} ({args.date})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
