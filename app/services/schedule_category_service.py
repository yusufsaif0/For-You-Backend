from hashlib import sha256

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import get_collection


DEFAULT_CATEGORIES = ("Workout", "Work", "Food", "Study", "Social", "Sleep")


class ScheduleCategoryService:
    @property
    def collection(self):
        return get_collection("schedule_categories")

    async def list(self, user_id: str) -> list[str]:
        cursor = self.collection.find({"user_id": user_id}).sort("name_key", 1)
        return [document["name"] async for document in cursor]

    async def create(self, name: str, user_id: str) -> str:
        name = " ".join(name.split())
        name_key = name.casefold()
        for default in DEFAULT_CATEGORIES:
            if default.casefold() == name_key:
                return default
        # A stable, unique ID makes repeated and concurrent saves idempotent.
        category_id = sha256(f"{user_id}\0{name_key}".encode()).hexdigest()
        ownership = {"_id": category_id, "user_id": user_id}
        try:
            document = await self.collection.find_one_and_update(
                ownership,
                {"$setOnInsert": {"name": name, "name_key": name_key, "user_id": user_id}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            document = await self.collection.find_one(ownership)
            if document is None:
                raise
        return document["name"]


schedule_category_service = ScheduleCategoryService()
