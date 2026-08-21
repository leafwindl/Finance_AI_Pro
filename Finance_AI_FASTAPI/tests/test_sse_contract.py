import asyncio

from app.agent_gateway.sse import parse_sse


async def chunks(parts):
    for part in parts:
        yield part


def test_sse_parser_handles_chunked_utf8_and_crlf():
    raw = (
        'event: progress\r\ndata: {"message":"正在处理"}\r\n\r\n'
        'event: delta\ndata: {"text":"中文回答"}\n\n'
    ).encode("utf-8")
    parts = [raw[:17], raw[17:43], raw[43:58], raw[58:]]

    async def collect():
        return [event async for event in parse_sse(chunks(parts))]

    events = asyncio.run(collect())
    assert events == [
        ("progress", {"message": "正在处理"}),
        ("delta", {"text": "中文回答"}),
    ]


def test_sse_parser_ignores_comments_and_invalid_json():
    raw = b': ping\n\nevent: delta\ndata: not-json\n\n'

    async def collect():
        return [event async for event in parse_sse(chunks([raw]))]

    assert asyncio.run(collect()) == []
