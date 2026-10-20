from fastapi import APIRouter, Depends

from app.core.auth import require_user
from app.core.config import settings
from app.schemas.applications import ApplicationChatRequest, ApplicationChatResponse, ApplicationExtractRequest
from app.schemas.document_ocr import DocumentOCRRequest, DocumentOCRResult
from app.services import application_assistant
from app.services.document_ocr import extract_document_fields

router = APIRouter(prefix="/applications", tags=["Application assistant"])


@router.get("/capabilities")
async def capabilities(_user: dict = Depends(require_user)):
    return {
        "processing_enabled": settings.applications_personal_data_enabled and bool(settings.gemini_api_key),
        "submission_mode": "guided",
        "automated_submission_available": False,
        "message": "Chat and selected document data are processed transiently by the backend and Google Gemini. "
        "Saved drafts stay encrypted in your device vault. Complete submission, OTP, CAPTCHA and payment on the official portal.",
    }


@router.post("/chat", response_model=ApplicationChatResponse)
async def chat(request: ApplicationChatRequest, user: dict = Depends(require_user)):
    return await application_assistant.chat(request, user["uid"])


@router.post("/extract", response_model=DocumentOCRResult)
async def extract(request: ApplicationExtractRequest, _user: dict = Depends(require_user)):
    application_assistant.require_processing_configuration()
    return await extract_document_fields(DocumentOCRRequest(mime_type=request.mime_type, file_base64=request.file_base64))
