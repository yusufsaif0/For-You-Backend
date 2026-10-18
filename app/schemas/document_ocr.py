from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocumentMimeType = Literal["application/pdf", "image/jpeg", "image/png", "image/webp"]


class DocumentOCRRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mime_type: DocumentMimeType
    file_base64: str = Field(min_length=1, max_length=8_400_000)


class ExtractedDocumentField(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=500)


class DocumentOCRResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: str = Field(min_length=1, max_length=60)
    fields: list[ExtractedDocumentField] = Field(max_length=30)
