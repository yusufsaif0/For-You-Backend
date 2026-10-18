from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument
from pydantic import ValidationError

from app.core.database import get_collection
from app.schemas.life_item import LifeItemCreate, LifeItemKind, LifeItemRead, LifeItemUpdate


def _read(document: dict) -> LifeItemRead:
    item = dict(document)
    item["id"] = str(item.pop("_id"))
    item.pop("user_id", None)
    return LifeItemRead.model_validate(item)


class LifeItemService:
    collection_name = "life_items"

    @property
    def collection(self):
        return get_collection(self.collection_name)

    async def create(self, item: LifeItemCreate, user_id: str) -> LifeItemRead:
        now = datetime.now(timezone.utc)
        document = item.model_dump()
        for field in ("occurred_at", "due_at", "starts_at", "reminder_at"):
            if document[field] is not None:
                document[field] = document[field].astimezone(timezone.utc)
        document.update(created_at=now, updated_at=now, user_id=user_id)
        result = await self.collection.insert_one(document)
        document["_id"] = result.inserted_id
        return _read(document)

    async def list(self, kind: LifeItemKind, user_id: str) -> list[LifeItemRead]:
        result = []
        cursor = self.collection.find({"kind": kind.value, "user_id": user_id}).sort(
            [("completed", 1), ("due_at", 1), ("starts_at", 1), ("occurred_at", -1)]
        )
        async for document in cursor:
            result.append(_read(document))
        return result

    @staticmethod
    def object_id(item_id: str) -> ObjectId:
        if not ObjectId.is_valid(item_id):
            raise HTTPException(status_code=400, detail="Invalid item ID.")
        return ObjectId(item_id)

    async def update(self, item_id: str, changes: LifeItemUpdate, user_id: str) -> LifeItemRead:
        object_id = self.object_id(item_id)
        updates = changes.model_dump(exclude_unset=True)
        ownership = {"_id": object_id, "user_id": user_id}
        existing = await self.collection.find_one(ownership)
        if existing is None:
            raise HTTPException(status_code=404, detail="This item no longer exists. Refresh the list.")
        candidate = {**existing, **updates}
        for field in ("_id", "created_at", "updated_at", "user_id"):
            candidate.pop(field, None)
        LifeItemCreate.model_validate(candidate)
        for field in ("occurred_at", "due_at", "starts_at", "reminder_at"):
            if field in updates and updates[field] is not None:
                updates[field] = updates[field].astimezone(timezone.utc)
        updates["updated_at"] = datetime.now(timezone.utc)
        document = await self.collection.find_one_and_update(
            ownership,
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        if document is None:
            raise HTTPException(status_code=404, detail="This item no longer exists. Refresh the list.")
        try:
            return _read(document)
        except ValidationError as error:
            raise HTTPException(status_code=422, detail="The update would make this item invalid.") from error

    async def delete(self, item_id: str, user_id: str) -> None:
        result = await self.collection.delete_one({"_id": self.object_id(item_id), "user_id": user_id})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="This item no longer exists. Refresh the list.")


life_item_service = LifeItemService()
