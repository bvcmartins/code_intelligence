"""AST → client-side OutboundCalls.

Walks each file's CST for HTTP-client markers in config/frameworks.CLIENT_PATTERNS
(requests/httpx, RestTemplate/WebClient, fetch/axios) and captures whatever URL
information is literal: a full URL, a bare host, a relative path, or a variable
expression like `${BILLING_URL}/items` (host_expr kept for the resolver to expand).

  >>> ADAPT ME <<< : same caveat as routes.py — node shapes per grammar must be
  confirmed; the URL argument is often a string literal, an f-string/template, or a
  binary concat of a var + literal. The richer your dump, the more you recover.
"""
from __future__ import annotations

from typing import Iterator

from config.frameworks import client_patterns_for, ClientPattern
from code_intelligence.ingest import CstNode, ParsedFile
from code_intelligence.model import OutboundCall
from code_intelligence.paths import split_url
from code_intelligence.extract.routes import (
    CALL_TYPES, STRING_TYPES, _marker_name,
)


def _url_argument(call: CstNode) -> str | None:
    """Best-effort URL string from a call's arguments.

    Handles three common shapes:
      - plain string literal:            "http://billing/items"
      - template/f-string with a var:    `${BILLING_URL}/items`  →  "${BILLING_URL}/items"
      - concat (BASE + "/items"):        joins literal + var-name fragments
    >>> ADAPT ME: refine concat/template handling to your grammar's node types.
    """
    frags: list[str] = []
    for n in call.walk():
        if n.type in STRING_TYPES and n.text:
            frags.append(n.text.strip().strip('"').strip("'").strip("`"))
        elif not n.children and n.text and n.text.isidentifier() and n.text.isupper():
            # ALL_CAPS bare identifier → likely a config var (BILLING_URL)
            frags.append("${" + n.text + "}")
    if not frags:
        return None
    # crude join; the resolver only needs host_expr + path, which split_url derives
    return "".join(frags)


def _method(pattern: ClientPattern, marker: str) -> str:
    if pattern.method_source == "from_marker":
        verb = marker.upper()
        return verb if verb in ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD") else "*"
    return "*"   # "arg"/"unknown": method is in an options object → resolve later


def extract_calls(pf: ParsedFile) -> list[OutboundCall]:
    patterns = client_patterns_for(pf.lang)
    if not patterns:
        return []
    by_marker: dict[str, ClientPattern] = {m: p for p in patterns for m in p.markers}

    calls: list[OutboundCall] = []
    for node in pf.root.walk():
        if node.type not in CALL_TYPES:
            continue
        marker = _marker_name(node)
        pat = marker and by_marker.get(marker)
        if not pat:
            continue
        raw = _url_argument(node)
        if not raw:
            continue
        host_expr, path = split_url(raw)
        calls.append(OutboundCall(
            from_file=pf.src_path, method=_method(pat, marker), raw_url=raw,
            host_expr=host_expr, path=path, lang=pf.lang, line=node.start_line,
        ))
    return calls


def extract_calls_stream(files: Iterator[ParsedFile]) -> Iterator[OutboundCall]:
    for pf in files:
        yield from extract_calls(pf)
