"""Resolved calls → ServiceEdges, plus coverage stats and cycle detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from code_intelligence.index import ResolutionIndex
from code_intelligence.model import OutboundCall, ServiceEdge
from code_intelligence.resolve import resolve_call


@dataclass
class Aggregation:
    edges: dict[tuple[str, str], ServiceEdge] = field(default_factory=dict)
    total_calls: int = 0
    resolved_calls: int = 0
    unresolved: list[str] = field(default_factory=list)   # "file:line method url"
    conflicts: list[str] = field(default_factory=list)     # human-readable findings

    @property
    def coverage(self) -> float:
        return self.resolved_calls / self.total_calls if self.total_calls else 0.0


def build_edges(calls: Iterable[OutboundCall], idx: ResolutionIndex) -> Aggregation:
    agg = Aggregation()
    for call in calls:
        agg.total_calls += 1
        src = idx.service_for_file(call.from_file) or "(unknown-caller)"
        res = resolve_call(call, idx)
        if not res.resolved or not res.to_service:
            agg.unresolved.append(f"{call.from_file}:{call.line} {call.method} {call.raw_url}")
            continue
        if res.to_service == src:
            continue   # self-call; not an inter-service edge
        agg.resolved_calls += 1
        key = (src, res.to_service)
        e = agg.edges.get(key)
        if e is None:
            e = ServiceEdge(from_service=src, to_service=res.to_service)
            agg.edges[key] = e
        e.weight += 1
        e.confidence = max(e.confidence, res.confidence)
        e.strategies.add(res.strategy)
        if len(e.examples) < 5:
            e.examples.append(f"{call.from_file}:{call.line} {call.method} {call.raw_url}")
        if res.conflicts:
            agg.conflicts.append(
                f"{call.from_file}:{call.line} resolved to '{res.to_service}' "
                f"({res.strategy}) but also matched {res.conflicts}")
    return agg


def find_cycles(agg: Aggregation) -> list[list[str]]:
    """Return dependency cycles (the headline architectural finding). Tarjan SCCs;
    any SCC with >1 node, or a self-loop, is a cycle."""
    graph: dict[str, set[str]] = {}
    for (a, b) in agg.edges:
        graph.setdefault(a, set()).add(b)
        graph.setdefault(b, set())

    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    idx_of: dict[str, int] = {}
    low: dict[str, int] = {}
    sccs: list[list[str]] = []

    def strongconnect(v: str):
        nonlocal index
        idx_of[v] = low[v] = index
        index += 1
        stack.append(v); on_stack.add(v)
        for w in graph.get(v, ()):
            if w not in idx_of:
                strongconnect(w)
                low[v] = min(low[v], low[w])
            elif w in on_stack:
                low[v] = min(low[v], idx_of[w])
        if low[v] == idx_of[v]:
            comp = []
            while True:
                w = stack.pop(); on_stack.discard(w); comp.append(w)
                if w == v:
                    break
            sccs.append(comp)

    for v in list(graph):
        if v not in idx_of:
            strongconnect(v)
    return [c for c in sccs if len(c) > 1]
