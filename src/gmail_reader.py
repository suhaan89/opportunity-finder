"""Gmail-Newsletter lesen (Phase 3).

- NUR Lesezugriff (Scope gmail.readonly), NUR Mails mit einem bestimmten Label.
- Zugang über OAuth-Refresh-Token (GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / GMAIL_REFRESH_TOKEN).
- Mail-Inhalte werden NIE geloggt oder gespeichert. Sie gehen nur an Gemini, um Links zu Angeboten
  herauszusuchen (siehe collect.pick_links). Die Links werden danach wie alle anderen geprüft.
"""
from __future__ import annotations

import base64
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterator

import requests

from .verify import parse_html

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://gmail.googleapis.com/gmail/v1/users/me"
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


class GmailAuthError(Exception):
    """Anmeldung fehlgeschlagen (meist: Refresh-Token abgelaufen oder widerrufen, siehe SETUP_TODO.md)."""


@dataclass
class MailDoc:
    """Eine Mail, reduziert auf Text und Links (ohne Absender/Betreff)."""
    text: str
    links: list[tuple[str, str]] = field(default_factory=list)


def _decode(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")


def _parts(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Alle Teile einer Mail (verschachtelt) nacheinander."""
    yield payload
    for sub in payload.get("parts", []) or []:
        yield from _parts(sub)


def parse_message(msg: dict[str, Any], max_chars: int = 12000) -> MailDoc | None:
    """Macht aus einer Gmail-API-Nachricht (format=full) Text + Links. HTML wird bevorzugt."""
    html = plain = ""
    for part in _parts(msg.get("payload", {}) or {}):
        data = (part.get("body", {}) or {}).get("data")
        if not data:
            continue
        mime = part.get("mimeType", "")
        if mime == "text/html" and not html:
            html = _decode(data)
        elif mime == "text/plain" and not plain:
            plain = _decode(data)
    if html:
        _title, text, links = parse_html(html, "", max_chars)
        return MailDoc(text, links) if text else None
    if plain:
        links = [("", u.rstrip(".,;")) for u in _URL_RE.findall(plain)]
        return MailDoc(" ".join(plain.split())[:max_chars], links)
    return None


class GmailReader:
    def __init__(
        self, client_id: str, client_secret: str, refresh_token: str,
        session: Any = None, timeout: float = 30,
    ) -> None:
        self.client_id, self.client_secret, self.refresh_token = client_id, client_secret, refresh_token
        self.session = session or requests.Session()
        self.timeout = timeout
        self._access_token = ""

    @classmethod
    def from_env(cls) -> "GmailReader | None":
        """Erzeugt den Reader, wenn alle drei Werte gesetzt sind, sonst None."""
        vals = [os.environ.get(k, "").strip() for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")]
        return cls(*vals) if all(vals) else None

    def _token(self) -> str:
        if not self._access_token:
            resp = self.session.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id, "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token, "grant_type": "refresh_token",
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                raise GmailAuthError("Token konnte nicht erneuert werden")
            self._access_token = resp.json()["access_token"]
        return self._access_token

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = self.session.get(
            f"{API}/{path}", params=params, headers={"Authorization": f"Bearer {self._token()}"}, timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()

    def _label_id(self, name: str) -> str | None:
        for label in self._get("labels").get("labels", []):
            if label.get("name", "").lower() == name.lower():
                return label["id"]
        return None

    def fetch_documents(self, label: str, newer_than_days: int, max_messages: int) -> list[MailDoc]:
        """Holt die letzten Mails mit dem Label. Gibt [] zurück, wenn es das Label nicht gibt."""
        label_id = self._label_id(label)
        if label_id is None:
            return []
        listing = self._get(
            "messages",
            {"labelIds": label_id, "q": f"newer_than:{int(newer_than_days)}d", "maxResults": int(max_messages)},
        )
        docs: list[MailDoc] = []
        for item in listing.get("messages", [])[:max_messages]:
            doc = parse_message(self._get(f"messages/{item['id']}", {"format": "full"}))
            if doc:
                docs.append(doc)
        return docs
