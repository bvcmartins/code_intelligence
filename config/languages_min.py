"""Minimal extension→language map (the four targeted languages)."""
from __future__ import annotations
import os

EXT_TO_LANG = {
    ".py": "python",
    ".java": "java",
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
}


def lang_for_path(path: str) -> str | None:
    return EXT_TO_LANG.get(os.path.splitext(path)[1].lower())
