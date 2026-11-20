"""检查项#6 结构化输出。

Chat 验证 response_format.type=json_object / json_schema：json_object 仅验证响应
必须是合法 JSON 且非空（不能仅 200）；json_schema 验证输出符合 schema（必填项、
类型、枚举、额外字段限制）。Responses 用 text.format.type=json_schema + schema；
Messages 用 output_config.format.type=json_schema + schema（不套用 Chat 字段，
协议开放时验证，未开放记硬失败）。
"""

from __future__ import annotations

import json

from k31selfcheck.protocols import (
    ProtocolClient,
    messages_text,
    responses_text,
)
from k31selfcheck.tests._common import attach_proto, expect_protocol_open, proto  # noqa: F401

_BOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "author": {"type": "string"},
        "year": {"type": "integer"},
        "genre": {"type": "string", "enum": ["novel", "poem", "essay"]},
    },
    "required": ["title", "author", "year", "genre"],
    "additionalProperties": False,
}

_PROMPT = ("给出一本虚构图书的信息，包含 title（书名）、author（作者）、"
           "year（出版年份，整数）、genre（取 novel/poem/essay 之一）。")


def _validate_book(rec, obj, source: str) -> None:
    rec.expect(f"{source} 输出为 object", isinstance(obj, dict), f"type={type(obj).__name__}")
    if not isinstance(obj, dict):
        return
    missing = [k for k in _BOOK_SCHEMA["required"] if k not in obj]
    rec.expect(f"{source} 必填项齐全（title/author/year/genre）", not missing,
               f"missing={missing} keys={list(obj)}")
    if "title" in obj:
        rec.expect(f"{source} title 为 string", isinstance(obj["title"], str),
                   f"title={obj['title']!r}")
    if "author" in obj:
        rec.expect(f"{source} author 为 string", isinstance(obj["author"], str),
                   f"author={obj['author']!r}")
    if "year" in obj:
        rec.expect(f"{source} year 为 integer",
                   isinstance(obj["year"], int) and not isinstance(obj["year"], bool),
                   f"year={obj['year']!r}")
    if "genre" in obj:
        rec.expect(f"{source} genre 命中枚举", obj["genre"] in ("novel", "poem", "essay"),
                   f"genre={obj['genre']!r}")
    extra = [k for k in obj if k not in _BOOK_SCHEMA["properties"]]
    rec.expect(f"{source} 无额外字段（additionalProperties=false）", not extra,
               f"extra_keys={extra}")


def _parse_json(rec, text: str, source: str):
    """解析并断言非空 JSON，返回对象或 None。"""
    rec.expect(f"{source} 输出非空", bool(text and text.strip()),
               f"text[:100]={text[:100]!r}")
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        rec.expect(f"{source} 输出为合法 JSON", False, f"{exc}; text[:200]={text[:200]!r}")
        return None
    rec.expect(f"{source} 输出为合法 JSON", True, "")
    return obj


def test_k06_chat_json_object(client, rec):
    """Chat response_format.type=json_object：响应必须是合法 JSON 且非空（仅 200 不算通过）"""
    req = {"model": client.model, "messages": [{"role": "user", "content": _PROMPT}],
           "max_completion_tokens": 4096,
           "response_format": {"type": "json_object"}}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    obj = _parse_json(rec, r.content, "json_object")
    if obj is not None:
        rec.expect("json_object 输出非空对象", bool(obj), f"parsed={obj}")


def test_k06_chat_json_schema(client, rec):
    """Chat response_format json_schema：输出符合 schema（必填/类型/枚举/额外字段限制）"""
    req = {"model": client.model, "messages": [{"role": "user", "content": _PROMPT}],
           "max_completion_tokens": 4096,
           "response_format": {"type": "json_schema",
                               "json_schema": {"name": "book_info", "schema": _BOOK_SCHEMA}}}
    r = client.chat(req)
    rec.attach_result(req, r, client.chat_completions_url, client.masked_headers())
    rec.expect("HTTP 2xx", r.ok, f"status={r.status_code} err={r.error}")
    obj = _parse_json(rec, r.content, "json_schema")
    if obj is not None:
        _validate_book(rec, obj, "json_schema")


def test_k06_responses_json_schema(proto, rec):
    """Responses text.format.type=json_schema + schema：输出符合 schema；未开放记硬失败"""
    payload = {"input": _PROMPT, "max_output_tokens": 4096,
               "text": {"format": {"type": "json_schema", "name": "book_info",
                                   "schema": _BOOK_SCHEMA}}}
    r = proto.call_responses(payload)
    attach_proto(rec, proto, ProtocolClient.RESPONSES_PATH, payload, r)
    expect_protocol_open(rec, "Responses json_schema", r, "Responses /v1/responses")
    obj = _parse_json(rec, responses_text(r), "Responses json_schema")
    if obj is not None:
        _validate_book(rec, obj, "Responses json_schema")


def test_k06_messages_json_schema(proto, rec):
    """Messages output_config.format.type=json_schema + schema：输出符合 schema；未开放记硬失败"""
    payload = {"messages": [{"role": "user", "content": _PROMPT}], "max_tokens": 4096,
               "output_config": {"format": {"type": "json_schema", "schema": _BOOK_SCHEMA}}}
    r = proto.call_messages(payload)
    attach_proto(rec, proto, ProtocolClient.MESSAGES_PATH, payload, r)
    expect_protocol_open(rec, "Messages json_schema", r, "Messages /anthropic/v1/messages")
    obj = _parse_json(rec, messages_text(r), "Messages json_schema")
    if obj is not None:
        _validate_book(rec, obj, "Messages json_schema")
