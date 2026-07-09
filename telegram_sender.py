"""
텔레그램 메시지 전송 (Dart-alert-bot 패턴: HTML, retry, 분할 전송)
"""
from __future__ import annotations

import logging
import time

import requests

import config

logger = logging.getLogger(__name__)


class TelegramSender:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID
        if not self.token or not self.chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID 미설정")
        self.base = f"https://api.telegram.org/bot{self.token}"
        self.session = requests.Session()

    def send_message(self, text: str, max_retries: int = 3) -> bool:
        """HTML 포맷 메시지 전송. 실패 시 최대 3회 재시도."""
        url = f"{self.base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        for attempt in range(max_retries):
            try:
                r = self.session.post(url, json=payload, timeout=10)
                if r.status_code == 200:
                    return True
                elif r.status_code == 429:
                    retry_after = r.json().get("parameters", {}).get("retry_after", 5)
                    logger.warning("텔레그램 rate limit. %s초 대기", retry_after)
                    time.sleep(retry_after)
                else:
                    logger.warning("텔레그램 전송 실패 %s: %s", r.status_code, r.text[:200])
            except Exception as e:
                logger.warning("텔레그램 전송 예외 (%s/%s): %s", attempt + 1, max_retries, e)

            if attempt < max_retries - 1:
                time.sleep(2)

        return False

    def send_error(self, error_msg: str) -> bool:
        """에러 알림 ([ERROR] earnings-dip: ...)."""
        return self.send_message(f"[ERROR] earnings-dip: <code>{error_msg[:500]}</code>")

    def send_long_message(self, text: str, max_len: int = 4000) -> bool:
        """긴 메시지를 max_len 단위로 분할 전송. 모두 성공 시 True."""
        if len(text) <= max_len:
            return self.send_message(text)

        chunks: list[str] = []
        remaining = text
        while remaining:
            if len(remaining) <= max_len:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, max_len)
            if split_at < max_len // 2:
                split_at = max_len
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")

        ok = True
        for i, chunk in enumerate(chunks):
            if not self.send_message(chunk):
                ok = False
            if i < len(chunks) - 1:
                time.sleep(0.4)
        return ok
