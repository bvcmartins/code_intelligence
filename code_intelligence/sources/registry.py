"""(3) Service registry / deployment manifests → {host|name → canonical service}.

This is the *alias authority*: it reconciles the many names a single service has
(short name, k8s Service DNS, hostname, deployment name) to one canonical id, and
maps deployment paths (repo dir) → service so we can attribute a *calling* file to
its owning service.

  >>> ADAPT ME <<< : implement readers for what you have — k8s Service/Deployment,
  Helm values, docker-compose, Consul, an internal service catalog.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from code_intelligence.ingest import ConfigFile
from code_intelligence.model import Service


@dataclass
class Registry:
    services: dict[str, Service] = field(default_factory=dict)   # canonical id -> Service
    host_to_service: dict[str, str] = field(default_factory=dict)
    alias_to_service: dict[str, str] = field(default_factory=dict)
    path_to_service: dict[str, str] = field(default_factory=dict)  # repo dir prefix -> service

    def ensure(self, canonical: str) -> Service:
        s = self.services.get(canonical)
        if s is None:
            s = Service(id=canonical, name=canonical, aliases={canonical})
            self.services[canonical] = s
            self.alias_to_service[canonical] = canonical
        return s

    def add_alias(self, canonical: str, alias: str) -> None:
        if not alias:
            return
        self.ensure(canonical).aliases.add(alias)
        self.alias_to_service[alias] = canonical

    def add_host(self, canonical: str, host: str) -> None:
        if not host:
            return
        self.ensure(canonical).hosts.add(host)
        self.host_to_service[host] = canonical
        self.add_alias(canonical, host)


def read_registry(cfg: ConfigFile, out: Registry) -> None:
    d = cfg.data
    if not isinstance(d, dict):
        return
    kind = str(d.get("kind", "")).lower()
    if kind == "service":               # k8s Service
        _read_k8s_service(d, out)
    elif kind == "deployment":          # k8s Deployment (name + labels)
        name = d.get("metadata", {}).get("name")
        if name:
            out.ensure(_canonical(name))
    # >>> ADAPT ME: docker-compose services, Helm values, Consul, internal catalog.


def _read_k8s_service(d: dict, out: Registry) -> None:
    meta = d.get("metadata", {})
    name = meta.get("name")
    ns = meta.get("namespace", "default")
    if not name:
        return
    canonical = _canonical(name)
    out.ensure(canonical)
    # cluster DNS forms all alias the same service
    for host in (name, f"{name}.{ns}", f"{name}.{ns}.svc",
                 f"{name}.{ns}.svc.cluster.local"):
        out.add_host(canonical, host)


def _canonical(name: str) -> str:
    """>>> ADAPT ME <<< normalize service names to a canonical id.
    Strip common suffixes so billing / billing-svc / billing-service unify."""
    n = name.lower()
    for suf in ("-svc", "-service", "-api", "-deployment", "-deploy"):
        if n.endswith(suf):
            n = n[: -len(suf)]
    return n
