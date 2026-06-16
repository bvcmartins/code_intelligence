"""Self-contained HTML report: the diagram + dependency matrix + coverage/findings.

This is the shareable deliverable. It embeds the rendered SVG inline (so the file
stands alone), a rows-depend-on-columns matrix, a coverage banner, a cycles
section, a config-conflict section, and the unresolved-calls appendix.
"""
from __future__ import annotations

import html

from code_intelligence.aggregate import Aggregation, find_cycles


def _matrix(agg: Aggregation) -> str:
    svcs = sorted({n for e in agg.edges for n in e})
    if not svcs:
        return "<p>No service edges resolved.</p>"
    head = "".join(f"<th>{html.escape(s)}</th>" for s in svcs)
    rows = []
    for a in svcs:
        cells = []
        for b in svcs:
            e = agg.edges.get((a, b))
            cells.append(f'<td class="hit">{e.weight}</td>' if e else "<td></td>")
        rows.append(f"<tr><th>{html.escape(a)}</th>{''.join(cells)}</tr>")
    return (f'<table class="matrix"><thead><tr><th>from \\ to</th>{head}</tr></thead>'
            f'<tbody>{"".join(rows)}</tbody></table>')


def build_html(agg: Aggregation, svg_path: str | None,
               title: str = "Service Dependency Map") -> str:
    cycles = find_cycles(agg)
    svg_inline = ""
    if svg_path:
        try:
            with open(svg_path) as fh:
                svg_inline = fh.read()
        except OSError:
            svg_inline = "<p><em>diagram render unavailable</em></p>"

    cov = agg.coverage * 100
    cov_class = "good" if cov >= 80 else "warn" if cov >= 50 else "bad"

    cycles_html = ("".join(f"<li>{' → '.join(html.escape(s) for s in c)} → "
                           f"{html.escape(c[0])}</li>" for c in cycles)
                   or "<li>None detected 🎉</li>")
    conflicts_html = ("".join(f"<li>{html.escape(c)}</li>" for c in agg.conflicts[:200])
                      or "<li>None.</li>")
    unresolved_html = ("".join(f"<li>{html.escape(u)}</li>" for u in agg.unresolved[:500])
                       or "<li>None 🎉</li>")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>{html.escape(title)}</title>
<style>
 body {{ font-family: Helvetica, Arial, sans-serif; margin: 0; color:#1f2933; }}
 header {{ background:#1f2933; color:#fff; padding:24px 32px; }}
 header h1 {{ margin:0; font-size:22px; }}
 main {{ padding: 24px 32px; max-width: 1100px; }}
 .cov {{ display:inline-block; padding:6px 12px; border-radius:6px; font-weight:bold; }}
 .cov.good {{ background:#def7e5; color:#1b7f3b; }}
 .cov.warn {{ background:#fff4d6; color:#8a6d00; }}
 .cov.bad  {{ background:#fde8e8; color:#b42318; }}
 section {{ margin: 28px 0; }}
 h2 {{ border-bottom:2px solid #e4e7eb; padding-bottom:6px; }}
 .diagram svg {{ max-width:100%; height:auto; border:1px solid #e4e7eb; border-radius:8px; }}
 table.matrix {{ border-collapse: collapse; font-size:12px; }}
 table.matrix th, table.matrix td {{ border:1px solid #e4e7eb; padding:4px 8px; text-align:center; }}
 table.matrix td.hit {{ background:#eef3fb; font-weight:bold; }}
 ul.findings li {{ margin:3px 0; font-family: ui-monospace, monospace; font-size:12px; }}
 .muted {{ color:#7b8794; font-size:13px; }}
</style></head><body>
<header><h1>{html.escape(title)}</h1>
<p class="muted">Discovered from API paths (route definitions ↔ outbound calls),
resolved via env → registry → gateway → OpenAPI. Edges are code/network call
dependencies, not imports.</p></header>
<main>
 <section>
   <span class="cov {cov_class}">{cov:.0f}% of outbound calls resolved</span>
   <span class="muted">&nbsp;{agg.resolved_calls}/{agg.total_calls} calls ·
   {len(agg.edges)} service edges · {len(cycles)} cycles ·
   {len(agg.conflicts)} conflicts · {len(agg.unresolved)} unresolved</span>
 </section>
 <section class="diagram"><h2>Service dependency diagram</h2>{svg_inline}</section>
 <section><h2>Dependency matrix (rows depend on columns)</h2>{_matrix(agg)}</section>
 <section><h2>Dependency cycles</h2><ul class="findings">{cycles_html}</ul></section>
 <section><h2>Config / routing conflicts</h2><ul class="findings">{conflicts_html}</ul></section>
 <section><h2>Unresolved calls (appendix)</h2>
   <p class="muted">Calls whose target could not be resolved to a service — usually
   fully-dynamic URLs, missing config, or untracked integrations.</p>
   <ul class="findings">{unresolved_html}</ul></section>
</main></body></html>"""
