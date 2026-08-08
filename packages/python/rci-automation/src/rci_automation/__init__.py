"""Scheduling, history, alert, and delivery capabilities."""

from rci_automation.email import (
    FakeEmailSender,
    SMTPEmailSender,
    SMTPSettings,
    UnavailableEmailSender,
    email_sender_from_env,
)
from rci_automation.memory import InMemoryAutomationRepository, RecordingEmailSender
from rci_automation.repository import PostgresAutomationRepository
from rci_automation.service import AutomationService

__all__ = [
    "AutomationService",
    "FakeEmailSender",
    "InMemoryAutomationRepository",
    "PostgresAutomationRepository",
    "RecordingEmailSender",
    "SMTPEmailSender",
    "SMTPSettings",
    "UnavailableEmailSender",
    "email_sender_from_env",
]
