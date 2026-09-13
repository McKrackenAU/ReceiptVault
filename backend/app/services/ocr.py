from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

from app.services.parse import parse_receipt_text


def extract_pdf_text(data: bytes) -> tuple[str, float]:
    try:
        reader = PdfReader(Path_from_bytes(data))
    except Exception:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            tmp.write(data)
            tmp.flush()
            try:
                reader = PdfReader(tmp.name)
            except Exception:
                return "", 0.0
    texts = []
    for page in reader.pages:
        texts.append(page.extract_text() or "")
    text = "\n".join(texts).strip()
    quality = min(100.0, len(text) / 8)
    return text, quality


def Path_from_bytes(data: bytes):
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.write(data)
    tmp.flush()
    tmp.close()
    return tmp.name


def quality_sufficient(text: str, quality: float) -> bool:
    if quality >= 25 and len(text) >= 40:
        return True
    if len(re_words(text)) >= 12:
        return True
    return False


def re_words(text: str) -> list[str]:
    return [part for part in text.replace("\n", " ").split(" ") if part.strip()]


def run_ocr(data: bytes, filename: str) -> tuple[str, float, str]:
    if not shutil.which("ocrmypdf") or not shutil.which("tesseract"):
        text, quality = extract_pdf_text(data) if filename.lower().endswith(".pdf") or data[:4] == b"%PDF" else (data.decode("utf-8", "ignore"), 40.0)
        return text, quality, "builtin-text"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "in.pdf"
        dest = Path(tmp) / "out.pdf"
        if data[:4] != b"%PDF":
            # Image input: wrap via ocrmypdf image import if possible.
            src = Path(tmp) / "in.bin"
            src.write_bytes(data)
            cmd = ["ocrmypdf", "--force-ocr", "--deskew", "--rotate-pages", str(src), str(dest)]
        else:
            src.write_bytes(data)
            cmd = ["ocrmypdf", "--skip-text", "--deskew", "--rotate-pages", str(src), str(dest)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            text, quality = extract_pdf_text(dest.read_bytes())
            return text, max(quality, 50.0), "ocrmypdf+tesseract"
        except Exception:
            text, quality = extract_pdf_text(data)
            return text, quality, "fallback-text"


def extract_and_parse(data: bytes, filename: str) -> dict:
    text = ""
    quality = 0.0
    engine = "none"
    if data[:4] == b"%PDF" or filename.lower().endswith(".pdf"):
        text, quality = extract_pdf_text(data)
        engine = "pypdf"
        if not quality_sufficient(text, quality):
            text, quality, engine = run_ocr(data, filename)
    elif filename.lower().endswith((".html", ".htm")) or data.lower().lstrip().startswith(b"<"):
        from app.services.html_sanitize import html_to_text

        text = html_to_text(data.decode("utf-8", "ignore"))
        quality = 80.0
        engine = "html-text"
    else:
        try:
            text = data.decode("utf-8")
            quality = 70.0
            engine = "utf8"
        except UnicodeDecodeError:
            text, quality, engine = run_ocr(data, filename)
    parsed = parse_receipt_text(text)
    parsed["raw_text"] = text
    parsed["normalized_text"] = " ".join(text.split())
    parsed["ocr_confidence"] = quality
    parsed["engine_version"] = engine
    if quality < 35:
        parsed["validation_flags"] = list(parsed.get("validation_flags") or []) + ["low_ocr_confidence"]
    if not text.strip():
        parsed["validation_flags"] = list(parsed.get("validation_flags") or []) + ["unreadable_pages"]
    return parsed
