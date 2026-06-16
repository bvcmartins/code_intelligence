"""(2) API gateway / ingress / service-mesh → {path-prefix|host → upstream service}.

Authoritative routing: maps an external path-prefix (and/or host) to the upstream
service that serves it. Covers k8s Ingress, Istio VirtualService, Gateway API
HTTPRoute, Kong, APISIX, etc. — each has a different shape, so this is a dispatch
of small per-kind readers.

  >>> ADAPT ME <<< : implement the readers for the gateway tech you actually use.
  Each should append (prefix_or_host, upstream_service) mappings.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from code_intelligence.ingest import ConfigFile
from code_intelligence.paths import normalize


@dataclass
class GatewayRouting:
    prefix_to_service: dict[str, str] = field(default_factory=dict)   # "/billing" -> "billing-svc"
    host_to_service: dict[str, str] = field(default_factory=dict)     # "billing.internal" -> "billing-svc"


def read_gateway(cfg: ConfigFile, out: GatewayRouting) -> None:
    """Dispatch a single config doc to the right reader by its `kind`/shape."""
    d = cfg.data
    if not isinstance(d, dict):
        return
    kind = str(d.get("kind", "")).lower()
    if kind == "ingress":
        _read_k8s_ingress(d, out)
    elif kind == "virtualservice":
        _read_istio_virtualservice(d, out)
    elif kind == "httproute":
        _read_gateway_api_httproute(d, out)
    # >>> ADAPT ME: add Kong/APISIX/Envoy/your-gateway readers here.


def _read_k8s_ingress(d: dict, out: GatewayRouting) -> None:
    for rule in (d.get("spec", {}).get("rules") or []):
        host = rule.get("host")
        for p in (rule.get("http", {}).get("paths") or []):
            prefix = normalize(p.get("path", "/"))
            svc = (p.get("backend", {}).get("service", {}) or {}).get("name")
            if svc:
                out.prefix_to_service[prefix] = svc
                if host:
                    out.host_to_service[host] = svc


def _read_istio_virtualservice(d: dict, out: GatewayRouting) -> None:
    spec = d.get("spec", {})
    for h in spec.get("hosts", []) or []:
        pass  # host→service often needs the DestinationRule; left as ADAPT ME
    for route in spec.get("http", []) or []:
        prefixes = [m.get("uri", {}).get("prefix") for m in route.get("match", []) or []]
        dests = [r.get("destination", {}).get("host") for r in route.get("route", []) or []]
        svc = next((x for x in dests if x), None)
        for pre in prefixes:
            if pre and svc:
                out.prefix_to_service[normalize(pre)] = svc


def _read_gateway_api_httproute(d: dict, out: GatewayRouting) -> None:
    for rule in (d.get("spec", {}).get("rules") or []):
        prefixes = [m.get("path", {}).get("value")
                    for m in rule.get("matches", []) or []]
        refs = [r.get("name") for r in rule.get("backendRefs", []) or []]
        svc = next((x for x in refs if x), None)
        for pre in prefixes:
            if pre and svc:
                out.prefix_to_service[normalize(pre)] = svc
