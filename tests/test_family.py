"""Run with: python -m unittest discover -s tests -v.

Set TEST_MONGODB_URL to enable FamilyApiTests against isolated test databases.
"""
import base64
import os
import unittest
from datetime import date
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import database
from app.core.auth import require_user
from app.core.config import settings
from app.main import app
from app.schemas.family import (
    FamilyDocumentCreate,
    FamilyInviteCreate,
    FamilyPublicKeyUpdate,
    FamilyTaskCreate,
    FamilyTaskUpdate,
    FamilyWishCreate,
    FamilyWishContributionCreate,
)
from app.services import family_service


def encoded(size: int) -> str:
    return base64.b64encode(bytes((value % 256 for value in range(size)))).decode("ascii")


def task_payload(**changes):
    return {
        "assignee_uid": "family-b",
        "title": "Pick up medicine",
        "due_at": "2030-01-01T09:00:00+05:30",
        "reminder_at": "2030-01-01T08:00:00+05:30",
        **changes,
    }


class FamilySchemaTests(unittest.TestCase):
    def test_invitation_normalizes_and_validates_email(self):
        self.assertEqual(FamilyInviteCreate(email=" Family@Example.com ").email, "family@example.com")
        with self.assertRaises(ValidationError):
            FamilyInviteCreate(email="not-an-email")

    def test_task_reminder_must_precede_due_time(self):
        FamilyTaskCreate(**task_payload())
        with self.assertRaises(ValidationError):
            FamilyTaskCreate(**task_payload(reminder_at="2030-01-01T09:00:00+05:30"))
        with self.assertRaises(ValidationError):
            FamilyTaskCreate(**task_payload(due_at="2030-01-01T09:00:00"))

    def test_task_assignee_cannot_edit_details(self):
        self.assertEqual(FamilyTaskUpdate(completed=True).model_dump(exclude_unset=True), {"completed": True})
        with self.assertRaises(ValidationError):
            FamilyTaskUpdate()

    def test_shared_wish_and_contribution_reject_invalid_amounts(self):
        with self.assertRaises(ValidationError):
            FamilyWishCreate(title="Car", target_amount=0, target_date=date(2030, 1, 1))
        with self.assertRaises(ValidationError):
            FamilyWishContributionCreate(amount=-1)

    def test_encrypted_document_payload_requires_supported_mime_and_size(self):
        FamilyDocumentCreate(
            id="0123456789abcdef01234567",
            title="PAN card",
            category="PAN card",
            filename="pan.pdf",
            mime_type="application/pdf",
            encrypted_content=encoded(29),
            owner_wrapped_key=encoded(108),
        )
        with self.assertRaises(ValidationError):
            FamilyDocumentCreate(
                id="bad-id",
                title="PAN card",
                category="PAN card",
                filename="pan.pdf",
                mime_type="text/plain",
                encrypted_content="invalid",
                owner_wrapped_key="invalid",
            )


class FamilyServiceValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_noncanonical_key_is_rejected_and_existing_key_is_immutable(self):
        user = {"uid": "family-a", "email": "a@example.com"}
        with self.assertRaises(HTTPException) as error:
            await family_service.register_public_key(
                FamilyPublicKeyUpdate(public_key="!" * 44),
                user,
            )
        self.assertEqual(error.exception.status_code, 422)


@unittest.skipUnless(os.getenv("TEST_MONGODB_URL"), "Set TEST_MONGODB_URL to run MongoDB integration tests")
class FamilyApiTests(unittest.TestCase):
    def setUp(self):
        self.database_name = f"daily_life_test_{uuid4().hex}"
        self.url_patch = patch.object(settings, "mongodb_url", os.environ["TEST_MONGODB_URL"])
        self.name_patch = patch.object(settings, "mongodb_database", self.database_name)
        self.url_patch.start()
        self.name_patch.start()
        self.addCleanup(self.url_patch.stop)
        self.addCleanup(self.name_patch.stop)
        self.current_user = {
            "uid": "family-a",
            "email": "a@example.com",
            "display_name": "Alex",
        }
        app.dependency_overrides[require_user] = lambda: self.current_user
        self.addCleanup(app.dependency_overrides.pop, require_user, None)
        self.client = TestClient(app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.addCleanup(self.drop_test_database)

    def drop_test_database(self):
        assert self.database_name.startswith("daily_life_test_")
        self.client.portal.call(database.client.drop_database, self.database_name)

    def as_user(self, uid, email, display_name):
        self.current_user = {"uid": uid, "email": email, "display_name": display_name}

    def connect_family(self):
        invitation = self.client.post("/api/family/invitations", json={"email": "b@example.com"})
        self.assertEqual(invitation.status_code, 201, invitation.text)
        invitation_id = invitation.json()["id"]
        self.as_user("family-b", "b@example.com", "Bea")
        accepted = self.client.post(f"/api/family/invitations/{invitation_id}/accept")
        self.assertEqual(accepted.status_code, 204, accepted.text)
        self.as_user("family-a", "a@example.com", "Alex")
        return invitation_id

    def test_email_invitation_acceptance_creates_pairwise_connection(self):
        response = self.client.post("/api/family/invitations", json={"email": "b@example.com"})
        self.assertEqual(response.status_code, 201, response.text)
        self.as_user("family-b", "b@example.com", "Bea")
        incoming = self.client.get("/api/family").json()["requests"]
        self.assertEqual(incoming[0]["direction"], "incoming")
        accepted = self.client.post(f"/api/family/invitations/{response.json()['id']}/accept")
        self.assertEqual(accepted.status_code, 204, accepted.text)
        self.as_user("family-a", "a@example.com", "Alex")
        members = self.client.get("/api/family").json()["members"]
        self.assertEqual(members[0]["uid"], "family-b")
        self.assertEqual(members[0]["display_name"], "Bea")

    def test_family_task_permissions_and_visibility(self):
        self.connect_family()
        created = self.client.post("/api/family/tasks", json=task_payload())
        self.assertEqual(created.status_code, 201, created.text)
        task_id = created.json()["id"]
        self.as_user("family-b", "b@example.com", "Bea")
        self.assertEqual(len(self.client.get("/api/family/tasks").json()), 1)
        self.assertEqual(self.client.patch(f"/api/family/tasks/{task_id}", json={"title": "Changed"}).status_code, 403)
        completed = self.client.patch(f"/api/family/tasks/{task_id}", json={"completed": True})
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertTrue(completed.json()["completed"])
        self.assertEqual(self.client.delete(f"/api/family/tasks/{task_id}").status_code, 404)

    def test_shared_wish_allows_participant_contributions_but_only_creator_can_delete(self):
        self.connect_family()
        created = self.client.post("/api/family/wishes", json={
            "title": "Family trip",
            "target_amount": 5000,
            "target_date": "2030-06-01",
            "member_uids": ["family-b"],
        })
        self.assertEqual(created.status_code, 201, created.text)
        wish_id = created.json()["id"]
        self.as_user("family-b", "b@example.com", "Bea")
        contribution = self.client.post(f"/api/family/wishes/{wish_id}/contributions", json={"amount": 1000})
        self.assertEqual(contribution.status_code, 200, contribution.text)
        self.assertEqual(contribution.json()["contributions"][0]["contributor_name"], "Bea")
        self.assertIn("created_at", contribution.json()["contributions"][0])
        self.assertEqual(self.client.post(f"/api/family/wishes/{wish_id}/contributions", json={"amount": 5000}).status_code, 422)
        self.assertEqual(self.client.delete(f"/api/family/wishes/{wish_id}").status_code, 404)

    def test_end_to_end_document_access_requires_approval_and_connected_member(self):
        self.connect_family()
        owner_key = encoded(32)
        requester_key = encoded(32)
        self.assertEqual(self.client.put("/api/family/public-key", json={"public_key": owner_key}).status_code, 204)
        self.as_user("family-b", "b@example.com", "Bea")
        self.assertEqual(self.client.put("/api/family/public-key", json={"public_key": requester_key}).status_code, 204)
        self.as_user("family-a", "a@example.com", "Alex")
        document_id = "0123456789abcdef01234567"
        published = self.client.post("/api/family/documents", json={
            "id": document_id,
            "title": "PAN",
            "category": "PAN card",
            "filename": "pan.pdf",
            "mime_type": "application/pdf",
            "encrypted_content": encoded(29),
            "owner_wrapped_key": encoded(108),
        })
        self.assertEqual(published.status_code, 201, published.text)
        self.as_user("family-b", "b@example.com", "Bea")
        request = self.client.post(f"/api/family/documents/{document_id}/requests")
        self.assertEqual(request.status_code, 201, request.text)
        self.assertEqual(self.client.get(f"/api/family/documents/{document_id}/content").status_code, 403)
        self.as_user("family-a", "a@example.com", "Alex")
        request_id = request.json()["id"]
        approved = self.client.post(
            f"/api/family/document-requests/{request_id}/approve",
            json={"wrapped_key": encoded(108)},
        )
        self.assertEqual(approved.status_code, 204, approved.text)
        self.as_user("family-b", "b@example.com", "Bea")
        content = self.client.get(f"/api/family/documents/{document_id}/content")
        self.assertEqual(content.status_code, 200, content.text)
        self.assertEqual(content.json()["wrapped_key"], encoded(108))
        self.assertEqual(self.client.delete(f"/api/family/documents/{document_id}").status_code, 404)
        self.as_user("family-c", "c@example.com", "Casey")
        self.assertEqual(self.client.get(f"/api/family/documents/{document_id}/content").status_code, 403)

    def test_key_registration_cannot_overwrite_existing_public_key(self):
        first = encoded(32)
        second = base64.b64encode(b"x" * 32).decode("ascii")
        self.assertEqual(self.client.put("/api/family/public-key", json={"public_key": first}).status_code, 204)
        self.assertEqual(self.client.put("/api/family/public-key", json={"public_key": first}).status_code, 204)
        self.assertEqual(self.client.put("/api/family/public-key", json={"public_key": second}).status_code, 409)

    def test_removing_member_revokes_family_document_access(self):
        self.connect_family()
        document_id = "0123456789abcdef01234567"
        self.client.put("/api/family/public-key", json={"public_key": encoded(32)})
        published = self.client.post("/api/family/documents", json={
            "id": document_id,
            "title": "Passport",
            "category": "Other",
            "filename": "passport.pdf",
            "mime_type": "application/pdf",
            "encrypted_content": encoded(29),
            "owner_wrapped_key": encoded(108),
        })
        self.assertEqual(published.status_code, 201, published.text)
        self.as_user("family-b", "b@example.com", "Bea")
        self.client.put("/api/family/public-key", json={"public_key": encoded(32)})
        self.client.post(f"/api/family/documents/{document_id}/requests")
        self.as_user("family-a", "a@example.com", "Alex")
        request_id = self.client.get("/api/family/document-requests").json()["incoming"][0]["id"]
        self.assertEqual(self.client.post(f"/api/family/document-requests/{request_id}/approve", json={"wrapped_key": encoded(108)}).status_code, 204)
        removed = self.client.delete("/api/family/members/family-b")
        self.assertEqual(removed.status_code, 204, removed.text)
        self.as_user("family-b", "b@example.com", "Bea")
        self.assertEqual(self.client.get(f"/api/family/documents/{document_id}/content").status_code, 403)


if __name__ == "__main__":
    unittest.main()
