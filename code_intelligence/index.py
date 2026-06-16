"""The unified ResolutionIndex: everything the cascade needs to look up, built from
all four config sources plus AST-extracted routes, with service identity canonicalized.

Built once, up front (it must be whole before any call is resolved). It owns:
  - env vars                (source 4)   VAR → value
  - registry/aliases/hosts  (source 3)   host|name → canonical service, path → service
  - gateway routing         (source 2)   prefix|host → service
  - declared routes         (source 1+ast) path-template → owning service
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from code_intelligence.ingest import ConfigFile
from code_intelligence.model import Route, Service
from code_intelligence.paths import normalize, path_matches, top_segment
from code_intelligence.sources import openapi, gateway, registry, envconfig


@dataclass
class ResolutionIndex:
    env: dict[str, str] = field(default_factory=dict)
    registry: registry.Registry = field(default_factory=registry.Registry)
    routing: gateway.GatewayRouting = field(default_factory=gateway.GatewayRouting)
    routes: list[Route] = field(default_factory=list)            # all declared routes
    _file_service: dict[str, str] = field(default_factory=dict)  # cache file→service

    # --- canonicalization -----------------------------------------------------
    def canonical(self, name: Optional[str]) -> Optional[str]:
        """Map any alias/host/name to its canonical service id (registry is the
        authority; fall back to a normalized form so unknown-but-consistent names
        still collapse together)."""
        if not name:
            return None
        if name in self.registry.alias_to_service:
            return self.registry.alias_to_service[name]
        if name in self.registry.host_to_service:
            return self.registry.host_to_service[name]
        return registry._canonical(name)

    # --- lookups used by the cascade ------------------------------------------
    def service_for_host(self, host: Optional[str]) -> Optional[str]:
        if not host:
            return None
        if host in self.registry.host_to_service:
            return self.registry.host_to_service[host]
        if host in self.routing.host_to_service:
            return self.canonical(self.routing.host_to_service[host])
        # bare hostname that looks like a service name
        return self.canonical(host.split(".")[0])

    def service_for_prefix(self, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        # longest-prefix match against gateway routing
        best = None
        for prefix, svc in self.routing.prefix_to_service.items():
            if normalize(path).startswith(normalize(prefix)):
                if best is None or len(prefix) > len(best[0]):
                    best = (prefix, svc)
        return self.canonical(best[1]) if best else None

    def service_for_route(self, method: str, path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        for r in self.routes:
            if r.owner_service and (r.method in ("*", method) or method == "*") \
               and path_matches(path, r.path):
                return self.canonical(r.owner_service)
        return None

    def service_for_file(self, file: str) -> Optional[str]:
        """Owning service of a *calling* file: manifest path mapping first, else the
        service that owns routes defined in that file."""
        if file in self._file_service:
            return self._file_service[file]
        svc = None
        for prefix, s in sorted(self.registry.path_to_service.items(),
                                key=lambda kv: -len(kv[0])):
            if file.startswith(prefix):
                svc = self.canonical(s)
                break
        if svc is None:
            for r in self.routes:
                if r.source == "ast" and r.file == file and r.owner_service:
                    svc = self.canonical(r.owner_service)
                    break
        self._file_service[file] = svc
        return svc

    def services(self) -> list[Service]:
        return list(self.registry.services.values())


def build_index(configs: Iterable[ConfigFile], ast_routes: Iterable[Route]) -> ResolutionIndex:
    idx = ResolutionIndex()
    # order doesn't matter for building the tables; the *cascade* enforces order.
    for cfg in configs:
        if cfg.kind == "env" or cfg.path.endswith((".env", ".properties")):
            envconfig.read_env(cfg, idx.env)
        if cfg.kind == "registry":
            registry.read_registry(cfg, idx.registry)
        if cfg.kind == "gateway":
            gateway.read_gateway(cfg, idx.routing)
        if cfg.kind == "openapi" or openapi.is_openapi(cfg):
            for r in openapi.routes_from(cfg):
                idx.routes.append(r)
                if r.owner_service:                # register the service as a node
                    idx.registry.ensure(idx.canonical(r.owner_service))

    # fold in AST-declared routes; their owner is the file's service (resolved later
    # via service_for_file, so leave owner_service None here and let aggregate set it)
    idx.routes.extend(ast_routes)

    # ensure gateway/env-discovered services exist as nodes too
    for svc in set(idx.routing.prefix_to_service.values()) | set(idx.routing.host_to_service.values()):
        idx.registry.ensure(idx.canonical(svc))
    return idx
