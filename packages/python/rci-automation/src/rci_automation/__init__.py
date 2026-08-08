"""Scheduling, history, alert, and delivery capabilities."""

from rci_automation.email import SMTPEmailSender, SMTPSettings, UnavailableEmailSender
from rci_automation.memory import InMemoryAutomationRepository, RecordingEmailSender
from rci_automation.repository import PostgresAutomationRepository
from rci_automation.service import AutomationService

__all__ = [
    "AutomationService",
    "InMemoryAutomationRepository",
    "PostgresAutomationRepository",
    "RecordingEmailSender",
    "SMTPEmailSender",
    "SMTPSettings",
    "UnavailableEmailSender",
]
