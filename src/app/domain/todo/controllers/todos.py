from typing import Annotated
from uuid import UUID
from datetime import datetime

import structlog
from advanced_alchemy.filters import FilterTypes
from advanced_alchemy.service import OffsetPagination
from litestar import Controller, delete, get, patch, post
from litestar.di import Provide
from litestar.params import Dependency, Parameter

import app.db.models as m
from app.domain.todo.deps import provide_tag_service, provide_todo_service
from app.domain.todo.schemas import TagCreate, TagModel, TodoCreate, TodoModel
from app.domain.todo.services import TagService, TodoService
from app.lib.deps import create_filter_dependencies

logger = structlog.get_logger()


class TodoController(Controller):
    """Controller for managing todo items."""

    tags = ["Todo"]

    dependencies = {
        "todo_service": Provide(provide_todo_service),
        "tag_service": Provide(provide_tag_service),
    } | create_filter_dependencies(
        {
            "id_filter": UUID,
            "search": "item",
            "pagination_type": "limit_offset",
            "pagination_size": 40,
            "created_at": True,
            "updated_at": True,
            "sort_field": "created_at",
            "sort_order": "asc",
        },
    )

    path = "/todos"

    @get(path="/", operation_id="list_todos")
    async def list_todos(
        self,
        current_user: m.User,
        todo_service: TodoService,
        filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)],
        start_time_from: Annotated[datetime | None, Parameter(
            query="start_time_from", description="Filter todos with start_time after this datetime (ISO format)")] = None,
        start_time_to: Annotated[datetime | None, Parameter(
            query="start_time_to", description="Filter todos with start_time before this datetime (ISO format)")] = None,
        end_time_from: Annotated[datetime | None, Parameter(
            query="end_time_from", description="Filter todos with end_time after this datetime (ISO format)")] = None,
        end_time_to: Annotated[datetime | None, Parameter(
            query="end_time_to", description="Filter todos with end_time before this datetime (ISO format)")] = None,
        include_series_items: Annotated[bool, Parameter(
            query="include_series_items",
            description="Include items generated from recurring series (default: false)",
        )] = False,
    ) -> OffsetPagination[TodoModel]:
        """List all todo items with optional start_time and end_time filtering."""
        user_filter = m.Todo.user_id == current_user.id
        additional_filters = []

        # Add custom datetime filters
        if start_time_from:
            additional_filters.append(m.Todo.start_time >= start_time_from)
        if start_time_to:
            additional_filters.append(m.Todo.start_time <= start_time_to)
        if end_time_from:
            additional_filters.append(m.Todo.end_time >= end_time_from)
        if end_time_to:
            additional_filters.append(m.Todo.end_time <= end_time_to)
        if not include_series_items:
            additional_filters.append(m.Todo.series_id.is_(None))

        all_filters = [user_filter] + additional_filters + list(filters)
        results, total = await todo_service.list_and_count(*all_filters)
        return todo_service.to_schema(data=results, total=total, schema_type=TodoModel, filters=filters)

    @post(path="/", operation_id="create_todo")
    async def create_todo(self, current_user: m.User, data: TodoCreate, todo_service: TodoService) -> TodoModel:
        """Create a new todo item."""
        todo_dict = data.to_dict()
        todo_dict["user_id"] = current_user.id
        todo_model = await todo_service.create(todo_dict)
        return todo_service.to_schema(todo_model, schema_type=TodoModel)

    @get(path="/{todo_id:uuid}", operation_id="get_todo")
    async def get_todo(self, todo_id: UUID, todo_service: TodoService) -> TodoModel | str:
        try:
            """Get a specific todo item by ID."""
            todo = await todo_service.get(todo_id)
            if not todo:
                return f"Todo item {todo_id} not found."
            return todo_service.to_schema(todo, schema_type=TodoModel)
        except (ValueError, RuntimeError, AttributeError) as e:
            return f"Error retrieving todo item {todo_id}: {e!s}"

    @patch(path="/{todo_id:uuid}", operation_id="update_todo")
    async def update_todo(self, todo_id: UUID, data: TodoCreate, todo_service: TodoService) -> str | TodoModel:
        """Update a specific todo item by ID."""
        todo = await todo_service.get(todo_id)
        if not todo:
            return f"Todo item {todo_id} not found."
        todo_dict = data.to_dict()
        updated_todo = await todo_service.update(item_id=todo_id, data=todo_dict)
        return todo_service.to_schema(updated_todo, schema_type=TodoModel)

    @delete(path="/{todo_id:uuid}", operation_id="delete_todo", status_code=200)
    async def delete_todo(self, todo_id: UUID, todo_service: TodoService) -> str | TodoModel:
        try:
            """Delete a specific todo item by ID."""
            todo = await todo_service.get(todo_id)
            if not todo:
                return f"Todo item {todo_id} not found."
            await todo_service.delete(todo_id)
            return todo_service.to_schema(todo, schema_type=TodoModel)
        except (ValueError, RuntimeError, AttributeError) as e:
            return f"Error deleting todo item {todo_id}: {e!s}"

    @post(path="/create_tag", operation_id="create_tag")
    async def create_tag(self, current_user: m.User, data: TagCreate, tag_service: TagService, todo_service: TodoService) -> TagModel:
        """Create a new tag."""

        tag_model = await tag_service.get_or_create_tag(current_user.id, data.name, data.color)
        current_todo_uuid = data.todo_id
        if current_todo_uuid:
            # If a todo is provided, associate the tag with it
            todo_tag = m.TodoTag(
                todo_id=current_todo_uuid, tag_id=tag_model.id)
            current_todo = await todo_service.get(current_todo_uuid)
            if current_todo:
                current_todo.todo_tags.append(todo_tag)

        return tag_service.to_schema(tag_model, schema_type=TagModel)

    @delete(path="/delete_tag/{tag_id:uuid}", operation_id="delete_tag", status_code=200)
    async def delete_tag(self, tag_id: UUID, current_user: m.User, tag_service: TagService) -> str | TagModel:
        """Delete a specific tag by ID."""
        tag = await tag_service.get_one_or_none(m.Tag.id == tag_id, m.Tag.user_id == current_user.id)
        if not tag:
            return f"Tag {tag_id} not found or does not belong to the user."

        await tag_service.delete(tag)

        return tag_service.to_schema(tag, schema_type=TagModel)

    @get(path="/tags", operation_id="list_tags")
    async def list_tags(self, current_user: m.User, tag_service: TagService, filters: Annotated[list[FilterTypes], Dependency(skip_validation=True)]) -> OffsetPagination[TagModel]:
        """List all tags for the current user."""
        user_filter = m.Tag.user_id == current_user.id
        results, total = await tag_service.list_and_count(user_filter, *filters)
        return tag_service.to_schema(data=results, total=total, schema_type=TagModel, filters=filters)
