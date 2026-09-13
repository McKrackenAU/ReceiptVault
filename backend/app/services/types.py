from __future__ import annotations

from dataclasses import dataclass

try:
    import magic
except ImportError:  # pragma: no cover
    magic = None

ACTIVE = {
    "application/x-msdownload",
    "application/x-executable",
    "application/x-dosexec",
    "application/x-sh",
    "application/javascript",
    "text/javascript",
    "application/x-msi",
    "application/vnd.microsoft.portable-executable",
}

PREVIEWABLE = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/tiff",
    "image/heic",
    "text/html",
    "text/plain",
    "message/rfc822",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

EXT_HINT = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".html": "text/html",
    ".htm": "text/html",
    ".eml": "message/rfc822",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
}


@dataclass
class DetectedType:
    media_type: str
    label: str


def sniff_magic(data: bytes) -> str | None:
    if not data:
        return "application/x-empty"
    if magic is None:
        return None
    try:
        return magic.from_buffer(data, mime=True)
    except Exception:
        return None


def sniff_signature(data: bytes) -> str | None:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] in {b"II*\x00", b"MM\x00*"}:
        return "image/tiff"
    if data[:4] == b"PK\x03\x04":
        if b"word/" in data[:4000]:
            return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if b"xl/" in data[:4000]:
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return "application/zip"
    if data.lower().lstrip().startswith(b"<!doctype html") or data.lower().lstrip().startswith(b"<html"):
        return "text/html"
    if b"From:" in data[:800] and b"Message-ID:" in data[:4000]:
        return "message/rfc822"
    return None


def detect_file_type(data: bytes, filename: str = "") -> DetectedType:
    sniffed = sniff_magic(data) or sniff_signature(data)
    ext = ""
    if "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()
    hinted = EXT_HINT.get(ext)
    media = sniffed or hinted or "application/octet-stream"
    # Never trust extension over a conflicting high-confidence sniff for executables.
    if sniffed in ACTIVE:
        media = sniffed
    return DetectedType(media_type=media, label=media)


def is_rejected_active(media_type: str, filename: str) -> bool:
    ext = filename.lower()
    return media_type in ACTIVE or ext.endswith((".exe", ".bat", ".cmd", ".msi", ".dll", ".js", ".vbs", ".ps1"))


def is_previewable(media_type: str) -> bool:
    return media_type in PREVIEWABLE
