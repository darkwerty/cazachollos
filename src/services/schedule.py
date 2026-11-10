"""Active hours of the scheduled passes, in Madrid time (the cron of Azure Container Apps Jobs runs in UTC)."""

from datetime import datetime, timedelta, timezone


def _last_sunday(year: int, month: int) -> datetime:
    first_next = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc)
    d = first_next - timedelta(days=1)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def madrid_time(now: datetime | None = None) -> datetime:
    """Peninsular Spanish time without tzdata (the slim image does not ship it): EU summer time rule."""
    utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    start = _last_sunday(utc.year, 3).replace(hour=1)
    end = _last_sunday(utc.year, 10).replace(hour=1)
    return utc + timedelta(hours=2 if start <= utc < end else 1)


def within_active_hours(spec: str, now: datetime | None = None) -> bool:
    """spec "7-24": from 7:00 to 23:59 Madrid time. Empty spec: always."""
    if not spec.strip():
        return True
    start, _, end = spec.partition("-")
    hour = madrid_time(now).hour
    return int(start) <= hour < int(end or 24)
