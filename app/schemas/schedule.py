from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ScheduleCategory(StrEnum):
    WORKOUT = "Workout"
    WORK = "Work"
    FOOD = "Food"
    STUDY = "Study"
    SOCIAL = "Social"
    SLEEP = "Sleep"


class ScheduleBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=120)
    category: ScheduleCategory
    starts_at: AwareDatetime
    reminder_at: AwareDatetime | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: str | None = Field(default=None, max_length=1000)
    completed: bool = False

    @model_validator(mode="after")
    def validate_reminder(self):
        if self.reminder_at is not None and self.reminder_at >= self.starts_at:
            raise ValueError("A reminder must be earlier than the schedule.")
        return self


class ScheduleCreate(ScheduleBase):
    """Payload accepted when the mobile app creates a schedule."""


class ScheduleUpdate(BaseModel):
    """Only supplied fields are changed; optional details can be cleared."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    category: ScheduleCategory | None = None
    starts_at: AwareDatetime | None = None
    reminder_at: AwareDatetime | None = None
    icon: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    notes: str | None = Field(default=None, max_length=1000)
    completed: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_changes(cls, values):
        if isinstance(values, dict):
            if not values:
                raise ValueError("Supply at least one field to update.")
            for field in ("title", "category", "starts_at", "completed"):
                if field in values and values[field] is None:
                    raise ValueError(f"{field} cannot be null.")
        return values


class ScheduleRead(ScheduleBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
