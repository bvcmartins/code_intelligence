"""End-to-end orchestration: ASTs + config → service dependency document.

  python -m code_intelligence.pipeline \
      --gcs gs://BUCKET/asts --config ./config_dump --out ./service_map.html

Two inputs stream independently:
  - ASTs  → route definitions (server) + outbound calls (client)
  - config → the four-source resolution index
Then: build index → resolve calls → aggregate → render → write HTML report.
"""
from __future__ import annotations

import argparse
import os

from code_intelligence.ingest import load_asts, load_configs
from code_intelligence.extract.routes import extract_routes
from code_intelligence.extract.calls import extract_calls
from code_intelligence.index import build_index
from code_intelligence.aggregate import build_edges
from code_intelligence.render import render
from code_intelligence.document import build_html


def run(ast_source: str, config_source: str, out_html: str,
        title: str = "Service Dependency Map") -> None:
    # 1. config → list (small; held whole to build the index)
    print("loading config…", flush=True)
    configs = list(load_configs(config_source))
    print(f"  {len(configs)} config files", flush=True)

    # 2. ASTs → routes + calls. Single pass; routes feed the index, calls buffered.
    #    (For very large repos, spill calls to disk like codegraph does with refs.)
    print("extracting routes + calls from ASTs…", flush=True)
    ast_routes = []
    calls = []
    n = 0
    for pf in load_asts(ast_source):
        ast_routes.extend(extract_routes(pf))
        calls.extend(extract_calls(pf))
        n += 1
        if n % 1000 == 0:
            print(f"  {n} files · {len(ast_routes)} routes · {len(calls)} calls", flush=True)
    print(f"  done: {n} files · {len(ast_routes)} routes · {len(calls)} calls", flush=True)

    # 3. unified resolution index (must be whole before resolving)
    print("building resolution index…", flush=True)
    idx = build_index(configs, ast_routes)
    print(f"  {len(idx.services())} services · {len(idx.routes)} routes · "
          f"{len(idx.env)} env vars", flush=True)

    # 4. resolve + aggregate
    print("resolving calls → service edges…", flush=True)
    agg = build_edges(calls, idx)
    print(f"  coverage {agg.coverage*100:.0f}% · {len(agg.edges)} edges", flush=True)

    # 5. render + document
    base = os.path.splitext(out_html)[0]
    svg = render(agg, base, fmt="svg", title=title)
    render(agg, base, fmt="pdf", title=title)        # PDF alongside, if dot present
    with open(out_html, "w") as fh:
        fh.write(build_html(agg, svg, title=title))
    print(f"wrote {out_html}  (+ {base}.dot, {base}.svg/.pdf if graphviz present)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Service dependency map from API paths.")
    ap.add_argument("--gcs", "--asts", dest="asts", required=True,
                    help="gs://bucket/prefix or local dir of tree-sitter JSON")
    ap.add_argument("--config", required=True,
                    help="gs://bucket/prefix or local dir of config files")
    ap.add_argument("--out", default="service_map.html", help="output HTML report")
    ap.add_argument("--title", default="Service Dependency Map")
    args = ap.parse_args()
    run(args.asts, args.config, args.out, title=args.title)


if __name__ == "__main__":
    main()
