from __future__ import annotations

import codecs
import json
import re
from collections.abc import AsyncIterator
from typing import Any


def encode_sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def parse_sse(byte_stream: AsyncIterator[bytes]) -> AsyncIterator[tuple[str, dict]]:
    """解析任意 HTTP 分块边界下的 SSE，支持 LF/CRLF 和多 data 行。"""
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""

    async for chunk in byte_stream:
        buffer += decoder.decode(chunk)
        while True:
            match = re.search(r"\r?\n\r?\n", buffer)
            if match is None:
                break
            raw_event = buffer[: match.start()]
            buffer = buffer[match.end() :]
            parsed = _parse_event(raw_event)
            if parsed is not None:
                yield parsed

    buffer += decoder.decode(b"", final=True)
    if buffer.strip():
        parsed = _parse_event(buffer)
        if parsed is not None:
            yield parsed


def _parse_event(raw_event: str) -> tuple[str, dict] | None:
    event = "message"
    data_lines: list[str] = []
    for raw_line in raw_event.splitlines():
        line = raw_line.rstrip("\r")
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if not data_lines:
        return None
    try:
        payload = json.loads("\n".join(data_lines))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return event, payload
