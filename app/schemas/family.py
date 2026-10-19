import re
from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class FamilyInviteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=254)

    @model_validator(mode="after")
    def validate_email(self):
        self.email = self.email.lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email):
            raise ValueError("Enter a valid email address.")
        return self


class FamilyPublicKeyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_key: str = Field(min_length=44, max_length=44)


class FamilyTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    assignee_uid: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    due_at: AwareDatetime
    reminder_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_reminder(self):
        if self.reminder_at is not None and self.reminder_at >= self.due_at:
            raise ValueError("A reminder must be earlier than the due date.")
        return self


class FamilyTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=120)
    notes: str | None = Field(default=None, max_length=500)
    due_at: AwareDatetime | None = None
    reminder_at: AwareDatetime | None = None
    completed: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_changes(cls, values):
        if not isinstance(values, dict) or not values:
            raise ValueError("Supply at least one field to update.")
        for field in ("title", "due_at", "completed"):
            if field in values and values[field] is None:
                raise ValueError(f"{field} cannot be null.")
        return values

    @model_validator(mode="after")
    def validate_reminder(self):
        if self.reminder_at is not None and self.due_at is not None and self.reminder_at >= self.due_at:
            raise ValueError("A reminder must be earlier than the due date.")
        return self


class FamilyWishCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=80)
    target_amount: float = Field(gt=0, le=100_000_000)
    target_date: date
    member_uids: list[str] = Field(default_factory=list, max_length=20)


class FamilyWishUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, min_length=1, max_length=80)
    target_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    target_date: date | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_changes(cls, values):
        if not isinstance(values, dict) or not values:
            raise ValueError("Supply at least one field to update.")
        return values


class FamilyWishContributionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float = Field(gt=0, le=100_000_000)


class FamilyDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str = Field(pattern=r"^[0-9a-fA-F]{24}$")
    title: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=60)
    filename: str = Field(min_length=1, max_length=200)
    mime_type: Literal["application/pdf", "image/jpeg", "image/png", "image/webp"]
    encrypted_content: str = Field(min_length=1, max_length=14_000_000)
    owner_wrapped_key: str = Field(min_length=144, max_length=144)


class FamilyDocumentAccessApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wrapped_key: str = Field(min_length=144, max_length=144)
