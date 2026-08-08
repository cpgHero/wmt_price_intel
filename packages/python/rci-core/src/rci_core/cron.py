"""Small deterministic five-field cron evaluator with IANA timezone support."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class CronExpressionError(ValueError):
    pass


def _field_values(field: str, minimum: int, maximum: int, *, sunday: bool = False) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        if not part:
            raise CronExpressionError("cron lists cannot contain empty values")
        base, separator, step_text = part.partition("/")
        try:
            step = int(step_text) if separator else 1
        except ValueError as exc:
            raise CronExpressionError(f"invalid cron step {part!r}") from exc
        if step <= 0:
            raise CronExpressionError("cron steps must be positive")
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as exc:
                raise CronExpressionError(f"invalid cron range {base!r}") from exc
        else:
            try:
                start = int(base)
                end = maximum if separator else start
            except ValueError as exc:
                raise CronExpressionError(f"invalid cron value {base!r}") from exc
        if start < minimum or start > maximum or end < minimum or end > maximum or start > end:
            raise CronExpressionError(f"cron value {part!r} is outside {minimum}..{maximum}")
        parsed = set(range(start, end + 1, step))
        values.update(0 if sunday and value == 7 else value for value in parsed)
    return values


class CronSchedule:
    def __init__(self, expression: str, timezone: str) -> None:
        fields = expression.split()
        if len(fields) != 5:
            raise CronExpressionError("cron expressions require five fields")
        self.expression = expression
        try:
            self.timezone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise CronExpressionError(f"unknown timezone {timezone!r}") from exc
        self.minutes = _field_values(fields[0], 0, 59)
        self.hours = _field_values(fields[1], 0, 23)
        self.days = _field_values(fields[2], 1, 31)
        self.months = _field_values(fields[3], 1, 12)
        self.weekdays = _field_values(fields[4], 0, 7, sunday=True)
        self._day_wildcard = fields[2] == "*"
        self._weekday_wildcard = fields[4] == "*"

    def matches(self, instant: datetime) -> bool:
        if instant.tzinfo is None:
            raise CronExpressionError("cron instants must be timezone-aware")
        local = instant.astimezone(self.timezone)
        weekday = (local.weekday() + 1) % 7
        day_matches = local.day in self.days
        weekday_matches = weekday in self.weekdays
        if self._day_wildcard:
            calendar_matches = weekday_matches
        elif self._weekday_wildcard:
            calendar_matches = day_matches
        else:
            calendar_matches = day_matches or weekday_matches
        return (
            local.minute in self.minutes
            and local.hour in self.hours
            and local.month in self.months
            and calendar_matches
        )

    def next_after(self, instant: datetime) -> datetime:
        if instant.tzinfo is None:
            raise CronExpressionError("cron instants must be timezone-aware")
        candidate = instant.astimezone(UTC).replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(5 * 366 * 24 * 60):
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)
        raise CronExpressionError("cron expression has no occurrence within five years")
