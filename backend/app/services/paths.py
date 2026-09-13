from __future__ import annotations

import os
import re
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._\- ()\u00C0-\u024F]")


class UnsafePathError(ValueError):
    pass


def safe_filename(name: str, fallback: str = "document") -> str:
    base = os.path.basename(name.replace("\\", "/"))
    cleaned = _UNSAFE.sub("_", base).strip(" .")
    if not cleaned or cleaned in {".", ".."}:
        return fallback
    return cleaned[:240]


def safe_relpath(value: str) -> str:
    normalized = value.replace("\\", "/").lstrip("/")
    parts: list[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == ".." or part.startswith(".."):
            raise UnsafePathError("path traversal rejected")
        parts.append(safe_filename(part))
    return "/".join(parts)


def resolve_under(root: Path, relpath: str) -> Path:
    root = root.resolve()
    if os.path.islink(root):
        raise UnsafePathError("storage root must not be a symlink")
    relative = safe_relpath(relpath)
    target = (root / relative).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("path escapes storage root") from exc
    if target.exists() and target.is_symlink():
        raise UnsafePathError("symlink escape rejected")
    return target


def content_addressed_relpath(sha256: str, filename: str) -> str:
    safe = safe_filename(filename)
    return f"{sha256[:2]}/{sha256[2:4]}/{sha256}-{safe}"
