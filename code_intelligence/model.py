"""Core vocabulary for the service-dependency map.

Everything upstream (tree-sitter ASTs, four config formats) is normalized into
these shapes; everything downstream (resolver, aggregator, renderer) consumes them.
Keeping this small is what keeps the pipeline polyglot and multi-source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# --- resolution strategies, ordered most→least authoritative -------------------
# The cascade in resolve.py tags every edge with the strategy that resolved it,
# which maps to a confidence. Order matters: see README's resolution cascade.
STRATEGY_OPENAPI = "openapi"          # concrete path matched a declared route owner
STRATEGY_GATEWAY = "gateway"          # path-prefix / gateway host → upstream service
STRATEGY_REGISTRY = "registry"        # host/DNS/name → service via manifests
STRATEGY_ENV_HOST = "env_host"        # env var resolved to a host that maps to a service
STRATEGY_AST_ROUTE = "ast_route"      # matched a code-extracted route (supplement)
STRATEGY_UNRESOLVED = "unresolved"

CONFIDENCE = {
    STRATEGY_OPENAPI: 0.95,
    STRATEGY_GATEWAY: 0.9,
    STRATEGY_REGISTRY: 0.9,
    STRATEGY_ENV_HOST: 0.85,
    STRATEGY_AST_ROUTE: 0.6,
    STRATEGY_UNRESOLVED: 0.0,
}


@dataclass(slots=True)
class Service:
    """A canonical service node. Identity is reconciled across all sources via the
    alias set (a service appears as billing / billing-svc / a hostname / an env var)."""
    id: str                                   # canonical id, e.g. "billing"
    name: str = ""
    aliases: set[str] = field(default_factory=set)        # every name it's known by
    hosts: set[str] = field(default_factory=set)          # dns names / hostnames
    path_prefixes: set[str] = field(default_factory=set)  # e.g. "/billing"
    languages: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)        # which inputs declared it


@dataclass(slots=True)
class Route:
    """A served endpoint (server side)."""
    method: str                     # GET / POST / * (uppercased; "*" = any)
    path: str                       # template, e.g. "/billing/{id}"
    owner_service: Optional[str]    # canonical service id, if known at extraction
    source: str                     # "openapi" | "gateway" | "ast"
    file: Optional[str] = None
    line: Optional[int] = None


@dataclass(slots=True)
class OutboundCall:
    """An outbound HTTP call (client side), with whatever was literal in the code."""
    from_file: str
    method: str                     # GET / POST / *
    raw_url: str                    # the literal/partial as written
    host_expr: Optional[str]        # host literal OR a variable name (e.g. "BILLING_URL")
    path: Optional[str]             # path portion if separable
    lang: str
    line: int
    from_service: Optional[str] = None   # owning service of from_file (resolved later)


@dataclass(slots=True)
class ResolutionResult:
    """Outcome of resolving one OutboundCall's *target* service."""
    resolved: bool
    to_service: Optional[str]
    strategy: str                   # one of STRATEGY_*
    confidence: float
    conflicts: list[str] = field(default_factory=list)   # other sources that disagreed


@dataclass(slots=True)
class ServiceEdge:
    """Aggregated dependency from one service to another."""
    from_service: str
    to_service: str
    weight: int = 0                 # number of resolved calls
    confidence: float = 0.0         # max confidence among contributing calls
    strategies: set[str] = field(default_factory=set)
    examples: list[str] = field(default_factory=list)    # "file:line GET /billing/{id}"
