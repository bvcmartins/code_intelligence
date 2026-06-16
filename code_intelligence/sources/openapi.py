"""(1) OpenAPI / Swagger → {service → served path templates}.

The most authoritative server-side declaration: each spec lists every path a
service exposes. Used as the top of the resolution cascade (match a concrete call
path to the owning service).

  >>> ADAPT ME <<< : how a spec maps to a *service name* varies — it may be
  `info.title`, an `x-service`/`x-application` extension, the filename, or a
  server URL. Set `service_name_of` to your convention.
"""
from __future__ import annotations

from typing import Iterator

from code_intelligence.ingest import ConfigFile
from code_intelligence.model import Route
from code_intelligence.paths import normalize


def is_openapi(cfg: ConfigFile) -> bool:
    d = cfg.data
    return isinstance(d, dict) and ("openapi" in d or "swagger" in d) and "paths" in d


def service_name_of(cfg: ConfigFile) -> str:
    """>>> ADAPT ME <<< pick the service identity for a spec."""
    d = cfg.data or {}
    info = d.get("info", {}) if isinstance(d, dict) else {}
    return (d.get("x-service") or info.get("x-service")
            or info.get("title") or cfg.path.rsplit("/", 1)[-1])


def routes_from(cfg: ConfigFile) -> Iterator[Route]:
    """Yield a Route per (path, method) declared in the spec, owned by its service."""
    if not is_openapi(cfg):
        return
    svc = service_name_of(cfg)
    base = ""
    # OpenAPI 3 servers[].url may carry a base path; v2 uses basePath
    d = cfg.data
    servers = d.get("servers") or []
    if servers and isinstance(servers, list):
        from code_intelligence.paths import split_url
        _, p = split_url(str(servers[0].get("url", "")))
        base = normalize(p or "")
    elif d.get("basePath"):
        base = normalize(d["basePath"])

    for path, ops in (d.get("paths") or {}).items():
        full = normalize(base + path)
        methods = [m.upper() for m in (ops or {}) if m.lower() in
                   ("get", "post", "put", "delete", "patch", "head", "options")]
        for method in (methods or ["*"]):
            yield Route(method=method, path=full, owner_service=svc,
                        source="openapi", file=cfg.path, line=None)
