"""AST → server-side Route definitions.

Walks each file's tree-sitter CST looking for the framework markers in
config/frameworks.ROUTE_PATTERNS (Flask/FastAPI/Django, Spring/JAX-RS, Express/Nest),
and reads the path literal + HTTP method from the matched node.

  >>> ADAPT ME <<< : the marker-matching and literal-reading below assume generic
  tree-sitter node shapes (decorator / annotation / call with a string-literal
  argument). The exact node types per grammar must be confirmed against real dumps;
  the seams are marked inline.
"""
from __future__ import annotations

from typing import Iterator

from config.frameworks import route_patterns_for, RoutePattern
from code_intelligence.ingest import CstNode, ParsedFile
from code_intelligence.model import Route
from code_intelligence.paths import normalize


# node types that, per grammar, carry a route marker. Confirm against dumps.
DECORATOR_TYPES = {"decorator", "annotation", "marker_annotation",
                   "decorator_expression"}
CALL_TYPES = {"call", "call_expression", "method_invocation"}
STRING_TYPES = {"string", "string_literal", "interpreted_string_literal",
                "template_string"}


def _marker_name(node: CstNode) -> str | None:
    """Last identifier in a decorator/annotation/call head, e.g.
    `@app.get` -> 'get', `@RequestMapping` -> 'RequestMapping'."""
    name = None
    for n in node.walk():
        if not n.children and n.text and n.text.isidentifier():
            name = n.text
    return name


def _first_string_literal(node: CstNode) -> str | None:
    """Read the first string-literal argument under a node (the path)."""
    for n in node.walk():
        if n.type in STRING_TYPES and n.text:
            return n.text.strip().strip('"').strip("'").strip("`")
    return None


def _http_method(pattern: RoutePattern, marker: str) -> str:
    if pattern.method_source == "from_marker":
        m = marker.upper()
        # Spring GetMapping -> GET, Flask get -> GET, RequestMapping/route -> *
        for verb in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD"):
            if verb in m:
                return verb
    return "*"


def extract_routes(pf: ParsedFile) -> list[Route]:
    patterns = route_patterns_for(pf.lang)
    if not patterns:
        return []
    by_marker: dict[str, RoutePattern] = {m: p for p in patterns for m in p.markers}
    prefix_markers = {m for p in patterns for m in p.prefix_markers}

    routes: list[Route] = []
    class_prefix = ""   # NestJS @Controller / Spring class @RequestMapping prefix

    for node in pf.root.walk():
        if node.type not in (DECORATOR_TYPES | CALL_TYPES):
            continue
        marker = _marker_name(node)
        if marker is None:
            continue
        if marker in prefix_markers:
            pref = _first_string_literal(node)
            if pref:
                class_prefix = normalize(pref)   # >>> ADAPT ME: scope this to its class
            # a prefix marker can also itself be a route (Spring @RequestMapping); fall through
        pat = by_marker.get(marker)
        if pat is None:
            continue
        path = _first_string_literal(node)
        if path is None:
            continue
        full = normalize((class_prefix + path) if path.startswith("/") else f"{class_prefix}/{path}")
        routes.append(Route(
            method=_http_method(pat, marker), path=full,
            owner_service=None,             # filled by index (file → service)
            source="ast", file=pf.src_path, line=node.start_line,
        ))
    return routes


def extract_routes_stream(files: Iterator[ParsedFile]) -> Iterator[Route]:
    for pf in files:
        yield from extract_routes(pf)
