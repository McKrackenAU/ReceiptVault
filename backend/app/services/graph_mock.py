from __future__ import annotations

from email.message import EmailMessage
from hashlib import sha256

MOCK_IDENTITIES = {
    "hotmail-one": {
        "id": "mock-hotmail-1",
        "mail": "owner.one@hotmail.com",
        "displayName": "Owner One",
        "account_type": "personal",
    },
    "hotmail-two": {
        "id": "mock-hotmail-2",
        "mail": "owner.two@hotmail.com",
        "displayName": "Owner Two",
        "account_type": "personal",
    },
    "outlook-work": {
        "id": "mock-outlook-1",
        "mail": "owner@outlook.com",
        "displayName": "Owner Outlook",
        "account_type": "personal",
    },
}


def _eml(subject: str, sender: str, body: str, filename: str, attachment: bytes, mid: str) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = "owner@localhost"
    msg["Subject"] = subject
    msg["Message-ID"] = mid
    msg["Date"] = "Fri, 12 Jul 2024 10:15:00 +1000"
    msg.set_content(body)
    msg.add_attachment(attachment, maintype="application", subtype="pdf", filename=filename)
    return msg.as_bytes()


_RECEIPT_PDF = b"""%PDF-1.4
1 0 obj<<>>endobj
2 0 obj<< /Length 120 >>stream
BT /F1 12 Tf 72 720 Td (From: Office Supplies Co) Tj 0 -16 Td (ABN: 12 345 678 901) Tj
0 -16 Td (Tax Invoice INV-1001) Tj 0 -16 Td (Date: 12/07/2024) Tj
0 -16 Td (Notebook 1 x $20.00 $20.00) Tj 0 -16 Td (Subtotal $20.00) Tj
0 -16 Td (GST $2.00) Tj 0 -16 Td (Total AUD $22.00) Tj ET
endstream
endobj
trailer<<>>
%%EOF
"""


def messages_for(identity: str) -> list[dict]:
    profile = MOCK_IDENTITIES[identity]
    pdf = _RECEIPT_PDF
    body_html = """<html><body><h1>Tax Invoice</h1><p>From: Cloud Hosting Pty Ltd</p>
    <p>ABN: 98 765 432 109</p><p>INV-2044 15/08/2024</p>
    <p>Hosting 1 x $110.00</p><p>GST $10.00</p><p>Total AUD $110.00</p>
    <script>alert(1)</script><img src="https://evil.example/pixel.gif"></body></html>"""
    eml1 = _eml(
        "Your tax invoice INV-1001",
        "billing@officesupplies.example",
        "Please find attached your tax invoice. Total AUD $22.00 GST included.",
        "invoice-1001.pdf",
        pdf,
        "<inv-1001@officesupplies.example>",
    )
    return [
        {
            "id": f"{identity}-msg-1",
            "internetMessageId": "<inv-1001@officesupplies.example>",
            "subject": "Your tax invoice INV-1001",
            "from": {"emailAddress": {"address": "billing@officesupplies.example", "name": "Office Supplies"}},
            "toRecipients": [{"emailAddress": {"address": profile["mail"]}}],
            "receivedDateTime": "2024-07-12T00:15:00Z",
            "sentDateTime": "2024-07-12T00:14:00Z",
            "body": {"contentType": "text", "content": "Please find attached your tax invoice. Total AUD $22.00"},
            "hasAttachments": True,
            "parentFolderId": "inbox",
            "mime": eml1,
            "attachments": [
                {
                    "id": f"{identity}-att-1",
                    "name": "invoice-1001.pdf",
                    "contentType": "application/pdf",
                    "contentBytes": pdf,
                    "size": len(pdf),
                }
            ],
        },
        {
            "id": f"{identity}-msg-2",
            "internetMessageId": f"<body-{identity}@cloudhost.example>",
            "subject": "Receipt for hosting",
            "from": {"emailAddress": {"address": "accounts@cloudhost.example", "name": "Cloud Hosting"}},
            "toRecipients": [{"emailAddress": {"address": profile["mail"]}}],
            "receivedDateTime": "2024-08-15T04:00:00Z",
            "sentDateTime": "2024-08-15T03:59:00Z",
            "body": {"contentType": "html", "content": body_html},
            "hasAttachments": False,
            "parentFolderId": "inbox",
            "mime": body_html.encode(),
            "attachments": [],
        },
        {
            "id": f"{identity}-msg-3",
            "internetMessageId": f"<promo-{identity}@shop.example>",
            "subject": "Weekend sale!",
            "from": {"emailAddress": {"address": "hello@shop.example", "name": "Shop"}},
            "toRecipients": [{"emailAddress": {"address": profile["mail"]}}],
            "receivedDateTime": "2024-09-01T01:00:00Z",
            "sentDateTime": "2024-09-01T01:00:00Z",
            "body": {"contentType": "text", "content": "Come visit our store this weekend."},
            "hasAttachments": False,
            "parentFolderId": "inbox",
            "mime": b"From: hello@shop.example\nSubject: Weekend sale!\nMessage-ID: <promo>\n\nCome visit.",
            "attachments": [],
        },
    ]


def folders() -> list[dict]:
    return [
        {"id": "inbox", "displayName": "Inbox", "wellKnownName": "inbox"},
        {"id": "archive", "displayName": "Archive", "wellKnownName": "archive"},
        {"id": "sentitems", "displayName": "Sent Items", "wellKnownName": "sentitems"},
    ]


def message_digest(payload: bytes) -> str:
    return sha256(payload).hexdigest()
