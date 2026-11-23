"""3.2 编码与特殊字符：中文/日文/emoji 正确编解码；特殊控制字符；超长 Unicode 字符。"""

from __future__ import annotations

from k31selfcheck2.tests._common import expect_common_ok, send


def test_32_15_中文日文emoji编解码(client, rec):
    """编码与特殊字符：中文/日文/emoji 提问 → 2xx 且 content 无乱码（无 � 替换符）"""
    req = {"model": client.model, "max_tokens": 512,
           "messages": [{"role": "user", "content":
                         "请用中文回答：日本の首都はどこですか？🗼🌸🗾（一句话即可）"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_15_控制字符与Unicode边界(client, rec):
    r"""编码与特殊字符：含 \n\t 与 Unicode 边界字符（如 ​ 零宽空格）→ 2xx 无乱码"""
    probe = ("请复述以下字符串的内容大意：第一行\n第二行\t带缩进"
             "​零宽空格 不间断空格")
    req = {"model": client.model, "max_tokens": 512,
           "messages": [{"role": "user", "content": probe}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_15_超长Unicode字符串(client, rec):
    """编码与特殊字符：超长 Unicode 字符串（~10k 字符）→ 2xx"""
    block = "汉字测试🙂🎉日本語テスト絵文字🚀" * 600  # 约 10k 字符
    rec.extra["input_chars"] = len(block)
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content": f"以下字符串共约多少个字符？只需估算。\n\n{block}"}]}
    r = send(client, rec, req)
    expect_common_ok(rec, r)


def test_32_15_空字符与UTF8BOM处理(client, rec):
    r"""编码与特殊字符：含 \0 空字符与 UTF-8 BOM（\ufeff）的输入 → 妥善处理（2xx 或 4xx，非 5xx/超时）"""
    probe = "﻿请复述以下内容大意：第一段\0隐藏空字符\n第二行正常文本。"  # 以 ﻿(BOM) 开头
    req = {"model": client.model, "max_tokens": 256,
           "messages": [{"role": "user", "content": probe}]}
    r = send(client, rec, req)
    handled = r.ok or (r.status_code is not None and 400 <= r.status_code < 500)
    rec.expect("含 \\0 空字符与 BOM 的输入被妥善处理（2xx 或 4xx，非 5xx/超时）",
               handled and r.error is None, f"status={r.status_code} err={r.error}")
    if r.ok:
        expect_common_ok(rec, r)
        rec.check("含 \\0 与 BOM 的输入被接受（2xx）", True, "行为已记录", soft=True)
    else:
        rec.check("含 \\0 与 BOM 的输入被拒绝（4xx 亦属合法边界处理）", True,
                  f"status={r.status_code}", soft=True)
