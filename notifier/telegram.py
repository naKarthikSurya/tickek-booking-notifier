"""Minimal Telegram Bot API client (stdlib only)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


class Telegram:
    def __init__(self, token: str, chat_id: str):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = str(chat_id)

    def _call(self, method: str, params: dict) -> dict:
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(f"{self.base}/{method}", data=data, timeout=30) as r:
            return json.loads(r.read().decode())

    def send(self, text: str) -> None:
        # Telegram caps messages at 4096 chars; split on line boundaries.
        chunk = ""
        for line in text.splitlines(keepends=True):
            if len(chunk) + len(line) > 3900:
                self._send_one(chunk)
                chunk = ""
            chunk += line
        if chunk.strip():
            self._send_one(chunk)

    def _send_one(self, text: str) -> None:
        self._call("sendMessage", {
            "chat_id": self.chat_id, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        })

    def new_messages(self, offset: int) -> tuple[list[str], int]:
        """Texts the user sent to the bot since `offset`, plus the next offset."""
        res = self._call("getUpdates", {"offset": offset, "timeout": 0})
        texts = []
        for u in res.get("result", []):
            offset = max(offset, u["update_id"] + 1)
            msg = u.get("message") or {}
            if str((msg.get("chat") or {}).get("id")) == self.chat_id:
                texts.append(msg.get("text") or "")
        return texts, offset
