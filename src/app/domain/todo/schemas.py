from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import field_validator

from app.config.base import get_settings
from app.db.models.importance import Importance
from app.domain.accounts.schemas import PydanticBaseModel

__all__ = ("TodoModel",)

settings = get_settings()


class TodoModel(PydanticBaseModel):
    id: UUID
    item: str
    description: str | None = None
    created_time: datetime
    alarm_time: datetime | None = None
    start_time: datetime
    end_time: datetime
    importance: Importance
    user_id: UUID
    tags: list[str] | None = None
    series_id: UUID | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def _extract_tag_names(cls, value: Any) -> list[str] | None:
        """Ensure tags validate as list of strings when provided by ORM proxy."""
        if value is None:
            return None

        if isinstance(value, str):
            return [value]

        if not isinstance(value, Iterable):
            return value

        extracted: list[str] = []
        for item in value:
            name = getattr(item, "name", None)
            extracted.append(name if isinstance(name, str) else str(item))

        return extracted


class TodoCreate(PydanticBaseModel):
    item: str
    description: str | None = None
    alarm_time: datetime | None = None
    start_time: datetime
    end_time: datetime
    importance: Importance = Importance.NONE
    tags: list[str] | None = None


class TodoUpdate(PydanticBaseModel):
    item: str | None = None
    description: str | None = None
    alarm_time: datetime | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    importance: Importance | None = None
    tags: list[str] | None = None


class TagModel(PydanticBaseModel):
    id: UUID
    name: str
    color: str | None = None
    user_id: UUID


class TagCreate(PydanticBaseModel):
    name: str
    color: str | None = None
    todo_id: UUID | None = None


class AgentTodoResponse(PydanticBaseModel):
    status: str
    message: str
    agent_response: list[dict[str, Any]]
