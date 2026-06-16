"""The resolution cascade: one OutboundCall → one ResolutionResult.

Applies all four sources *in sequence* (README), most-authoritative winning, with
env substitution first so later steps have a concrete URL to match. Records other
sources that resolved to a *different* service as conflicts (config/gateway drift).
"""
from __future__ import annotations

from code_intelligence.index import ResolutionIndex
from code_intelligence.model import (
    OutboundCall, ResolutionResult, CONFIDENCE,
    STRATEGY_OPENAPI, STRATEGY_GATEWAY, STRATEGY_REGISTRY, STRATEGY_ENV_HOST,
    STRATEGY_AST_ROUTE, STRATEGY_UNRESOLVED,
)
from code_intelligence.sources.envconfig import resolve_var


def resolve_call(call: OutboundCall, idx: ResolutionIndex) -> ResolutionResult:
    host, path = call.host_expr, call.path

    # 1. ENRICH — substitute env/config vars so host becomes concrete.
    if host and (host.startswith("$") or host.isupper()):
        val = resolve_var(host, idx.env)
        if val:
            from code_intelligence.paths import split_url
            new_host, new_path = split_url(val)
            host = new_host or host
            if new_path and new_path != "/" and (not path or path == "/"):
                path = new_path

    candidates: list[tuple[str, str]] = []   # (service, strategy)

    # 4 (authoritative path) — OpenAPI declared routes
    svc = idx.service_for_route(call.method, path)
    if svc:
        candidates.append((svc, STRATEGY_OPENAPI))

    # 3 (routing) — gateway/ingress path-prefix
    svc = idx.service_for_prefix(path)
    if svc:
        candidates.append((svc, STRATEGY_GATEWAY))

    # 2 (host) — registry/manifest host or (post-enrichment) literal host
    svc = idx.service_for_host(host)
    if svc:
        # distinguish "host came from env var" vs "host was literal" for confidence
        strat = STRATEGY_ENV_HOST if (call.host_expr and
                (call.host_expr.startswith("$") or call.host_expr.isupper())) \
                else STRATEGY_REGISTRY
        candidates.append((svc, strat))

    # 5 (supplement) — AST-extracted routes
    svc = idx.service_for_route(call.method, path)   # includes ast routes via index
    if svc and not any(c[0] == svc for c in candidates):
        candidates.append((svc, STRATEGY_AST_ROUTE))

    if not candidates:
        return ResolutionResult(False, None, STRATEGY_UNRESOLVED, 0.0)

    # pick the most authoritative (highest confidence) candidate
    candidates.sort(key=lambda c: CONFIDENCE[c[1]], reverse=True)
    winner_svc, winner_strat = candidates[0]
    conflicts = sorted({s for s, _ in candidates if s != winner_svc})
    return ResolutionResult(
        resolved=True, to_service=winner_svc, strategy=winner_strat,
        confidence=CONFIDENCE[winner_strat], conflicts=conflicts,
    )
