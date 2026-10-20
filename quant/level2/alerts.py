"""Telegram notifications using environment-provided credentials only."""
from __future__ import annotations
import json
import os
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

class TelegramAlerts:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None, timeout: float = 8.0):
        self.token = token if token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = chat_id if chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")
        self.timeout = timeout

    @property
    def enabled(self) -> bool: return bool(self.token and self.chat_id)

    def send(self, message: str) -> bool:
        if not self.enabled or not message.strip(): return False
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        body = urlencode({"chat_id": self.chat_id, "text": message, "disable_web_page_preview": "true"}).encode()
        request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return 200 <= response.status < 300 and payload.get("ok") is True
        except (HTTPError, URLError, TimeoutError, ValueError, OSError): return False
