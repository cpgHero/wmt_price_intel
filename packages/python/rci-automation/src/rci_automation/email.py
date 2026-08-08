"""SMTP delivery adapter with server-side environment configuration."""

from __future__ import annotations

import asyncio
import hashlib
import os
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from rci_automation.models import EmailDeliveryRecord


@dataclass(frozen=True, slots=True)
class SMTPSettings:
    host: str
    port: int
    sender: str
    username: str | None
    password: str | None
    starttls: bool

    @classmethod
    def from_env(cls) -> SMTPSettings:
        host = os.getenv("SMTP_HOST")
        sender = os.getenv("SMTP_FROM_EMAIL")
        if not host or not sender:
            raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL are required for email delivery")
        return cls(
            host=host,
            port=int(os.getenv("SMTP_PORT", "587")),
            sender=sender,
            username=os.getenv("SMTP_USERNAME"),
            password=os.getenv("SMTP_PASSWORD"),
            starttls=os.getenv("SMTP_STARTTLS", "true").strip().lower()
            in {"1", "true", "yes", "on"},
        )


class SMTPEmailSender:
    def __init__(self, settings: SMTPSettings) -> None:
        self._settings = settings

    async def send(self, delivery: EmailDeliveryRecord) -> str:
        return await asyncio.to_thread(self._send_sync, delivery)

    def _send_sync(self, delivery: EmailDeliveryRecord) -> str:
        message = EmailMessage()
        message["From"] = self._settings.sender
        message["To"] = ", ".join(delivery.recipients)
        message["Subject"] = delivery.subject
        message["X-RCI-Idempotency-Key"] = delivery.idempotency_key
        message.set_content(delivery.text_body)
        if delivery.html_body:
            message.add_alternative(delivery.html_body, subtype="html")
        with smtplib.SMTP(self._settings.host, self._settings.port, timeout=30) as client:
            if self._settings.starttls:
                client.starttls()
            if self._settings.username:
                client.login(self._settings.username, self._settings.password or "")
            refused = client.send_message(message)
        if refused:
            raise RuntimeError(f"SMTP refused {len(refused)} recipient(s)")
        return message.get("Message-ID") or hashlib.sha256(message.as_bytes()).hexdigest()


class FakeEmailSender:
    """Non-network sender for explicit acceptance and development environments."""

    async def send(self, delivery: EmailDeliveryRecord) -> str:
        digest = hashlib.sha256(delivery.idempotency_key.encode()).hexdigest()[:24]
        return f"fake-{digest}"


class UnavailableEmailSender:
    async def send(self, delivery: EmailDeliveryRecord) -> str:
        raise RuntimeError("SMTP delivery is not configured")


def email_sender_from_env() -> SMTPEmailSender | FakeEmailSender | UnavailableEmailSender:
    provider = os.getenv("EMAIL_PROVIDER", "auto").strip().lower()
    if provider == "fake":
        return FakeEmailSender()
    if provider == "unavailable":
        return UnavailableEmailSender()
    if provider == "smtp":
        return SMTPEmailSender(SMTPSettings.from_env())
    if provider == "auto":
        return (
            SMTPEmailSender(SMTPSettings.from_env())
            if os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM_EMAIL")
            else UnavailableEmailSender()
        )
    raise RuntimeError("EMAIL_PROVIDER must be one of auto, fake, unavailable, or smtp")
