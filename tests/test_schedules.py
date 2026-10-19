"""Run with: python -m unittest discover -s tests -v.

Set TEST_MONGODB_URL to enable API tests against a disposable MongoDB database.
Every test creates and removes its own daily_life_test_* database.
"""
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo.errors import ConnectionFailure

from app.core import database
from app.core.auth import require_user
from app.core.config import settings
from app.main import app
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from app.services.schedule_service import _to_schedule_read


def activity(**changes):
    return {"title": "Morning walk", "category": "Workout", "starts_at": "2026-10-18T07:30:00+05:30", **changes}


class SchemaTests(unittest.TestCase):
    def test_whitespace_title_is_rejected(self):
        with self.assertRaises(ValidationError):
            ScheduleCreate(**activity(title="   "))

    def test_datetime_requires_offset(self):
        with self.assertRaises(ValidationError):
            ScheduleCreate(**activity(starts_at="2026-10-18T07:30:00"))

    def test_partial_update_can_clear_notes_but_not_required_fields(self):
        self.assertEqual(ScheduleUpdate(notes=None).model_dump(exclude_unset=True), {"notes": None})
        for changes in ({}, {"title": None}, {"completed": None}, {"unknown": True}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                ScheduleUpdate(**changes)

    def test_reminder_must_precede_schedule(self):
        with self.assertRaises(ValidationError):
            ScheduleCreate(**activity(reminder_at="2026-10-18T07:30:00+05:30"))
        schedule = ScheduleCreate(**activity(reminder_at="2026-10-18T07:20:00+05:30"))
        self.assertEqual(schedule.reminder_at.isoformat(), "2026-10-18T07:20:00+05:30")

    def test_legacy_naive_utc_is_returned_with_offset_and_completion_default(self):
        schedule = _to_schedule_read({"_id": ObjectId(), **activity(starts_at=datetime(2026, 10, 18, 2))})
        self.assertEqual(schedule.starts_at.utcoffset().total_seconds(), 0)
        self.assertFalse(schedule.completed)
        self.assertIn('Z', schedule.model_dump_json())

    def test_old_date_and_time_contract_is_readable(self):
        schedule = _to_schedule_read({"_id": ObjectId(), "title": "Legacy", "category": "Work", "date": "2026-10-18", "start_time": "09:30 AM"})
        self.assertEqual(schedule.starts_at, datetime(2026, 10, 18, 9, 30, tzinfo=timezone.utc))


@unittest.skipUnless(os.getenv("TEST_MONGODB_URL"), "Set TEST_MONGODB_URL to run MongoDB integration tests")
class ScheduleApiTests(unittest.TestCase):
    def setUp(self):
        self.database_name = f"daily_life_test_{uuid4().hex}"
        self.url_patch = patch.object(settings, "mongodb_url", os.environ["TEST_MONGODB_URL"])
        self.name_patch = patch.object(settings, "mongodb_database", self.database_name)
        self.url_patch.start()
        self.name_patch.start()
        self.addCleanup(self.url_patch.stop)
        self.addCleanup(self.name_patch.stop)
        self.user_id = "test-user-a"
        app.dependency_overrides[require_user] = lambda: {"uid": self.user_id, "email": "test@example.com"}
        self.addCleanup(app.dependency_overrides.pop, require_user, None)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        # Only ever drop the uniquely generated test database.
        self.addCleanup(self.drop_test_database)

    def drop_test_database(self):
        assert self.database_name.startswith("daily_life_test_")
        self.client.portal.call(database.client.drop_database, self.database_name)

    def create(self, **changes):
        response = self.client.post("/api/schedules", json=activity(**changes))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_full_lifecycle_preserves_completion_and_created_at(self):
        created = self.create(notes="Bring shoes")
        self.assertFalse(created["completed"])
        path = f"/api/schedules/{created['id']}"
        edited = self.client.patch(path, json={"title": "Evening walk", "notes": "", "starts_at": "2026-10-19T18:00:00+05:30"})
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["title"], "Evening walk")
        self.assertEqual(edited.json()["notes"], "")
        self.assertEqual(edited.json()["created_at"], created["created_at"])
        completed = self.client.patch(path, json={"completed": True})
        self.assertTrue(completed.json()["completed"])
        loaded = self.client.get("/api/schedules").json()
        self.assertEqual(len(loaded), 1)
        self.assertTrue(loaded[0]["completed"])
        self.assertEqual(loaded[0]["title"], "Evening walk")
        undone = self.client.patch(path, json={"completed": False})
        self.assertFalse(undone.json()["completed"])
        deleted = self.client.delete(path)
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(deleted.content, b"")
        self.assertEqual(self.client.get("/api/schedules").json(), [])

    def test_schedules_survive_new_backend_client(self):
        created = self.create()
        # A new MongoDB connection simulates restarting the backend process.
        self.client.portal.call(database.close_mongo_connection)
        self.client.portal.call(database.connect_to_mongo)
        self.assertEqual(self.client.get("/api/schedules").json()[0]["id"], created["id"])

    def test_schedules_are_isolated_by_authenticated_user(self):
        created = self.create()
        self.user_id = "test-user-b"
        self.assertEqual(self.client.get("/api/schedules").json(), [])
        path = f"/api/schedules/{created['id']}"
        self.assertEqual(self.client.patch(path, json={"completed": True}).status_code, 404)
        self.assertEqual(self.client.delete(path).status_code, 404)
        self.user_id = "test-user-a"
        self.assertEqual(self.client.get("/api/schedules").json()[0]["id"], created["id"])

    def test_local_day_filter_includes_utc_previous_day(self):
        before = self.create(starts_at="2026-10-17T23:59:59+05:30")
        first = self.create(starts_at="2026-10-18T00:00:00+05:30")
        last = self.create(starts_at="2026-10-18T23:59:59+05:30")
        after = self.create(starts_at="2026-10-19T00:00:00+05:30")
        response = self.client.get("/api/schedules", params={"scheduled_for": "2026-10-18T12:00:00+05:30"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([item["id"] for item in response.json()], [first["id"], last["id"]])

    def test_bad_or_missing_ids(self):
        for method, body in ((self.client.patch, {"completed": True}), (self.client.delete, None)):
            for object_id, status in (("bad-id", 400), (str(ObjectId()), 404)):
                with self.subTest(method=method.__name__, object_id=object_id):
                    kwargs = {"json": body} if body else {}
                    self.assertEqual(method(f"/api/schedules/{object_id}", **kwargs).status_code, status)

    def test_invalid_changes_do_not_modify_saved_activity(self):
        created = self.create()
        for changes in ({"title": " "}, {"title": None}, {"starts_at": "invalid"}, {"starts_at": "2026-10-18T07:00:00"}, {"category": " "}, {"category": "x" * 61}, {"completed": None}, {}, {"notes": "x" * 1001}):
            with self.subTest(changes=changes):
                response = self.client.patch(f"/api/schedules/{created['id']}", json=changes)
                self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.get("/api/schedules").json()[0]["title"], created["title"])

    def test_custom_categories_survive_reconnect_and_are_account_scoped(self):
        path = "/api/schedules/categories"
        response = self.client.post(path, json={"name": "  Family  time  "})
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json(), "Family time")
        self.assertEqual(self.client.post(path, json={"name": "family TIME"}).json(), "Family time")
        self.client.portal.call(database.close_mongo_connection)
        self.client.portal.call(database.connect_to_mongo)
        self.assertEqual(self.client.get(path).json(), ["Family time"])
        created = self.create(category="Family time")
        self.assertEqual(created["category"], "Family time")
        changed = self.client.patch(f"/api/schedules/{created['id']}", json={"category": "Travel"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["category"], "Travel")
        self.user_id = "test-user-b"
        self.assertEqual(self.client.get(path).json(), [])
        self.assertEqual(self.client.post(path, json={"name": "family time"}).json(), "family time")
        self.user_id = "test-user-a"
        self.assertEqual(self.client.get(path).json(), ["Family time"])

    def test_database_outage_returns_retryable_message(self):
        with patch("app.services.schedule_service.get_collection", side_effect=ConnectionFailure("test")):
            response = self.client.get("/api/schedules")
        self.assertEqual(response.status_code, 503)
        self.assertIn("try again", response.json()["detail"])

    def test_life_item_create_update_list_delete(self):
        created_response = self.client.post("/api/life-items", json={
            "kind": "meal",
            "title": "Lunch",
            "meal_type": "Lunch",
            "calories": 620,
            "occurred_at": "2026-10-18T12:00:00+05:30",
        })
        self.assertEqual(created_response.status_code, 201, created_response.text)
        created = created_response.json()
        self.assertEqual(created["calories"], 620)

        listed = self.client.get("/api/life-items", params={"kind": "meal"})
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual([item["id"] for item in listed.json()], [created["id"]])

        updated = self.client.patch(f"/api/life-items/{created['id']}", json={"notes": "Home cooked"})
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["notes"], "Home cooked")

        deleted = self.client.delete(f"/api/life-items/{created['id']}")
        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(self.client.get("/api/life-items", params={"kind": "meal"}).json(), [])

    def test_life_items_are_isolated_by_authenticated_user(self):
        response = self.client.post("/api/life-items", json={
            "kind": "meal",
            "title": "Lunch",
            "meal_type": "Lunch",
            "calories": 620,
            "occurred_at": "2026-10-18T12:00:00+05:30",
        })
        self.assertEqual(response.status_code, 201, response.text)
        item_id = response.json()["id"]
        self.user_id = "test-user-b"
        self.assertEqual(self.client.get("/api/life-items", params={"kind": "meal"}).json(), [])
        self.assertEqual(self.client.patch(f"/api/life-items/{item_id}", json={"title": "Changed"}).status_code, 404)
        self.assertEqual(self.client.delete(f"/api/life-items/{item_id}").status_code, 404)


if __name__ == "__main__":
    unittest.main()
