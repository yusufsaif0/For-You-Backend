from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from app.api.routes import document_ocr_router, family_router, food_analysis_router, life_items_router, market_router, schedules_router
from app.core.config import settings
from app.core.database import close_mongo_connection, connect_to_mongo


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production()
    await connect_to_mongo()
    yield
    await close_mongo_connection()

app = FastAPI(
    title=settings.app_name,
    description="Backend API for Daily Life mobile app",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.app_environment == "production" else "/docs",
    redoc_url=None if settings.app_environment == "production" else "/redoc",
    openapi_url=None if settings.app_environment == "production" else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(schedules_router, prefix=settings.api_v1_prefix)
app.include_router(life_items_router, prefix=settings.api_v1_prefix)
app.include_router(food_analysis_router, prefix=settings.api_v1_prefix)
app.include_router(document_ocr_router, prefix=settings.api_v1_prefix)
app.include_router(market_router, prefix=settings.api_v1_prefix)
app.include_router(family_router, prefix=settings.api_v1_prefix)


@app.exception_handler(PyMongoError)
async def database_unavailable(_, __):
    return JSONResponse(
        status_code=503,
        content={"detail": "Your data is temporarily unavailable. Please try again."},
    )


@app.get("/")
async def root():
    return {
        "message": "Daily Life API is running"
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
