# code_intelligence — service dependency map from API paths

Builds a **runtime service-dependency diagram** for a large, polyglot codebase by
matching, across the whole repo, **who serves an API path** against **who calls it**.
Inputs are the tree-sitter ASTs (already in GCS) plus ingested **configuration files**.
Unlike an import graph, this captures real *service-to-service* wiring.

Languages targeted: Python, Java, TypeScript, JavaScript. Mostly REST.

> Sibling project `codegraph/` (import/AST code graph) is separate and untouched.
> This repo is a **backbone**: format-coupling points are quarantined behind
> `# >>> SCHEMA ADAPTER` / `# >>> ADAPT ME` markers so you wire the real tree-sitter
> JSON and config schemas with Gemini on the workstation.

## Why API paths, not imports

Python doesn't `import` Java; services talk over the network. So the dependency
edges live in **API calls + routing**, not imports. We discover them from:

- **Server side** — route/endpoint definitions (what paths a service exposes)
- **Client side** — outbound HTTP calls (what paths a service calls)
- **Config** — the Rosetta stone that resolves the messy, "all over the place"
  URLs (env vars, hostnames, gateway prefixes) back to concrete services.

## The resolution cascade (all four config sources, in sequence)

For each outbound call `{method, host-or-var, path}`:

```
1. env/config        substitute vars   (BILLING_URL → http://billing-svc)   ENRICH (run first)
2. registry/manifest  host/DNS/name → canonical service                     by HOST
3. gateway/ingress    path-prefix / gateway host → upstream service          by ROUTING
4. openapi            concrete path → declared route owner                   by PATH (authoritative)
5. ast route-defs     match against code-extracted routes (supplement)       medium confidence
6. unresolved         → findings appendix
```

env/config runs first because it turns variables into real hosts so later steps
can match. When two sources resolve and **disagree**, the more authoritative wins
and the conflict is logged as a finding (real config/gateway drift).

## Pipeline

```
GCS tree-sitter JSON ─┐
                      ├─ extract.routes   AST → Route defs (server)
                      └─ extract.calls    AST → OutboundCalls (client)
config files ─────────── sources.{openapi,gateway,registry,envconfig}
                                   │
                                   ▼
                      index.ResolutionIndex   (+ service canonicalization / alias map)
                                   │
                      resolve.resolve_call    (the 6-step cascade, confidence-tagged)
                                   │
                      aggregate.build_edges    calls → ServiceEdges (weight, confidence, cycles)
                                   │
                      render.to_dot → Graphviz SVG/PDF
                      document.build_html      diagram + dependency matrix + coverage/findings
```

## Layout

```
config/frameworks.py          per-framework route + http-client patterns (the catalogs)
code_intelligence/
  model.py                    Service / Route / OutboundCall / ServiceEdge / ResolutionResult
  ingest.py                   GCS/local streaming, tree-sitter normalize, config loading  ← SCHEMA ADAPTER
  extract/routes.py           AST → server route definitions
  extract/calls.py            AST → client outbound calls
  sources/openapi.py          (1) OpenAPI/Swagger  → service → served paths   ← ADAPT ME
  sources/gateway.py          (2) gateway/ingress/mesh → prefix/host → service ← ADAPT ME
  sources/registry.py         (3) registry/manifests → host/name → service (alias authority) ← ADAPT ME
  sources/envconfig.py        (4) env/config → var → host/url                 ← ADAPT ME
  index.py                    unified ResolutionIndex + canonicalization
  resolve.py                  the 6-step cascade
  aggregate.py                calls → ServiceEdges, cycle detection
  render.py                   Graphviz dot + SVG/PDF
  document.py                 self-contained HTML report (diagram + matrix + findings)
  pipeline.py                 orchestration
```

## Run order (once adapted)

```bash
python -m code_intelligence.pipeline \
    --gcs gs://YOUR_BUCKET/asts --config ./config_dump \
    --out ./service_map.html
```

## What it honestly is

A **static** discovery of service wiring. It captures literal/config-resolvable
endpoints; it cannot see URLs built fully at runtime, reflection, or async/event
flows. The report quantifies coverage ("83% of calls resolved; 17% unresolved")
and lists the unresolved tail + config conflicts — usually the most useful findings.
