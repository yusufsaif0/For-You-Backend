from datetime import datetime
from enum import StrEnum

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class LifeItemKind(StrEnum):
    MEAL = "meal"
    WEIGHT = "weight"
    TASK = "task"
    EVENT = "event"


class MealType(StrEnum):
    BREAKFAST = "Breakfast"
    LUNCH = "Lunch"
    DINNER = "Dinner"
    SNACK = "Snack"


class LifeItemBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    kind: LifeItemKind
    title: str = Field(min_length=1, max_length=120)
    occurred_at: AwareDatetime | None = None
    calories: int | None = Field(default=None, ge=0, le=10000)
    sugar_g: float | None = Field(default=None, ge=0, le=1000)
    fat_g: float | None = Field(default=None, ge=0, le=1000)
    meal_type: MealType | None = None
    weight_kg: float | None = Field(default=None, gt=0, le=1000)
    due_at: AwareDatetime | None = None
    starts_at: AwareDatetime | None = None
    reminder_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=1000)
    priority: str | None = Field(default=None, pattern=r"^(Low|Medium|High)$")
    completed: bool = False

    @model_validator(mode="after")
    def validate_kind_fields(self):
        if self.kind == LifeItemKind.MEAL and (
            self.calories is None or self.occurred_at is None or self.meal_type is None
        ):
            raise ValueError("Meals require a meal type, calories, and an occurrence time.")
        if self.kind != LifeItemKind.MEAL and (self.sugar_g is not None or self.fat_g is not None):
            raise ValueError("Sugar and fat values are only valid for meal entries.")
        if self.kind == LifeItemKind.WEIGHT and (self.weight_kg is None or self.occurred_at is None):
            raise ValueError("Weight entries require a weight and measurement time.")
        if self.kind == LifeItemKind.TASK and self.due_at is None:
            raise ValueError("Tasks require a due date and time.")
        if self.kind == LifeItemKind.EVENT and self.starts_at is None:
            raise ValueError("Events require a start date and time.")
        if self.reminder_at is not None:
            target = self.due_at if self.kind == LifeItemKind.TASK else self.starts_at
            if target is not None and self.reminder_at >= target:
                raise ValueError("A reminder must be earlier than its task or event.")
        if self.kind not in (LifeItemKind.TASK, LifeItemKind.EVENT) and self.reminder_at is not None:
            raise ValueError("Reminders are only available for tasks and events.")
        return self


class LifeItemCreate(LifeItemBase):
    pass


class LifeItemUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    occurred_at: AwareDatetime | None = None
    calories: int | None = Field(default=None, ge=0, le=10000)
    sugar_g: float | None = Field(default=None, ge=0, le=1000)
    fat_g: float | None = Field(default=None, ge=0, le=1000)
    meal_type: MealType | None = None
    weight_kg: float | None = Field(default=None, gt=0, le=1000)
    due_at: AwareDatetime | None = None
    starts_at: AwareDatetime | None = None
    reminder_at: AwareDatetime | None = None
    notes: str | None = Field(default=None, max_length=1000)
    priority: str | None = Field(default=None, pattern=r"^(Low|Medium|High)$")
    completed: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_patch(cls, values):
        if not isinstance(values, dict) or not values:
            raise ValueError("Supply at least one field to update.")
        if "title" in values and values["title"] is None:
            raise ValueError("title cannot be null.")
        if "completed" in values and values["completed"] is None:
            raise ValueError("completed cannot be null.")
        return values


class LifeItemRead(LifeItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime
