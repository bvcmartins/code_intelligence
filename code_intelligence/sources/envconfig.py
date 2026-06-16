"""(4) Env / config files → {VAR → value(host/url)}.

The enrichment step that runs *first* in the cascade: turns `BILLING_URL` and
friends into concrete hosts/URLs so the host- and path-based steps have something
to match. Covers .env, .properties, and key/value YAML/JSON config maps.

  >>> ADAPT ME <<< : your real precedence between overlapping env files (per-env
  overrides, k8s ConfigMaps/Secrets) — here later files simply overwrite earlier.
"""
from __future__ import annotations

import re

from code_intelligence.ingest import ConfigFile


_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][\w.]*)\s*[=:]\s*(.+?)\s*$")


def read_env(cfg: ConfigFile, out: dict[str, str]) -> None:
    """Populate VAR → value. URL-ish values are the ones the resolver cares about."""
    if cfg.path.endswith((".env", ".properties")) and isinstance(cfg.data, str):
        for line in cfg.data.splitlines():
            if not line or line.lstrip().startswith("#"):
                continue
            m = _LINE.match(line)
            if m:
                out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    elif isinstance(cfg.data, dict):
        _flatten(cfg.data, out)
        # k8s ConfigMap: real values live under `data:`
        if isinstance(cfg.data.get("data"), dict):
            _flatten(cfg.data["data"], out)


def _flatten(d: dict, out: dict[str, str], prefix: str = "") -> None:
    for k, v in d.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            _flatten(v, out, f"{key}.")
        elif isinstance(v, (str, int)):
            out[str(k)] = str(v)        # store by leaf key; vars referenced by name


def resolve_var(host_expr: str, env: dict[str, str]) -> str | None:
    """'${BILLING_URL}' or '$BILLING_URL' or 'BILLING_URL' → its value, if known."""
    if not host_expr:
        return None
    name = host_expr.strip()
    m = re.match(r"^\$\{?([A-Za-z_][\w.]*)\}?$", name)
    if m:
        name = m.group(1)
    return env.get(name)
