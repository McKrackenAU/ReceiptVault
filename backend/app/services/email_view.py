from __future__ import annotations

import html
from email import policy
from email.parser import BytesParser

from app.services.html_sanitize import sanitize_email_html


def parse_email_view(data: bytes) -> dict:
    msg = BytesParser(policy=policy.default).parsebytes(data)
    body_html = ""
    body_text = ""
    inline_attachments: list[dict] = []
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            disp = part.get_content_disposition()
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if disp == "attachment" or (filename and ctype not in {"text/html", "text/plain"}):
                inline_attachments.append(
                    {
                        "filename": filename or "attachment",
                        "media_type": ctype,
                        "bytes": len(payload),
                    }
                )
                continue
            if ctype == "text/html" and not body_html:
                body_html = _part_text(part, payload)
            elif ctype == "text/plain" and not body_text:
                body_text = _part_text(part, payload)
    else:
        ctype = msg.get_content_type()
        payload = msg.get_payload(decode=True) or b""
        if ctype == "text/html":
            body_html = _part_text(msg, payload)
        else:
            body_text = _part_text(msg, payload)
    sanitized = sanitize_email_html(body_html)
    if not sanitized and body_text:
        sanitized = f"<pre>{html.escape(body_text)}</pre>"
    return {
        "from": str(msg.get("from") or ""),
        "to": str(msg.get("to") or ""),
        "cc": str(msg.get("cc") or ""),
        "subject": str(msg.get("subject") or ""),
        "date": str(msg.get("date") or ""),
        "html": sanitized,
        "text": body_text,
        "eml_parts": inline_attachments,
    }


def _part_text(part, payload: bytes) -> str:
    try:
        content = part.get_content()
        return content if isinstance(content, str) else payload.decode("utf-8", "ignore")
    except Exception:
        return payload.decode("utf-8", "ignore")


def is_email_media(media_type: str, filename: str = "") -> bool:
    name = filename.lower()
    return media_type in {"message/rfc822", "message/rfc822; charset=utf-8"} or name.endswith(".eml")
