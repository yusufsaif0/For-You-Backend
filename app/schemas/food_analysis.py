from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FoodImageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mime_type: Literal["image/jpeg", "image/png", "image/webp"]
    image_base64: str = Field(min_length=1, max_length=8_400_000)


class DetectedFood(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    portion_g: float = Field(gt=0, le=10000)
    calories: int = Field(ge=0, le=10000)
    sugar_g: float = Field(ge=0, le=1000)
    fat_g: float = Field(ge=0, le=1000)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("Food name cannot be blank.")
        return name


class FoodAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_food: bool
    foods: list[DetectedFood] = Field(max_length=12)

    @model_validator(mode="after")
    def foods_match_classification(self):
        if self.is_food != bool(self.foods):
            raise ValueError("Food classification must agree with the detected food list.")
        return self
