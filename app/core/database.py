from pymongo import AsyncMongoClient

from app.core.config import settings


client: AsyncMongoClient | None = None


async def connect_to_mongo() -> None:
    """Create and verify the MongoDB connection during application startup."""
    global client

    if not settings.mongodb_url:
        raise RuntimeError("MONGODB_URL is required. Add it to the backend .env file.")

    client = AsyncMongoClient(settings.mongodb_url, tz_aware=True, serverSelectionTimeoutMS=5000)
    await client.admin.command("ping")
    database = client[settings.mongodb_database]
    await database["schedules"].create_index([("user_id", 1), ("starts_at", 1)])
    await database["schedule_categories"].create_index([("user_id", 1), ("name_key", 1)])
    await database["life_items"].create_index([("user_id", 1), ("kind", 1), ("occurred_at", -1)])
    await database["family_invitations"].create_index([("target_email", 1), ("status", 1)])
    await database["family_invitations"].create_index([("inviter_uid", 1), ("status", 1)])
    await database["family_connections"].create_index(
        [("uid_a", 1), ("uid_b", 1)],
        unique=True,
    )
    await database["family_connections"].create_index([("member_uids", 1)])
    await database["family_public_keys"].create_index([("uid", 1)], unique=True)
    await database["family_tasks"].create_index([("creator_uid", 1), ("due_at", 1)])
    await database["family_tasks"].create_index([("assignee_uid", 1), ("due_at", 1)])
    await database["family_wishes"].create_index([("creator_uid", 1), ("created_at", -1)])
    await database["family_wishes"].create_index([("member_uids", 1), ("created_at", -1)])
    await database["family_documents"].create_index([("owner_uid", 1), ("created_at", -1)])
    await database["family_document_requests"].create_index(
        [("document_id", 1), ("requester_uid", 1)],
        unique=True,
    )
    await database["family_document_requests"].create_index([("owner_uid", 1), ("status", 1)])
    await database["family_document_requests"].create_index([("requester_uid", 1), ("status", 1)])


async def close_mongo_connection() -> None:
    """Close MongoDB resources during application shutdown."""
    global client

    if client is not None:
        await client.close()
        client = None


def get_collection(name: str):
    if client is None:
        raise RuntimeError("MongoDB is not connected.")
    return client[settings.mongodb_database][name]
