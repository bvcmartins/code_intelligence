"""URL/path normalization + template matching.

Served routes are templates (`/users/{id}`, `/users/:id`, `/users/*`); calls carry
concrete-ish paths (`/users/42`). Matching them needs template-aware comparison,
not string equality. Also splits raw URLs into (host_expr, path) and extracts the
leading path segment used for prefix-based routing.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit


# {id}, :id, <id>, * → a single wildcard segment
_PARAM = re.compile(r"\{[^/}]+\}|:[^/]+|<[^/>]+>|\*")


def split_url(raw: str) -> tuple[str | None, str | None]:
    """('http://billing-svc/items/1') -> ('billing-svc', '/items/1').
    Relative ('/items/1') -> (None, '/items/1').
    Variable-built ('${BILLING_URL}/items') -> ('${BILLING_URL}', '/items') —
    the caller decides whether host_expr is a literal or a var to resolve."""
    raw = raw.strip().strip('"').strip("'")
    if "://" in raw:
        u = urlsplit(raw)
        return (u.netloc or None), (u.path or "/")
    # leading var like ${X}/p or `${X}` + path
    m = re.match(r"^(\$\{[^}]+\}|\$[A-Za-z_]\w*)(/.*)?$", raw)
    if m:
        return m.group(1), (m.group(2) or "/")
    if raw.startswith("/"):
        return None, raw
    return None, raw or None


def normalize(path: str) -> str:
    """Trim trailing slash, collapse doubles. '/a/b/' -> '/a/b'."""
    if not path:
        return "/"
    path = re.sub(r"/{2,}", "/", path)
    return path[:-1] if len(path) > 1 and path.endswith("/") else path


def top_segment(path: str) -> str | None:
    """'/billing/items/1' -> '/billing'  (the prefix used for gateway routing)."""
    p = normalize(path)
    parts = [s for s in p.split("/") if s]
    return f"/{parts[0]}" if parts else None


def template_to_regex(template: str) -> re.Pattern:
    """Compile a route template into a matcher for concrete paths."""
    esc = re.escape(normalize(template))
    # re.escape turned our params into escaped text; swap them back to a segment match
    esc = re.sub(r"\\\{[^/}]+\\\}|:[^/]+|\\<[^/>]+\\>|\\\*", r"[^/]+", esc)
    return re.compile(f"^{esc}/?$")


def path_matches(concrete: str, template: str) -> bool:
    return bool(template_to_regex(template).match(normalize(concrete)))
