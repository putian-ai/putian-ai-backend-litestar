"""Shared scheduling helpers for todo agent tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class TimeBlock:
    start_time: datetime
    end_time: datetime


def build_blocks_from_todos(existing: Iterable, user_tz: ZoneInfo) -> list[TimeBlock]:
    blocks: list[TimeBlock] = []
    for todo in existing:
        if todo.start_time and todo.end_time:
            t_start = todo.start_time.astimezone(user_tz)
            t_end = todo.end_time.astimezone(user_tz)
        elif todo.alarm_time:
            t_start = todo.alarm_time.astimezone(user_tz)
            t_end = t_start + timedelta(hours=1)
        else:
            continue
        blocks.append(TimeBlock(t_start, t_end))
    return sorted(blocks, key=lambda b: b.start_time)


def has_conflict(start_time: datetime, end_time: datetime, blocks: Sequence[TimeBlock]) -> bool:
    return any(block.start_time < end_time and block.end_time > start_time for block in blocks)


def find_free_slot_in_blocks(
    search_start: datetime,
    search_end: datetime,
    duration: timedelta,
    blocks: Sequence[TimeBlock],
) -> datetime | None:
    current = search_start
    for block in sorted(blocks, key=lambda b: b.start_time):
        if current + duration <= block.start_time:
            return current
        if block.end_time > current:
            current = block.end_time

    if current + duration <= search_end:
        return current
    return None
