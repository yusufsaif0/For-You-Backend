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
    await database["life_items"].create_index([("user_id", 1), ("kind", 1), ("occurred_at", -1)])


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
