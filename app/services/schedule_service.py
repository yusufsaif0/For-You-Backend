from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument

from app.core.database import get_collection
from app.models.schedule import schedule_document
from app.schemas.schedule import ScheduleCreate, ScheduleRead, ScheduleUpdate


def _legacy_starts_at(date_value: object, time_value: object) -> datetime:
    """Convert documents written by the original date/start_time API contract."""
    date_text = str(date_value or "")
    time_text = str(time_value or "00:00")

    for date_format in ("%Y-%m-%d", "%d %b %Y", "%d/%m/%Y"):
        for time_format in ("%H:%M", "%I:%M %p"):
            try:
                return datetime.strptime(f"{date_text} {time_text}", f"{date_format} {time_format}").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue

    # Retain a readable response for an old malformed record instead of failing
    # the entire collection request. New records always provide starts_at.
    return datetime.now(timezone.utc)


def _to_schedule_read(document: dict) -> ScheduleRead:
    """Map both current and legacy MongoDB documents to the public API schema."""
    schedule = dict(document)
    now = datetime.now(timezone.utc)

    schedule["id"] = str(schedule.pop("_id"))
    if not schedule.get("starts_at"):
        schedule["starts_at"] = _legacy_starts_at(schedule.get("date"), schedule.get("start_time"))
    schedule.setdefault("created_at", now)
    schedule.setdefault("updated_at", schedule["created_at"])
    # MongoDB stores UTC instants and older clients return naive UTC datetimes.
    # Always include the UTC offset in JSON so phones do not interpret them as local time.
    schedule.setdefault("reminder_at", None)
    for field in ("starts_at", "reminder_at", "created_at", "updated_at"):
        value = schedule[field]
        if isinstance(value, datetime):
            if value.tzinfo is None:
                schedule[field] = value.replace(tzinfo=timezone.utc)
            else:
                schedule[field] = value.astimezone(timezone.utc)

    return ScheduleRead.model_validate(schedule)


class ScheduleService:
    collection_name = "schedules"

    @property
    def collection(self):
        return get_collection(self.collection_name)

    async def create(self, schedule: ScheduleCreate, user_id: str) -> ScheduleRead:
        now = datetime.now(timezone.utc)
        document = schedule_document(schedule, now)
        document["user_id"] = user_id
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return _to_schedule_read(document)

    @staticmethod
    def object_id(schedule_id: str) -> ObjectId:
        if not ObjectId.is_valid(schedule_id):
            raise HTTPException(status_code=400, detail="Invalid schedule ID.")
        return ObjectId(schedule_id)

    async def update(self, schedule_id: str, changes: ScheduleUpdate, user_id: str) -> ScheduleRead:
        updates = changes.model_dump(exclude_unset=True)
        object_id = self.object_id(schedule_id)
        ownership = {"_id": object_id, "user_id": user_id}
        existing = await self.collection.find_one(ownership)
        if existing is None:
            raise HTTPException(status_code=404, detail="This schedule no longer exists. Refresh the list.")
        candidate = {**existing, **updates}
        if not candidate.get("starts_at"):
            candidate["starts_at"] = _legacy_starts_at(candidate.get("date"), candidate.get("start_time"))
        for field in ("_id", "created_at", "updated_at", "date", "start_time"):
            candidate.pop(field, None)
        ScheduleCreate.model_validate(candidate)
        updates["updated_at"] = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            ownership,
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise HTTPException(status_code=404, detail="This schedule no longer exists. Refresh the list.")
        return _to_schedule_read(document)

    async def delete(self, schedule_id: str, user_id: str) -> None:
        result = await self.collection.delete_one({"_id": self.object_id(schedule_id), "user_id": user_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="This schedule no longer exists. Refresh the list.")

    async def list(self, scheduled_for: datetime | None = None, user_id: str = "") -> list[ScheduleRead]:
        query = {"user_id": user_id}
        if scheduled_for:
            start = scheduled_for.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
            query["starts_at"] = {"$gte": start, "$lt": end}

        schedules: list[ScheduleRead] = []
        cursor = self.collection.find(query).sort("starts_at", 1)
        async for document in cursor:
            schedules.append(_to_schedule_read(document))
        return sorted(schedules, key=lambda schedule: schedule.starts_at)


schedule_service = ScheduleService()
