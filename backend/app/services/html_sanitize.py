from __future__ import annotations

import nh3

_ALLOWED_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "i",
    "li",
    "ol",
    "p",
    "pre",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}

_ALLOWED_ATTRS = {
    "a": {"href"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}

_ALLOWED_URL = {"https", "http", "mailto"}


def sanitize_email_html(html: str) -> str:
    """Strip scripts, styles, remote images, and active content."""
    cleaned = nh3.clean(
        html or "",
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes=_ALLOWED_URL,
        strip_comments=True,
        link_rel="noopener noreferrer",
    )
    # Images are omitted from the allow-list so remote/active content never renders.
    return cleaned


def html_to_text(html: str) -> str:
    cleaned = sanitize_email_html(html)
    text = nh3.clean(cleaned, tags=set(), attributes={})
    return " ".join(text.split())
