import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import require_user
from app.main import app
from app.schemas.schedule import ScheduleCategoryCreate, ScheduleCreate, ScheduleUpdate
from app.services.schedule_category_service import ScheduleCategoryService


class CategoryValidationTests(unittest.TestCase):
    def test_custom_category_is_valid_on_create_and_edit(self):
        schedule = ScheduleCreate(title="Visit parents", category="  Family  ", starts_at="2026-10-20T10:00:00+05:30")
        self.assertEqual(schedule.category, "Family")
        self.assertEqual(ScheduleUpdate(category="Travel").category, "Travel")

    def test_blank_long_and_null_categories_are_rejected(self):
        for name in ("", "   ", "x" * 61, None):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                ScheduleCategoryCreate(name=name)
            with self.subTest(update=name), self.assertRaises(ValidationError):
                ScheduleUpdate(category=name)


class CategoryServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_names_are_deduplicated_per_account(self):
        collection = MagicMock()
        collection.find_one_and_update = AsyncMock(return_value={"name": "Family time"})
        service = ScheduleCategoryService()
        with patch("app.services.schedule_category_service.get_collection", return_value=collection):
            self.assertEqual(await service.create(" Family   time ", "user-a"), "Family time")
            first_query = collection.find_one_and_update.call_args.args[0]
            await service.create("family TIME", "user-a")
            self.assertEqual(first_query, collection.find_one_and_update.call_args.args[0])
            await service.create("Family time", "user-b")
            other_query = collection.find_one_and_update.call_args.args[0]
            self.assertNotEqual(first_query["_id"], other_query["_id"])
            self.assertEqual(other_query["user_id"], "user-b")

    async def test_existing_default_name_uses_canonical_spelling(self):
        with patch("app.services.schedule_category_service.get_collection") as get_collection:
            self.assertEqual(await ScheduleCategoryService().create(" work ", "user-a"), "Work")
            get_collection.assert_not_called()


class CategoryRouteTests(unittest.TestCase):
    def setUp(self):
        app.dependency_overrides[require_user] = lambda: {"uid": "user-a"}
        self.addCleanup(app.dependency_overrides.pop, require_user, None)
        # These route tests mock storage and do not run the database lifespan.
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_save_and_load_use_the_authenticated_account(self):
        with patch("app.api.routes.schedules.schedule_category_service.create", new_callable=AsyncMock, return_value="Family") as create:
            response = self.client.post("/api/schedules/categories", json={"name": "Family"})
            self.assertEqual(response.status_code, 201, response.text)
            self.assertEqual(response.json(), "Family")
            create.assert_awaited_once_with("Family", "user-a")
        with patch("app.api.routes.schedules.schedule_category_service.list", new_callable=AsyncMock, return_value=["Family"]) as load:
            self.assertEqual(self.client.get("/api/schedules/categories").json(), ["Family"])
            load.assert_awaited_once_with("user-a")

    def test_invalid_name_never_reaches_storage(self):
        with patch("app.api.routes.schedules.schedule_category_service.create", new_callable=AsyncMock) as create:
            for name in (" ", "x" * 61, None):
                self.assertEqual(self.client.post("/api/schedules/categories", json={"name": name}).status_code, 422)
            create.assert_not_awaited()
