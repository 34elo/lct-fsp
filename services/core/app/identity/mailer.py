"""Отправка писем по SMTP (E20-1). Пустой `SMTP_HOST` — письма не уходят."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Protocol

import structlog

from app.config import Settings

log = structlog.get_logger()


class Mailer(Protocol):
    async def send(self, to: str, subject: str, body: str) -> None: ...


class SmtpMailer:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    def _send_sync(self, msg: EmailMessage) -> None:
        s = self._s
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            if s.smtp_user:
                smtp.starttls()
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)

    async def send(self, to: str, subject: str, body: str) -> None:
        if not self._s.smtp_host:
            log.info("email.skipped", reason="smtp_not_configured")
            return
        msg = EmailMessage()
        msg["From"] = self._s.smtp_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        try:
            await asyncio.to_thread(self._send_sync, msg)
        except (OSError, smtplib.SMTPException) as exc:  # адрес в лог не пишем (ПДн)
            log.warning("email.send_failed", error=type(exc).__name__)
