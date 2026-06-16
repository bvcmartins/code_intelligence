"""Streaming + deserialization for both inputs: tree-sitter ASTs and config files.

  ┌──────────────────────────────────────────────────────────────────────┐
  │  >>> SCHEMA ADAPTER  <<<                                                │
  │  `to_cst_node` is the only place that knows your tree-sitter JSON shape.│
  │  Point it at one real sample on the workstation. (Same contract as     │
  │  codegraph/ingest.py — copy your tuned version over if you already did  │
  │  it there.)                                                            │
  └──────────────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Iterator, Optional, Any

try:
    import orjson as _json
    def _loads(b: bytes) -> Any: return _json.loads(b)
except ImportError:
    import json as _json
    def _loads(b: bytes) -> Any: return _json.loads(b)


# --- normalized tree-sitter node (generic across grammars) ---------------------

@dataclass(slots=True)
class CstNode:
    type: str
    start_byte: int
    end_byte: int
    start_line: int
    end_line: int
    text: Optional[str]
    children: list["CstNode"] = field(default_factory=list)
    fields: dict[str, "CstNode"] = field(default_factory=dict)

    def child_by_field(self, name: str) -> Optional["CstNode"]:
        return self.fields.get(name)

    def first_child_of_type(self, t: str) -> Optional["CstNode"]:
        for c in self.children:
            if c.type == t:
                return c
        return None

    def walk(self) -> Iterator["CstNode"]:
        stack = [self]
        while stack:
            n = stack.pop()
            yield n
            stack.extend(reversed(n.children))


# --- SCHEMA ADAPTER: tree-sitter JSON field names ------------------------------
KEY_TYPE = "type"
KEY_CHILDREN = "children"
KEY_TEXT = "text"               # None if your dump stores no source text
KEY_START_BYTE = "start_byte"
KEY_END_BYTE = "end_byte"
KEY_START_POINT = "start_point"  # expected [row, col]
KEY_END_POINT = "end_point"
KEY_FIELD_NAME = "field"          # per-child field label, if present (else None)


def to_cst_node(raw: dict) -> CstNode:
    """>>> ADAPT ME <<< — normalize one raw tree-sitter JSON dict recursively."""
    sp = raw.get(KEY_START_POINT) or [0, 0]
    ep = raw.get(KEY_END_POINT) or [0, 0]
    node = CstNode(
        type=raw.get(KEY_TYPE, "ERROR"),
        start_byte=int(raw.get(KEY_START_BYTE, 0)),
        end_byte=int(raw.get(KEY_END_BYTE, 0)),
        start_line=int(sp[0]), end_line=int(ep[0]),
        text=raw.get(KEY_TEXT) if KEY_TEXT else None,
    )
    for rc in raw.get(KEY_CHILDREN, []) or []:
        child = to_cst_node(rc)
        node.children.append(child)
        if KEY_FIELD_NAME and rc.get(KEY_FIELD_NAME):
            node.fields[rc[KEY_FIELD_NAME]] = child
    return node


@dataclass(slots=True)
class ParsedFile:
    src_path: str
    lang: str
    root: CstNode


# --- streaming sources (GCS or local) -----------------------------------------

def iter_blobs(source: str, suffixes: tuple[str, ...]) -> Iterator[tuple[str, bytes]]:
    """Yield (relative_path, bytes) for files under a gs:// prefix or local dir."""
    if source.startswith("gs://"):
        from google.cloud import storage
        bucket_name, _, prefix = source[len("gs://"):].partition("/")
        client = storage.Client()
        for blob in client.list_blobs(client.bucket(bucket_name), prefix=prefix):
            if blob.name.endswith(suffixes):
                rel = blob.name[len(prefix):].lstrip("/") if prefix else blob.name
                yield rel, blob.download_as_bytes()
    else:
        for dp, _, files in os.walk(source):
            for fn in files:
                if fn.endswith(suffixes):
                    p = os.path.join(dp, fn)
                    with open(p, "rb") as fh:
                        yield os.path.relpath(p, source), fh.read()


def load_asts(source: str) -> Iterator[ParsedFile]:
    """Stream tree-sitter JSON → ParsedFiles. See codegraph notes on recovering the
    original source path / language (mirror whatever you settled on there)."""
    from config.languages_min import lang_for_path  # tiny ext→lang map (see below)
    for json_path, data in iter_blobs(source, (".json",)):
        raw = _loads(data)
        if isinstance(raw, dict) and "tree" in raw:        # metadata-wrapped
            src_path = raw.get("path", json_path)
            lang = raw.get("lang") or lang_for_path(src_path) or "unknown"
            tree = raw["tree"]
        else:                                               # json mirrors source path
            src_path = json_path[:-5] if json_path.endswith(".json") else json_path
            lang = lang_for_path(src_path) or "unknown"
            tree = raw
        if lang == "unknown":
            continue
        yield ParsedFile(src_path=src_path, lang=lang, root=to_cst_node(tree))


@dataclass(slots=True)
class ConfigFile:
    path: str
    kind: str           # "openapi" | "gateway" | "registry" | "env" | "unknown"
    data: Any           # parsed YAML/JSON (dict/list) or raw text for env files
    raw: bytes


def load_configs(source: str) -> Iterator[ConfigFile]:
    """Stream config files and classify them. Classification is heuristic — refine
    `classify_config` for your repo's conventions."""
    import yaml
    for path, data in iter_blobs(source, (".yaml", ".yml", ".json", ".env", ".properties")):
        kind = classify_config(path, data)
        parsed: Any
        try:
            if path.endswith((".yaml", ".yml")):
                parsed = yaml.safe_load(data)
            elif path.endswith(".json"):
                parsed = _loads(data)
            else:
                parsed = data.decode("utf-8", "replace")   # env/properties: raw text
        except Exception:
            parsed = None
        yield ConfigFile(path=path, kind=kind, data=parsed, raw=data)


def classify_config(path: str, data: bytes) -> str:
    """>>> ADAPT ME <<< — route each config file to one of the four source parsers.

    Heuristics below are starting points; tune to your repo (filenames, k8s `kind:`,
    `openapi:`/`swagger:` keys, gateway CRDs, etc.)."""
    p = path.lower()
    head = data[:4096].lower()
    if p.endswith((".env",)) or "properties" in p:
        return "env"
    if b"openapi" in head or b"swagger" in head:
        return "openapi"
    if any(k in head for k in (b"virtualservice", b"ingress", b"httproute",
                               b"kongplugin", b"apisixroute", b"gateway")):
        return "gateway"
    if any(k in head for k in (b"kind: service", b"kind: deployment",
                               b"helm", b"consul")):
        return "registry"
    return "unknown"
