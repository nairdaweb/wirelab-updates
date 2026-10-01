"""products.yml reader (a small YAML subset, standard library only), validation and semver helpers.

Supported YAML: block mappings and block sequences indented with spaces, one-line scalars
(plain, "double" or 'single' quoted), null / ~ / empty, true / false, comments after "#".
Not supported: flow collections, anchors, multi-line strings, tabs. Anything else raises
CatalogError with the line number, so a typo fails the build instead of shipping bad data.
"""

import json
import re

KEY_RE = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s+(.*))?$")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NPM_RE = re.compile(r"^(?:@[a-z0-9-~][a-z0-9-._~]*/)?[a-z0-9-~][a-z0-9-._~]*$")
REPO_RE = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
HOST_VERSION_RE = re.compile(r"^\d+(?:\.\d+){0,2}$")

TYPES = {"nodebb-plugin", "chrome-extension", "android-apk", "gateway"}
CHANNELS = {"stable"}
STATUSES = {"released", "soon", "planned"}
VISIBILITIES = {"public", "private"}
SOURCES = {"npm", "manual", "none"}


class CatalogError(ValueError):
    pass


# ---------------------------------------------------------------- YAML subset

def _strip_comment(line):
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == "\\" and quote == '"':
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _scalar(text, lineno):
    text = text.strip()
    if text in ("", "~", "null"):
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if text[0] == '"':
        try:
            value = json.loads(text)
        except ValueError:
            raise CatalogError(f"line {lineno}: bad double-quoted string") from None
        if not isinstance(value, str):
            raise CatalogError(f"line {lineno}: bad double-quoted string")
        return value
    if text[0] == "'":
        if len(text) < 2 or text[-1] != "'":
            raise CatalogError(f"line {lineno}: bad single-quoted string")
        return text[1:-1].replace("''", "'")
    if text[0] in "[{&*!|>@`%":
        raise CatalogError(f"line {lineno}: unsupported YAML syntax")
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse_yaml(text):
    lines = []
    for n, raw in enumerate(text.splitlines(), 1):
        body = _strip_comment(raw).rstrip()
        if not body.strip():
            continue
        lead = body[: len(body) - len(body.lstrip())]
        if "\t" in lead:
            raise CatalogError(f"line {n}: tabs are not allowed for indentation")
        lines.append([len(lead), body.strip(), n])
    if not lines:
        return {}
    value, i = _block(lines, 0, lines[0][0])
    if i != len(lines):
        raise CatalogError(f"line {lines[i][2]}: unexpected indentation")
    return value


def _block(lines, i, indent):
    content = lines[i][1]
    if content == "-" or content.startswith("- "):
        return _seq(lines, i, indent)
    return _map(lines, i, indent)


def _map(lines, i, indent):
    out = {}
    while i < len(lines) and lines[i][0] == indent:
        _, content, n = lines[i]
        if content == "-" or content.startswith("- "):
            break
        m = KEY_RE.match(content)
        if not m:
            raise CatalogError(f"line {n}: expected 'key: value'")
        key, rest = m.group(1), m.group(2)
        if key in out:
            raise CatalogError(f"line {n}: duplicate key '{key}'")
        i += 1
        if rest is None or rest.strip() == "":
            if i < len(lines) and (lines[i][0] > indent or (
                    lines[i][0] == indent and (lines[i][1] == "-" or lines[i][1].startswith("- ")))):
                out[key], i = _block(lines, i, lines[i][0])
            else:
                out[key] = None
        else:
            out[key] = _scalar(rest, n)
    if i < len(lines) and lines[i][0] > indent:
        raise CatalogError(f"line {lines[i][2]}: unexpected indentation")
    return out, i


def _seq(lines, i, indent):
    out = []
    while i < len(lines) and lines[i][0] == indent and (lines[i][1] == "-" or lines[i][1].startswith("- ")):
        _, content, n = lines[i]
        item = content[1:].lstrip()
        if not item:
            i += 1
            if i < len(lines) and lines[i][0] > indent:
                value, i = _block(lines, i, lines[i][0])
            else:
                value = None
            out.append(value)
        elif KEY_RE.match(item) and item[0] not in "\"'":
            # "- key: value" starts a mapping whose keys are aligned after the dash
            col = indent + (len(content) - len(item))
            lines[i] = [col, item, n]
            value, i = _map(lines, i, col)
            out.append(value)
        else:
            out.append(_scalar(item, n))
            i += 1
    if i < len(lines) and lines[i][0] > indent:
        raise CatalogError(f"line {lines[i][2]}: unexpected indentation")
    return out, i


# ---------------------------------------------------------------- semver

def parse_semver(version):
    m = SEMVER_RE.match(str(version or ""))
    if not m:
        return None
    pre = m.group(4)
    return int(m.group(1)), int(m.group(2)), int(m.group(3)), pre


def semver_key(version):
    """Sort key: releases after their pre-releases, numeric pre-release parts compared as numbers."""
    p = parse_semver(version)
    if not p:
        return (-1, -1, -1, 0, ())
    major, minor, patch, pre = p
    if pre is None:
        return (major, minor, patch, 1, ())
    parts = tuple((0, int(x), "") if x.isdigit() else (1, 0, x) for x in pre.split("."))
    return (major, minor, patch, 0, parts)


def min_from_range(spec):
    """'^4.15.0' / '>=4.0.0' / '4.x' -> '4.15.0' / '4.0.0' / '4.0.0'; None when unreadable."""
    m = re.search(r"(\d+)(?:\.(\d+|x|\*))?(?:\.(\d+|x|\*))?", str(spec or ""))
    if not m:
        return None
    nums = [m.group(1)] + [g if g and g.isdigit() else "0" for g in (m.group(2), m.group(3))]
    return ".".join(nums)


# ---------------------------------------------------------------- validation

def _localized(value, field, pid, required):
    if value is None and not required:
        return None
    if not isinstance(value, dict) or not all(isinstance(value.get(k), str) and value.get(k).strip() for k in ("pl", "en")):
        raise CatalogError(f"{pid}: '{field}' needs non-empty 'pl' and 'en'")
    return {"pl": value["pl"].strip(), "en": value["en"].strip()}


def _choice(p, field, allowed, pid):
    value = p.get(field)
    if value not in allowed:
        raise CatalogError(f"{pid}: '{field}' must be one of {sorted(allowed)}")
    return value


def validate(data):
    """Returns (site, products) with defaults filled in; raises CatalogError on any problem."""
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise CatalogError("products.yml: 'schema: 1' is required")
    site = data.get("site")
    if not isinstance(site, str) or not re.match(r"^https://[a-z0-9.-]+$", site):
        raise CatalogError("products.yml: 'site' must be an https origin without a trailing slash")
    items = data.get("products")
    if not isinstance(items, list) or not items:
        raise CatalogError("products.yml: 'products' must be a non-empty list")
    seen = set()
    products = []
    for raw in items:
        if not isinstance(raw, dict):
            raise CatalogError("products.yml: each product must be a mapping")
        pid = raw.get("id")
        if not isinstance(pid, str) or not ID_RE.match(pid):
            raise CatalogError(f"bad product id: {pid!r}")
        if pid in seen:
            raise CatalogError(f"duplicate product id: {pid}")
        seen.add(pid)
        p = {
            "id": pid,
            "name": _localized(raw.get("name"), "name", pid, True),
            "type": _choice(raw, "type", TYPES, pid),
            "channel": _choice(raw, "channel", CHANNELS, pid),
            "status": _choice(raw, "status", STATUSES, pid),
            "visibility": _choice(raw, "visibility", VISIBILITIES, pid),
            "source": _choice(raw, "source", SOURCES, pid),
            "summary": None, "npm": None, "repo": None, "branch": "main", "changelog": "CHANGELOG.md",
            "version": None, "date": None, "min_host_version": None,
        }
        private = p["visibility"] == "private"
        p["summary"] = None if private else _localized(raw.get("summary"), "summary", pid, p["status"] != "planned")
        if p["source"] == "npm":
            if private:
                raise CatalogError(f"{pid}: private products cannot use source: npm (no token in Actions)")
            for field, rx in (("npm", NPM_RE), ("repo", REPO_RE)):
                if not isinstance(raw.get(field), str) or not rx.match(raw[field]):
                    raise CatalogError(f"{pid}: '{field}' is required for source: npm")
                p[field] = raw[field]
            for field in ("branch", "changelog"):
                if raw.get(field) is not None:
                    if not isinstance(raw[field], str) or not re.match(r"^[A-Za-z0-9._/-]+$", raw[field]) or ".." in raw[field]:
                        raise CatalogError(f"{pid}: bad '{field}'")
                    p[field] = raw[field]
            if raw.get("version") is not None:
                raise CatalogError(f"{pid}: 'version' comes from npm; remove it from products.yml")
        elif private and (raw.get("npm") or raw.get("repo")):
            raise CatalogError(f"{pid}: private products must not list npm or repo")
        else:
            for field in ("npm", "repo"):
                value = raw.get(field)
                if value is not None:
                    if not isinstance(value, str) or not (NPM_RE if field == "npm" else REPO_RE).match(value):
                        raise CatalogError(f"{pid}: bad '{field}'")
                    p[field] = value
        if p["source"] == "manual":
            version, date = raw.get("version"), raw.get("date")
            if not isinstance(version, str) or not parse_semver(version):
                raise CatalogError(f"{pid}: 'version' must be a quoted semver string, e.g. \"1.0.0\"")
            if not isinstance(date, str) or not DATE_RE.match(date):
                raise CatalogError(f"{pid}: 'date' must be a quoted YYYY-MM-DD string")
            p["version"], p["date"] = version, date
        elif p["source"] == "none":
            if raw.get("version") is not None or raw.get("date") is not None:
                raise CatalogError(f"{pid}: source: none takes no version or date")
            if p["status"] != "planned":
                raise CatalogError(f"{pid}: source: none is only for status: planned")
        mhv = raw.get("min_host_version")
        if mhv is not None:
            mhv = str(mhv)
            if not HOST_VERSION_RE.match(mhv):
                raise CatalogError(f"{pid}: bad 'min_host_version'")
            p["min_host_version"] = mhv
        products.append(p)
    return site, products


def load(path):
    with open(path, encoding="utf-8") as f:
        return validate(parse_yaml(f.read()))
