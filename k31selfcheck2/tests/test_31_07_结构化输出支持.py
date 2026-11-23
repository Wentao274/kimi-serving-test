"""3.1 结构化输出支持：json_object（强制输出合法 JSON）和 json_schema（按 Schema 定义输出）。

json_schema 至少需支持 type、properties、required、enum、items 等关键字；
校验 required 键、类型、enum 值、嵌套 items 数组元素类型。
"""

from __future__ import annotations

import json

from k31selfcheck2.tests._common import expect_common_ok, send

_DISH_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "category": {"type": "string", "enum": ["appetizer", "main", "dessert"]},
        "price": {"type": "number"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "calories": {"type": "integer"},
    },
    "required": ["name", "category", "price", "tags"],
    "additionalProperties": False,
}

_PROMPT = ("请给出一道虚构菜品的信息：name（菜品名）、category（appetizer/main/dessert 之一）、"
           "price（价格，数字）、tags（字符串数组，如 [\"辣\", \"素食\"]）、calories（整数）。")


def _parse_content_json(rec, text: str, source: str):
    """解析并硬断言非空合法 JSON，返回对象或 None。"""
    rec.expect(f"{source} 输出非空", bool(text and text.strip()),
               f"text[:120]={(text or '')[:120]!r}")
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        rec.expect(f"{source} 输出为合法 JSON", False,
                   f"{exc}; text[:200]={(text or '')[:200]!r}")
        return None
    rec.expect(f"{source} 输出为合法 JSON", True, "")
    return obj


def test_31_07_json_object输出合法JSON(client, rec):
    """结构化输出支持：json_object 模式输出合法 JSON"""
    req = {"model": client.model, "max_tokens": 2048,
           "messages": [{"role": "user", "content": _PROMPT + " 请以 JSON 格式返回。"}],
           "response_format": {"type": "json_object"}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    obj = _parse_content_json(rec, r.content, "json_object")
    if obj is not None:
        rec.expect("json_object 输出为非空对象", isinstance(obj, dict) and bool(obj),
                   f"parsed={obj}")


def test_31_07_json_schema按Schema输出(client, rec):
    """结构化输出支持：json_schema 按 Schema（type/properties/required/enum/items）输出"""
    req = {"model": client.model, "max_tokens": 2048,
           "messages": [{"role": "user", "content": _PROMPT}],
           "response_format": {"type": "json_schema",
                                "json_schema": {"name": "dish_info", "schema": _DISH_SCHEMA}}}
    r = send(client, rec, req)
    expect_common_ok(rec, r)
    obj = _parse_content_json(rec, r.content, "json_schema")
    if obj is None:
        return
    rec.expect("json_schema 输出为 object", isinstance(obj, dict),
               f"type={type(obj).__name__}")
    if not isinstance(obj, dict):
        return
    missing = [k for k in _DISH_SCHEMA["required"] if k not in obj]
    rec.expect("required 键齐全（name/category/price/tags）", not missing,
               f"missing={missing} keys={list(obj)}")
    if "name" in obj:
        rec.expect("name 类型为 string", isinstance(obj["name"], str),
                   f"name={obj['name']!r}")
    if "category" in obj:
        rec.expect("category 命中 enum（appetizer/main/dessert）",
                   obj["category"] in ("appetizer", "main", "dessert"),
                   f"category={obj['category']!r}")
    if "price" in obj:
        rec.expect("price 类型为 number",
                   isinstance(obj["price"], (int, float)) and not isinstance(obj["price"], bool),
                   f"price={obj['price']!r}")
    if "tags" in obj:
        rec.expect("tags 类型为 array（嵌套 items）", isinstance(obj["tags"], list),
                   f"tags={obj['tags']!r}")
        if isinstance(obj["tags"], list):
            bad = [t for t in obj["tags"] if not isinstance(t, str)]
            rec.expect("tags 数组元素类型均为 string（items.type）", not bad,
                       f"bad_items={bad[:3]}")
