from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class ActivityUpdate(BaseModel):
    """Whitelisted fields for updating an OPC activity."""

    model_config = {"extra": "forbid"}

    name: str | None = Field(None, min_length=1, max_length=200)
    startDate: date | None = None
    finishDate: date | None = None
    duration: int | None = Field(None, ge=0, le=9999)
    status: Literal["Not Started", "In Progress", "Complete"] | None = None
    calendarId: str | None = None
    wbsId: str | None = None


class ActivityCreate(BaseModel):
    """Required and optional fields for creating an OPC activity."""

    model_config = {"extra": "forbid"}

    name: str = Field(..., min_length=1, max_length=200)
    wbsId: str
    startDate: date | None = None
    finishDate: date | None = None
    duration: int | None = Field(None, ge=0, le=9999)
    status: Literal["Not Started", "In Progress", "Complete"] = "Not Started"
    calendarId: str | None = None


class WBSNodeCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(..., min_length=1, max_length=200)
    parentWbsId: str | None = None
    sequenceNumber: int | None = Field(None, ge=0)


class WBSNodeUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(None, min_length=1, max_length=200)
    sequenceNumber: int | None = Field(None, ge=0)


class RelationshipCreate(BaseModel):
    model_config = {"extra": "forbid"}

    predecessorActivityId: str
    successorActivityId: str
    type: Literal["FS", "SS", "FF", "SF"] = "FS"
    lag: int = Field(0, ge=-999, le=999)


class RelationshipUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    type: Literal["FS", "SS", "FF", "SF"] | None = None
    lag: int | None = Field(None, ge=-999, le=999)


class CalendarUpdate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(None, min_length=1, max_length=200)
