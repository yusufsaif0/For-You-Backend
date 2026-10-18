from datetime import datetime, timezone
from typing import Any

from app.schemas.schedule import ScheduleCreate


def schedule_document(schedule: ScheduleCreate, now: datetime) -> dict[str, Any]:
    """Map an API creation payload to the MongoDB document shape."""
    # BSON datetimes have millisecond precision. Match it in the creation response.
    now = now.replace(microsecond=(now.microsecond // 1000) * 1000)
    starts_at = schedule.starts_at.astimezone(timezone.utc)
    document = {
        **schedule.model_dump(),
        "starts_at": starts_at.replace(microsecond=(starts_at.microsecond // 1000) * 1000),
        "created_at": now,
        "updated_at": now,
    }
    if schedule.reminder_at is not None:
        reminder_at = schedule.reminder_at.astimezone(timezone.utc)
        document["reminder_at"] = reminder_at.replace(microsecond=(reminder_at.microsecond // 1000) * 1000)
    return document
