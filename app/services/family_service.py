import base64
import binascii
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.core.database import get_collection
from app.schemas.family import (
    FamilyDocumentAccessApprove,
    FamilyDocumentCreate,
    FamilyInviteCreate,
    FamilyPublicKeyUpdate,
    FamilyTaskCreate,
    FamilyTaskUpdate,
    FamilyWishContributionCreate,
    FamilyWishCreate,
    FamilyWishUpdate,
)


MAX_DOCUMENT_BYTES = 10 * 1024 * 1024 + 28


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(value: str, label: str) -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(status_code=400, detail=f"Invalid {label} ID.")
    return ObjectId(value)


def _display_name(user: dict) -> str:
    name = user.get("display_name")
    return name.strip()[:100] if isinstance(name, str) and name.strip() else str(user.get("email") or "Family member")


def _profile(user: dict) -> dict[str, str]:
    return {
        "uid": user["uid"],
        "email": str(user.get("email") or "").lower(),
        "display_name": _display_name(user),
    }


async def _is_connected(first_uid: str, second_uid: str) -> bool:
    if first_uid == second_uid:
        return True
    collection = get_collection("family_connections")
    return await collection.find_one({
        "uid_a": min(first_uid, second_uid),
        "uid_b": max(first_uid, second_uid),
    }) is not None


async def _require_connection(first_uid: str, second_uid: str) -> None:
    if first_uid != second_uid and not await _is_connected(first_uid, second_uid):
        raise HTTPException(status_code=403, detail="Connect with this family member before sharing data.")


def _family_id(value: str) -> ObjectId:
    return _id(value, "family item")


async def get_overview(user: dict) -> dict[str, Any]:
    uid = user["uid"]
    connections = get_collection("family_connections")
    member_docs = []
    async for connection in connections.find({"member_uids": uid}):
        member = next((profile for profile in connection["profiles"] if profile["uid"] != uid), None)
        if member:
            member_docs.append({
                **member,
                "connected_at": connection["created_at"],
            })
    member_docs.sort(key=lambda item: item["display_name"].casefold())
    member_uids = [member["uid"] for member in member_docs]

    invitation_collection = get_collection("family_invitations")
    email = str(user.get("email") or "").lower()
    requests = []
    async for invitation in invitation_collection.find({
        "$or": [
            {"inviter_uid": uid, "status": "pending"},
            {"target_email": email, "status": "pending"},
        ]
    }).sort("created_at", -1):
        incoming = invitation["target_email"] == email and invitation["inviter_uid"] != uid
        requests.append({
            "id": str(invitation["_id"]),
            "direction": "incoming" if incoming else "outgoing",
            "email": invitation["inviter_email"] if incoming else invitation["target_email"],
            "created_at": invitation["created_at"],
        })

    public_keys: dict[str, str] = {}
    if member_uids:
        async for key in get_collection("family_public_keys").find({"uid": {"$in": member_uids}}):
            public_keys[key["uid"]] = key["public_key"]
    return {"members": member_docs, "requests": requests, "public_keys": public_keys}


async def create_invitation(request: FamilyInviteCreate, user: dict) -> dict[str, Any]:
    uid = user["uid"]
    email = request.email.lower()
    own_email = str(user.get("email") or "").lower()
    if not own_email:
        raise HTTPException(status_code=403, detail="A verified email account is required.")
    if email == own_email:
        raise HTTPException(status_code=400, detail="You cannot invite your own account.")

    connections = get_collection("family_connections")
    existing_connection = await connections.find_one({"profiles.email": email, "member_uids": uid})
    if existing_connection:
        raise HTTPException(status_code=409, detail="This account is already connected to your family.")
    invitations = get_collection("family_invitations")
    existing = await invitations.find_one({
        "status": "pending",
        "$or": [
            {"inviter_uid": uid, "target_email": email},
            {"inviter_email": email, "target_email": own_email},
        ],
    })
    if existing:
        raise HTTPException(status_code=409, detail="A family request is already pending for this email.")

    now = _now()
    invitation = {
        "inviter_uid": uid,
        "inviter_email": own_email,
        "inviter_name": _display_name(user),
        "target_email": email,
        "status": "pending",
        "created_at": now,
    }
    result = await invitations.insert_one(invitation)
    return {
        "id": str(result.inserted_id),
        "direction": "outgoing",
        "email": email,
        "created_at": now,
    }


async def respond_invitation(invitation_id: str, accept: bool, user: dict) -> None:
    uid = user["uid"]
    email = str(user.get("email") or "").lower()
    invitations = get_collection("family_invitations")
    invitation = await invitations.find_one({
        "_id": _id(invitation_id, "invitation"),
        "target_email": email,
        "status": "pending",
    })
    if invitation is None:
        raise HTTPException(status_code=404, detail="This family request is no longer available.")
    inviter_uid = invitation["inviter_uid"]
    if inviter_uid == uid:
        raise HTTPException(status_code=400, detail="You cannot accept a request from your own account.")

    now = _now()
    if accept:
        first_uid, second_uid = sorted((uid, inviter_uid))
        profiles_by_uid = {
            inviter_uid: {
                "uid": inviter_uid,
                "email": invitation["inviter_email"],
                "display_name": invitation["inviter_name"],
            },
            uid: _profile(user),
        }
        connections = get_collection("family_connections")
        existing = await connections.find_one({"uid_a": first_uid, "uid_b": second_uid})
        if existing is None:
            try:
                await connections.insert_one({
                    "uid_a": first_uid,
                    "uid_b": second_uid,
                    "member_uids": [first_uid, second_uid],
                    "profiles": [profiles_by_uid[first_uid], profiles_by_uid[second_uid]],
                    "created_at": now,
                })
            except DuplicateKeyError:
                if await connections.find_one({"uid_a": first_uid, "uid_b": second_uid}) is None:
                    raise
        await invitations.update_one(
            {"_id": invitation["_id"], "status": "pending"},
            {"$set": {"status": "accepted", "target_uid": uid, "accepted_at": now}},
        )
        await invitations.update_many(
            {
                "inviter_uid": uid,
                "target_email": invitation["inviter_email"],
                "status": "pending",
            },
            {"$set": {"status": "accepted", "target_uid": inviter_uid, "accepted_at": now}},
        )
    else:
        await invitations.update_one(
            {"_id": invitation["_id"], "status": "pending"},
            {"$set": {"status": "declined", "target_uid": uid, "responded_at": now}},
        )


async def remove_member(other_uid: str, user: dict) -> None:
    uid = user["uid"]
    if other_uid == uid:
        raise HTTPException(status_code=400, detail="You cannot remove your own account.")
    first_uid, second_uid = sorted((uid, other_uid))
    result = await get_collection("family_connections").delete_one({"uid_a": first_uid, "uid_b": second_uid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="This family connection no longer exists.")

    await get_collection("family_tasks").delete_many({
        "$or": [
            {"creator_uid": uid, "assignee_uid": other_uid},
            {"creator_uid": other_uid, "assignee_uid": uid},
        ],
    })
    await get_collection("family_document_requests").delete_many({
        "$or": [
            {"owner_uid": uid, "requester_uid": other_uid},
            {"owner_uid": other_uid, "requester_uid": uid},
        ],
    })
    wishes = get_collection("family_wishes")
    await wishes.update_many(
        {"creator_uid": uid, "member_uids": other_uid},
        {"$pull": {"member_uids": other_uid}},
    )
    await wishes.update_many(
        {"creator_uid": other_uid, "member_uids": uid},
        {"$pull": {"member_uids": uid}},
    )


async def get_own_public_key(user: dict) -> dict[str, str | None]:
    record = await get_collection("family_public_keys").find_one({"uid": user["uid"]})
    return {"public_key": record["public_key"] if record else None}


async def register_public_key(request: FamilyPublicKeyUpdate, user: dict) -> None:
    try:
        decoded = base64.b64decode(request.public_key, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=422, detail="The family public key is invalid.") from error
    if len(decoded) != 32:
        raise HTTPException(status_code=422, detail="The family public key must be 32 bytes.")

    collection = get_collection("family_public_keys")
    existing = await collection.find_one({"uid": user["uid"]})
    if existing:
        if existing["public_key"] != request.public_key:
            raise HTTPException(
                status_code=409,
                detail="A different family key is already registered. Restore the original recovery key before sharing.",
            )
        return
    try:
        await collection.insert_one({
            "uid": user["uid"],
            "public_key": request.public_key,
            "created_at": _now(),
        })
    except DuplicateKeyError as error:
        existing = await collection.find_one({"uid": user["uid"]})
        if not existing or existing["public_key"] != request.public_key:
            raise HTTPException(status_code=409, detail="A different family key is already registered.") from error


def _task_read(document: dict) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "creator_uid": document["creator_uid"],
        "assignee_uid": document["assignee_uid"],
        "title": document["title"],
        "notes": document.get("notes"),
        "due_at": document["due_at"],
        "reminder_at": document.get("reminder_at"),
        "completed": document.get("completed", False),
        "created_at": document["created_at"],
    }


async def list_tasks(user: dict) -> list[dict[str, Any]]:
    uid = user["uid"]
    collection = get_collection("family_tasks")
    result = []
    async for item in collection.find({"$or": [{"creator_uid": uid}, {"assignee_uid": uid}]}).sort("due_at", 1):
        other_uid = item["assignee_uid"] if item["creator_uid"] == uid else item["creator_uid"]
        if await _is_connected(uid, other_uid):
            result.append(_task_read(item))
    return result


async def create_task(request: FamilyTaskCreate, user: dict) -> dict[str, Any]:
    uid = user["uid"]
    await _require_connection(uid, request.assignee_uid)
    now = _now()
    document = request.model_dump()
    document["creator_uid"] = uid
    document["created_at"] = now
    document["updated_at"] = now
    if document["due_at"].tzinfo is None:
        raise HTTPException(status_code=422, detail="The due date must include a timezone.")
    document["due_at"] = document["due_at"].astimezone(timezone.utc)
    if document.get("reminder_at") is not None:
        document["reminder_at"] = document["reminder_at"].astimezone(timezone.utc)
    result = await get_collection("family_tasks").insert_one(document)
    document["_id"] = result.inserted_id
    return _task_read(document)


async def update_task(task_id: str, changes: FamilyTaskUpdate, user: dict) -> dict[str, Any]:
    uid = user["uid"]
    collection = get_collection("family_tasks")
    task = await collection.find_one({"_id": _family_id(task_id)})
    if task is None or uid not in (task["creator_uid"], task["assignee_uid"]):
        raise HTTPException(status_code=404, detail="This family reminder no longer exists.")
    if task["creator_uid"] != uid:
        update_fields = set(changes.model_fields_set)
        if update_fields != {"completed"}:
            raise HTTPException(status_code=403, detail="Only the reminder creator can edit its details.")

    updates = changes.model_dump(exclude_unset=True)
    candidate = {**task, **updates}
    if candidate.get("reminder_at") is not None and candidate["reminder_at"] >= candidate["due_at"]:
        raise HTTPException(status_code=422, detail="A reminder must be earlier than the due date.")
    for field in ("due_at", "reminder_at"):
        if updates.get(field) is not None:
            updates[field] = updates[field].astimezone(timezone.utc)
    updates["updated_at"] = _now()
    document = await collection.find_one_and_update(
        {"_id": task["_id"]},
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    return _task_read(document)


async def delete_task(task_id: str, user: dict) -> None:
    result = await get_collection("family_tasks").delete_one({
        "_id": _family_id(task_id),
        "creator_uid": user["uid"],
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="This family reminder no longer exists.")


def _wish_read(document: dict) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "creator_uid": document["creator_uid"],
        "creator_name": document["creator_name"],
        "member_uids": document["member_uids"],
        "title": document["title"],
        "target_amount": document["target_amount"],
        "target_date": document["target_date"],
        "contributions": document["contributions"],
        "created_at": document["created_at"],
    }


async def list_wishes(user: dict) -> list[dict[str, Any]]:
    uid = user["uid"]
    collection = get_collection("family_wishes")
    result = []
    async for item in collection.find({"$or": [{"creator_uid": uid}, {"member_uids": uid}]}).sort("created_at", -1):
        if item["creator_uid"] == uid or await _is_connected(uid, item["creator_uid"]):
            result.append(_wish_read(item))
    return result


async def create_wish(request: FamilyWishCreate, user: dict) -> dict[str, Any]:
    uid = user["uid"]
    participant_uids = list(dict.fromkeys([uid, *request.member_uids]))
    if len(participant_uids) > 20:
        raise HTTPException(status_code=422, detail="A shared wish can include up to 20 family members.")
    for member_uid in participant_uids:
        await _require_connection(uid, member_uid)
    today = _now().date()
    if request.target_date < today:
        raise HTTPException(status_code=422, detail="Choose a target date that is today or later.")
    now = _now()
    document = {
        "creator_uid": uid,
        "creator_name": _display_name(user),
        "creator_email": str(user.get("email") or "").lower(),
        "member_uids": participant_uids,
        "title": request.title,
        "target_amount": request.target_amount,
        "target_date": request.target_date.isoformat(),
        "contributions": [],
        "created_at": now,
        "updated_at": now,
    }
    result = await get_collection("family_wishes").insert_one(document)
    document["_id"] = result.inserted_id
    return _wish_read(document)


async def update_wish(wish_id: str, changes: FamilyWishUpdate, user: dict) -> dict[str, Any]:
    collection = get_collection("family_wishes")
    object_id = _family_id(wish_id)
    wish = await collection.find_one({"_id": object_id, "creator_uid": user["uid"]})
    if wish is None:
        raise HTTPException(status_code=404, detail="This shared wish no longer exists.")
    updates = changes.model_dump(exclude_unset=True)
    if "target_amount" in updates:
        total_saved = sum(entry["amount"] for entry in wish["contributions"])
        if updates["target_amount"] < total_saved:
            raise HTTPException(status_code=422, detail="The target cannot be less than the amount already saved.")
    if "target_date" in updates:
        target_date = updates["target_date"]
        if target_date < wish["created_at"].date():
            raise HTTPException(status_code=422, detail="The target date cannot be before this wish was created.")
        updates["target_date"] = target_date.isoformat()
    updates["updated_at"] = _now()
    filter_query: dict[str, Any] = {"_id": object_id, "creator_uid": user["uid"]}
    if "target_amount" in updates:
        filter_query["$expr"] = {
            "$gte": [
                {"$literal": updates["target_amount"]},
                {"$sum": "$contributions.amount"},
            ],
        }
    updated = await collection.find_one_and_update(
        filter_query,
        {"$set": updates},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        exists = await collection.find_one({"_id": object_id, "creator_uid": user["uid"]})
        if exists is None:
            raise HTTPException(status_code=404, detail="This shared wish no longer exists.")
        raise HTTPException(status_code=422, detail="The target cannot be less than the amount already saved.")
    return _wish_read(updated)


async def delete_wish(wish_id: str, user: dict) -> None:
    result = await get_collection("family_wishes").delete_one({
        "_id": _family_id(wish_id),
        "creator_uid": user["uid"],
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="This shared wish no longer exists.")


async def add_wish_contribution(wish_id: str, request: FamilyWishContributionCreate, user: dict) -> dict[str, Any]:
    uid = user["uid"]
    collection = get_collection("family_wishes")
    object_id = _family_id(wish_id)
    wish = await collection.find_one({"_id": object_id})
    if wish is None:
        raise HTTPException(status_code=404, detail="This shared wish no longer exists.")
    if uid not in wish["member_uids"]:
        raise HTTPException(status_code=403, detail="You are not a participant in this shared wish.")
    if uid != wish["creator_uid"]:
        await _require_connection(uid, wish["creator_uid"])
    contribution = {
        "contributor_uid": uid,
        "contributor_name": _display_name(user),
        "amount": request.amount,
        "created_at": _now(),
    }
    updated = await collection.find_one_and_update(
        {
            "_id": object_id,
            "$expr": {
                "$lte": [
                    {"$add": [{"$sum": "$contributions.amount"}, {"$literal": request.amount}]},
                    {"$add": ["$target_amount", 0.000001]},
                ],
            },
        },
        {"$push": {"contributions": contribution}, "$set": {"updated_at": contribution["created_at"]}},
        return_document=ReturnDocument.AFTER,
    )
    if updated is None:
        raise HTTPException(status_code=422, detail="The contribution cannot exceed the remaining wish target.")
    return _wish_read(updated)


def _decode_encrypted_content(value: str) -> bytes:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=422, detail="The encrypted document data is invalid.") from error
    if len(decoded) < 29 or len(decoded) > MAX_DOCUMENT_BYTES:
        raise HTTPException(status_code=413, detail="Choose a document no larger than 10 MB for family sharing.")
    return decoded


def _validate_wrapped_key(value: str) -> None:
    try:
        decoded = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(status_code=422, detail="The encrypted document access key is invalid.") from error
    if len(decoded) != 108:
        raise HTTPException(status_code=422, detail="The encrypted document access key has an invalid size.")


def _document_read(document: dict, owner_name: str, access_status: str) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "owner_uid": document["owner_uid"],
        "owner_name": owner_name,
        "title": document["title"],
        "category": document["category"],
        "filename": document["filename"],
        "mime_type": document["mime_type"],
        "created_at": document["created_at"],
        "access_status": access_status,
    }


async def publish_document(request: FamilyDocumentCreate, user: dict) -> dict[str, Any]:
    owner_key = await get_collection("family_public_keys").find_one({"uid": user["uid"]})
    if owner_key is None:
        raise HTTPException(status_code=409, detail="Set up family document encryption before publishing documents.")
    content = _decode_encrypted_content(request.encrypted_content)
    _validate_wrapped_key(request.owner_wrapped_key)
    object_id = ObjectId(request.id)
    document = {
        "_id": object_id,
        "owner_uid": user["uid"],
        "owner_name": _display_name(user),
        "title": request.title,
        "category": request.category,
        "filename": request.filename,
        "mime_type": request.mime_type,
        "encrypted_content": request.encrypted_content,
        "encrypted_size": len(content),
        "owner_wrapped_key": request.owner_wrapped_key,
        "created_at": _now(),
    }
    try:
        await get_collection("family_documents").insert_one(document)
    except DuplicateKeyError as error:
        raise HTTPException(status_code=409, detail="This family document has already been published.") from error
    return _document_read(document, document["owner_name"], "owner")


async def list_documents(user: dict) -> list[dict[str, Any]]:
    uid = user["uid"]
    requests = get_collection("family_document_requests")
    result = []
    overview = await get_overview(user)
    member_uids = [member["uid"] for member in overview["members"]]
    async for document in get_collection("family_documents").find(
        {"$or": [{"owner_uid": uid}, {"owner_uid": {"$in": member_uids}}]}
    ).sort("created_at", -1):
        owner_uid = document["owner_uid"]
        if owner_uid == uid:
            current_status = "owner"
        else:
            request = await requests.find_one({"document_id": document["_id"], "requester_uid": uid})
            current_status = request["status"] if request and request["status"] in ("pending", "approved") else "none"
        result.append(_document_read(document, document["owner_name"], current_status))
    return result


async def create_document_request(document_id: str, user: dict) -> dict[str, Any]:
    uid = user["uid"]
    object_id = _family_id(document_id)
    document = await get_collection("family_documents").find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="This family document no longer exists.")
    owner_uid = document["owner_uid"]
    if owner_uid == uid:
        raise HTTPException(status_code=400, detail="You already own this family document.")
    await _require_connection(uid, owner_uid)
    requester_key = await get_collection("family_public_keys").find_one({"uid": uid})
    if requester_key is None:
        raise HTTPException(status_code=409, detail="Set up family document encryption before requesting access.")

    requests = get_collection("family_document_requests")
    existing = await requests.find_one({"document_id": object_id, "requester_uid": uid})
    if existing and existing["status"] in ("pending", "approved"):
        raise HTTPException(status_code=409, detail="A request for this document is already pending or approved.")
    now = _now()
    request = {
        "document_id": object_id,
        "requester_uid": uid,
        "requester_name": _display_name(user),
        "owner_uid": owner_uid,
        "document_title": document["title"],
        "status": "pending",
        "created_at": now,
    }
    if existing:
        await requests.update_one({"_id": existing["_id"]}, {"$set": request, "$unset": {"wrapped_key": ""}})
        request["_id"] = existing["_id"]
    else:
        result = await requests.insert_one(request)
        request["_id"] = result.inserted_id
    return _document_request_read(request)


def _document_request_read(request: dict) -> dict[str, Any]:
    return {
        "id": str(request["_id"]),
        "document_id": str(request["document_id"]),
        "requester_uid": request["requester_uid"],
        "requester_name": request["requester_name"],
        "owner_uid": request["owner_uid"],
        "document_title": request["document_title"],
        "status": request["status"],
        "created_at": request["created_at"],
    }


async def list_document_requests(user: dict) -> dict[str, list[dict[str, Any]]]:
    uid = user["uid"]
    collection = get_collection("family_document_requests")
    incoming = []
    outgoing = []
    async for request in collection.find({
        "$or": [
            {"owner_uid": uid, "status": "pending"},
            {"requester_uid": uid},
        ]
    }).sort("created_at", -1):
        read = _document_request_read(request)
        (incoming if request["owner_uid"] == uid else outgoing).append(read)
    return {"incoming": incoming, "outgoing": outgoing}


async def respond_document_request(
    request_id: str,
    approve: bool,
    body: FamilyDocumentAccessApprove | None,
    user: dict,
) -> None:
    uid = user["uid"]
    requests = get_collection("family_document_requests")
    request = await requests.find_one({
        "_id": _id(request_id, "document request"),
        "owner_uid": uid,
        "status": "pending",
    })
    if request is None:
        raise HTTPException(status_code=404, detail="This document access request is no longer pending.")
    await _require_connection(uid, request["requester_uid"])
    updates: dict[str, Any] = {
        "status": "approved" if approve else "declined",
        "responded_at": _now(),
    }
    if approve:
        if body is None:
            raise HTTPException(status_code=422, detail="An encrypted access key is required to approve this request.")
        _validate_wrapped_key(body.wrapped_key)
        requester_key = await get_collection("family_public_keys").find_one({"uid": request["requester_uid"]})
        if requester_key is None:
            raise HTTPException(status_code=409, detail="This member must set up family document encryption first.")
        updates["wrapped_key"] = body.wrapped_key
    await requests.update_one({"_id": request["_id"], "status": "pending"}, {"$set": updates})


async def get_document_content(document_id: str, user: dict) -> dict[str, str]:
    uid = user["uid"]
    object_id = _family_id(document_id)
    document = await get_collection("family_documents").find_one({"_id": object_id})
    if document is None:
        raise HTTPException(status_code=404, detail="This family document no longer exists.")
    if document["owner_uid"] == uid:
        wrapped_key = document["owner_wrapped_key"]
    else:
        await _require_connection(uid, document["owner_uid"])
        request = await get_collection("family_document_requests").find_one({
            "document_id": object_id,
            "requester_uid": uid,
            "owner_uid": document["owner_uid"],
            "status": "approved",
        })
        if request is None or not request.get("wrapped_key"):
            raise HTTPException(status_code=403, detail="The document owner has not approved access.")
        wrapped_key = request["wrapped_key"]
    return {
        "encrypted_content": document["encrypted_content"],
        "wrapped_key": wrapped_key,
        "mime_type": document["mime_type"],
        "filename": document["filename"],
    }


async def delete_document(document_id: str, user: dict) -> None:
    object_id = _family_id(document_id)
    result = await get_collection("family_documents").delete_one({
        "_id": object_id,
        "owner_uid": user["uid"],
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="This family document no longer exists.")
    await get_collection("family_document_requests").delete_many({"document_id": object_id})
