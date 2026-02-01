# ExecPlan: recurring-todo-series

## Goal
Add an agent CRUD tool that creates recurring todos within a date range, auto-resolves conflicts to free slots, enforces range/volume limits, and avoids list spam by collapsing series in list views.

## Constraints
- Range length <= 6 months (~183 days)
- Max created todos <= 100
- Rest days are skipped
- Each todo must have start_time and end_time
- Conflicts must be rescheduled into free slots on the same date
- Default list view should not display 100 repeated items

## Data Model
- New table: todo_series
  - id, user_id, name, description, timezone
  - rule_type (enum: daily, weekly, monthly, interval)
  - rule_payload (JSON)
  - start_date, end_date
  - default_start_time (HH:MM), duration_minutes
  - created_at, updated_at
- Todo model: add series_id (nullable FK -> todo_series.id), series_index (int) or occurrence_key (date string) for de-duplication
- Indices:
  - todo(series_id)
  - todo_series(user_id, start_date, end_date)

## Rule Payload Shapes
- daily: {"template": {"item": str, "description": str?, "start_time": "HH:MM"?, "duration_minutes": int?, "tags": [str]?}}
- weekly: {"days": [0..6], "templates": {"0": {...}, "1": {...}}}
- monthly: {"day": 1..31, "template": {...}}
- interval: {"cycle": [{"type": "work", "template": {...}}, {"type": "rest"}], "repeat": int?}

## Tool & Schema
- New Pydantic args model: RecurringTodoArgs
  - series_name, start_date, end_date, timezone
  - rule_type, rule_payload
  - default_start_time, duration_minutes
  - tags (optional), importance (optional)
  - max_items (default 100)
- New CRUD tool: create_recurring_todos
  - Returns: counts, series_id, sample items, failures

## Core Flow (Implementation)
1. Validate args, parse timezone, ensure range and max items.
2. Build occurrence dates from rule_type/payload.
3. Preload existing todos in range (UTC), group by local date.
4. For each occurrence date:
   - Build desired slot (start_time + duration)
   - If conflict, scan for free slot in working hours (08:00-22:00) or preferred window
   - If no slot, record failure (do not create)
   - If slot found, append to create list
5. Create todo_series record, then batch create todos with series_id.
6. Return summary with partial list and failure reasons.

## List Collapsing
- API list (GET /todos): add query param include_series_items (default false)
  - false: return series summaries + non-series todos
  - true: return all todos (current behavior)
- Agent get_todo_list: default collapse by series_id with summary + latest 1-3 items

## Error Handling
- If occurrences > max_items -> return error
- If date range > 6 months -> return error
- If no slot for a day -> include in failures

## Tests
- Unit: recurrence generation per rule, monthly missing day behavior, interval skip rest
- Unit: conflict resolution finds free slot
- Integration: create_recurring_todos tool creates series + todos
- API: list collapsing behavior (include_series_items on/off)

## Pending Decisions
- Monthly date missing (skip vs last-day)
- Default working hours / preferred time-of-day
- Collapse scope: agent list only vs API list too
