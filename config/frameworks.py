"""Per-framework pattern catalogs: how to recognize route definitions (server) and
HTTP client calls (client) in each language's AST.

These are the analog of codegraph's LangSpec. The AST extractors (extract/routes.py,
extract/calls.py) consult these tables; adding a framework = adding an entry.

The actual node-matching against your tree-sitter JSON is in the extractors and is
marked ADAPT ME there — this file only declares *what* to look for, not how the
JSON is shaped. Verify the identifier/annotation strings against real dumps.
"""
from __future__ import annotations

from dataclasses import dataclass, field


# --- server: route-definition patterns ----------------------------------------

@dataclass(frozen=True)
class RoutePattern:
    lang: str
    framework: str
    kind: str                       # "decorator" | "annotation" | "call"
    # names that mark a route (decorator/annotation names, or callee like "app.get")
    markers: frozenset[str]
    # how to read the HTTP method: "from_marker" (e.g. get→GET) or "arg"
    method_source: str = "from_marker"
    path_arg_index: int = 0         # which call/decorator arg holds the path literal
    # optional class-level prefix marker (NestJS @Controller, Spring class @RequestMapping)
    prefix_markers: frozenset[str] = frozenset()


ROUTE_PATTERNS: list[RoutePattern] = [
    # Python
    RoutePattern("python", "flask", "decorator",
                 frozenset({"route", "get", "post", "put", "delete", "patch"})),
    RoutePattern("python", "fastapi", "decorator",
                 frozenset({"get", "post", "put", "delete", "patch", "api_route"})),
    RoutePattern("python", "django", "call",
                 frozenset({"path", "re_path", "url"})),
    # Java (Spring / JAX-RS) — annotations
    RoutePattern("java", "spring", "annotation",
                 frozenset({"GetMapping", "PostMapping", "PutMapping",
                            "DeleteMapping", "PatchMapping", "RequestMapping"}),
                 prefix_markers=frozenset({"RequestMapping"})),  # class-level prefix
    RoutePattern("java", "jaxrs", "annotation",
                 frozenset({"Path", "GET", "POST", "PUT", "DELETE"}),
                 prefix_markers=frozenset({"Path"})),
    # TypeScript / JavaScript
    RoutePattern("typescript", "express", "call",
                 frozenset({"get", "post", "put", "delete", "patch", "use", "all"})),
    RoutePattern("typescript", "nestjs", "annotation",
                 frozenset({"Get", "Post", "Put", "Delete", "Patch"}),
                 prefix_markers=frozenset({"Controller"})),
    RoutePattern("javascript", "express", "call",
                 frozenset({"get", "post", "put", "delete", "patch", "use", "all"})),
]


# --- client: outbound HTTP-call patterns --------------------------------------

@dataclass(frozen=True)
class ClientPattern:
    lang: str
    library: str
    # callee markers, e.g. "requests.get", "axios.post", "fetch", "WebClient.get"
    markers: frozenset[str]
    method_source: str = "from_marker"   # "from_marker" | "arg" | "unknown"
    url_arg_index: int = 0               # which arg holds the URL


CLIENT_PATTERNS: list[ClientPattern] = [
    # Python
    ClientPattern("python", "requests",
                  frozenset({"get", "post", "put", "delete", "patch", "request", "head"})),
    ClientPattern("python", "httpx",
                  frozenset({"get", "post", "put", "delete", "patch", "request"})),
    ClientPattern("python", "urllib", frozenset({"urlopen", "Request"})),
    # Java
    ClientPattern("java", "resttemplate",
                  frozenset({"getForObject", "postForObject", "exchange",
                             "getForEntity", "postForEntity"})),
    ClientPattern("java", "webclient", frozenset({"get", "post", "put", "delete"})),
    ClientPattern("java", "httpclient", frozenset({"send", "sendAsync"})),
    # TS / JS
    ClientPattern("typescript", "fetch", frozenset({"fetch"}), method_source="arg"),
    ClientPattern("typescript", "axios",
                  frozenset({"get", "post", "put", "delete", "patch", "request"})),
    ClientPattern("javascript", "fetch", frozenset({"fetch"}), method_source="arg"),
    ClientPattern("javascript", "axios",
                  frozenset({"get", "post", "put", "delete", "patch", "request"})),
]


def route_patterns_for(lang: str) -> list[RoutePattern]:
    return [p for p in ROUTE_PATTERNS if p.lang == lang]


def client_patterns_for(lang: str) -> list[ClientPattern]:
    return [p for p in CLIENT_PATTERNS if p.lang == lang]
