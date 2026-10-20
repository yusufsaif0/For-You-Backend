from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ApplicationMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ApplicationScope(BaseModel):
    service: Literal["unknown", "ews", "residence", "examination", "other"] = "unknown"
    state: str = Field(default="", max_length=100)
    district: str = Field(default="", max_length=100)
    institution: str = Field(default="", max_length=200)
    session: str = Field(default="", max_length=100)


class ApplicationRequirement(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=160)
    kind: Literal["field", "document"]
    required: bool = True
    description: str = Field(default="", max_length=600)
    source_url: str = Field(default="", max_length=2048)


class ApplicationFact(BaseModel):
    value: str = Field(default="Not verified", max_length=500)
    source_url: str = Field(default="", max_length=2048)


class ApplicationSource(BaseModel):
    url: str
    title: str
    checked_at: str


class ApplicationPlan(BaseModel):
    title: str = Field(default="New application", max_length=200)
    scope: ApplicationScope = Field(default_factory=ApplicationScope)
    portal_url: str = Field(default="", max_length=2048)
    requirements: list[ApplicationRequirement] = Field(default_factory=list, max_length=35)
    fee: ApplicationFact = Field(default_factory=ApplicationFact)
    deadline: ApplicationFact = Field(default_factory=ApplicationFact)
    sources: list[ApplicationSource] = Field(default_factory=list, max_length=6)
    research_id: str = Field(default="", max_length=64)


class ApplicationChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ApplicationMessage] = Field(min_length=1, max_length=24)
    plan: ApplicationPlan = Field(default_factory=ApplicationPlan)
    confirmed_fields: dict[str, str] = Field(default_factory=dict, max_length=50)
    verify_requirements: bool = False
    processing_consent: Literal[True]

    # The service separately bounds the combined field values before inference.


class ApplicationChatResponse(BaseModel):
    reply: str = Field(min_length=1, max_length=5000)
    plan: ApplicationPlan
    suggested_values: dict[str, str] = Field(default_factory=dict, max_length=35)
    questions: list[str] = Field(default_factory=list, max_length=4)
    submission_mode: Literal["guided"] = "guided"


class ApplicationExtractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mime_type: Literal["application/pdf", "image/jpeg", "image/png", "image/webp"]
    file_base64: str = Field(min_length=1, max_length=8_400_000)
    processing_consent: Literal[True]
