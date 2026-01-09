# Remove redundant SSE message/history events in AI agent stream

This ExecPlan is a dynamic document. As work proceeds, the `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` sections must stay updated.

This plan must be maintained according to `/.agents/PLANS.md`.

## Purpose / Big Picture

Users of the AI chat stream see duplicated assistant responses because the backend emits both incremental `message_delta` events and a final `message` event containing the full content. The backend also emits a final `history` event that includes internal conversation history. After this change, the stream will continue to emit `message_delta` events and a `completed` event, but it will not emit `message` or `history`. The user-visible effect is a single assistant reply in the UI, with no extra final content or history payloads.

## Progress

- [x] (2026-01-05 03:56Z) Drafted plan and identified backend/frontend touchpoints.
- [x] (2026-01-05 04:00Z) Update `src/app/domain/todo_agents/services.py` to stop emitting `message` and `history` events while preserving `completed`.
- [x] (2026-01-05 04:00Z) Update `front-end/app/(app)/(tabs)/ai-chat.tsx` to process only the intended event types (primarily `message_delta`, optionally `tool_result`) and ignore others.
- [ ] Validate the SSE output and the UI behavior.

## Surprises & Discoveries

- None so far.

## Decision Log

- Decision: Remove the `message` event and the final `history` event from the SSE stream, while keeping `completed` with `final_message` intact.
  Reason: The stream already provides incremental `message_delta` updates, and the final `message` duplicates content in the UI. The `history` payload is not needed by the chat UI and can leak extra details.
  Date/Author: 2026-01-05 / Codex

- Decision: Add frontend filtering by SSE event name.
  Reason: It makes the UI robust against unexpected payloads and prevents accidental duplication if backend emits more content-like events.
  Date/Author: 2026-01-05 / Codex

## Outcomes & Retrospective

- Pending implementation.

## Context and Orientation

The SSE stream is produced by `TodoAgentService.stream_chat_with_agent` in `src/app/domain/todo_agents/services.py`. The controller in `src/app/domain/todo_agents/controllers/todo_agents.py` forwards each payload into `ServerSentEventMessage` without altering the event content. The front-end streaming client in `front-end/app/(app)/(tabs)/ai-chat.tsx` parses SSE data with `eventsource-parser` and currently appends any `parsed.content` or `parsed.output` to the assistant message, regardless of event type. This causes the final `message` event to duplicate the output already assembled from `message_delta` events.

## Plan of Work

First, adjust the backend streaming service so that it still tracks the last message for the `completed` event but does not emit a `message` event for `message_output_item`. Then remove the final `history` event after the stream finishes. Next, update the front-end stream parser to react only to specific event names (e.g., `message_delta` for assistant text and `tool_result` for tool output) and ignore other events. Finally, validate the change by running the stream and confirming that no `message` or `history` events appear and the UI shows a single assistant reply.

## Concrete Steps

1. Edit `src/app/domain/todo_agents/services.py` and update `_handle_run_item_stream_event` to return `handled=True` with an empty payload list for `message_output_item`, while still passing the `message_update` so `completed` retains the full text. Remove the final `history` emission at the end of `stream_chat_with_agent`.
2. Edit `front-end/app/(app)/(tabs)/ai-chat.tsx` and use the SSE event name to filter which payloads update `accumulatedContent`.
3. (Optional) Run a manual stream call from the front-end or via curl to confirm the event sequence.

Expected evidence during validation (example event sequence, no final `message` or `history`):

    event: session_initialized
    event: agent_updated
    event: message_delta
    event: message_delta
    event: completed

## Validation and Acceptance

- Manual validation: start the backend and front-end, send a chat prompt, and confirm the stream does not emit `message` or `history`. The UI should show the assistant reply only once and continue to receive `completed`.
- Acceptance: The SSE stream output excludes `event: message` and `event: history` while still emitting `event: completed` with `final_message`.

## Idempotence and Recovery

These edits are safe to reapply. If a rollback is needed, restore the `message` emission in `_handle_run_item_stream_event` and re-add the `history` event after streaming completes.

## Artifacts and Notes

- Expected change is limited to `src/app/domain/todo_agents/services.py` and `front-end/app/(app)/(tabs)/ai-chat.tsx`.

## Interfaces and Dependencies

- No new dependencies. The change relies on existing SSE event names (`message_delta`, `tool_result`, `completed`). The `TodoAgentService` stream remains the single source of SSE payloads.

Plan notes: Initial version created to remove redundant `message` and `history` events and align the UI parser.
Plan update (2026-01-05 04:00Z): Marked backend/frontend steps complete after applying the planned code edits.
