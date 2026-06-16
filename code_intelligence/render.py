"""Graphviz rendering of the service-dependency graph.

Nodes = services; edge thickness ∝ call volume; cycle edges in red; low-confidence
edges dashed. Produces DOT text (always) and, if the `graphviz` package + system
`dot` are present, SVG/PDF.
"""
from __future__ import annotations

import math
from code_intelligence.aggregate import Aggregation, find_cycles


def _pen_width(weight: int) -> float:
    return round(1.0 + math.log1p(weight), 2)


def to_dot(agg: Aggregation, title: str = "Service Dependencies") -> str:
    cycles = find_cycles(agg)
    in_cycle = {s for c in cycles for s in c}
    cycle_edges = {(a, b) for c in cycles for a in c for b in c if (a, b) in agg.edges}

    lines = [
        "digraph services {",
        '  rankdir=LR;',
        f'  labelloc="t"; label="{title}";',
        '  node [shape=box, style="rounded,filled", fillcolor="#eef3fb", '
        'color="#4f83cc", fontname="Helvetica"];',
        '  edge [color="#888888", fontname="Helvetica", fontsize=9];',
    ]
    for s in sorted({n for e in agg.edges for n in e}):
        fill = "#fde8e8" if s in in_cycle else "#eef3fb"
        border = "#cc4f4f" if s in in_cycle else "#4f83cc"
        lines.append(f'  "{s}" [fillcolor="{fill}", color="{border}"];')
    for (a, b), e in sorted(agg.edges.items()):
        attrs = [f'penwidth={_pen_width(e.weight)}', f'label="{e.weight}"']
        if (a, b) in cycle_edges:
            attrs.append('color="#cc4f4f"')
        if e.confidence < 0.7:
            attrs.append('style=dashed')
        lines.append(f'  "{a}" -> "{b}" [{", ".join(attrs)}];')
    lines.append("}")
    return "\n".join(lines)


def render(agg: Aggregation, out_basename: str, fmt: str = "svg",
           title: str = "Service Dependencies") -> str | None:
    """Write DOT and try to render fmt (svg/pdf). Returns the rendered file path or
    None if graphviz isn't available (DOT is always written)."""
    dot = to_dot(agg, title)
    with open(f"{out_basename}.dot", "w") as fh:
        fh.write(dot)
    try:
        import graphviz
        src = graphviz.Source(dot)
        return src.render(out_basename, format=fmt, cleanup=True)
    except Exception as exc:   # graphviz pkg or system `dot` missing
        print(f"[render] graphviz unavailable ({exc}); wrote {out_basename}.dot only")
        return None
