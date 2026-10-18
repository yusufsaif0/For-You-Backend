from fastapi import APIRouter, Depends

from app.core.auth import require_user
from app.schemas.document_ocr import DocumentOCRRequest, DocumentOCRResult
from app.services.document_ocr import extract_document_fields

router = APIRouter(prefix="/documents", tags=["Private document extraction"])


@router.post("/extract", response_model=DocumentOCRResult)
async def extract_document(
    request: DocumentOCRRequest,
    _user: dict = Depends(require_user),
) -> DocumentOCRResult:
    return await extract_document_fields(request)
