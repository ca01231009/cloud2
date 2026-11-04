"""api/tools.py を確かめるテスト（コマ12）

実行のしかた（Codespace のターミナルで。Azure にも OpenRouter にもつながない）
  pip install pytest pydantic
  python -m pytest lesson12/test_tools.py -v

Cosmos DB の代わりに、メモリに置いた「偽物の保存先」（FakeRepo）を使う。
モデルの代わりに、用意した応答を順に返す「偽物のモデル」（FakeModel）と、モックLLM（llm.MockProvider）を使う。
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

import auth  # noqa: E402
import llm  # noqa: E402
import tools  # noqa: E402

AOI = auth.Principal("user-aoi", "青井", ())
SORA = auth.Principal("staff-sora", "空木", ("staff",))
VPN_AOI = "aaaaaaaa-0000-4000-8000-000000000001"
VPN_KAI = "bbbbbbbb-0000-4000-8000-000000000002"


class FakeRepo:
    def __init__(self):
        self.items = {
            VPN_AOI: {"id": VPN_AOI, "title": "自宅から VPN が切れる", "body": "", "status": "未対応", "createdBy": "user-aoi"},
            VPN_KAI: {"id": VPN_KAI, "title": "VPN がつながらない", "body": "", "status": "未対応", "createdBy": "user-kai"},
        }

    def search(self, keyword, status, owner, limit):
        return [
            i
            for i in self.items.values()
            if keyword in i["title"] and (status is None or i["status"] == status) and (owner is None or i["createdBy"] == owner)
        ][:limit]

    def get(self, inquiry_id):
        return self.items.get(inquiry_id)

    def update_status(self, inquiry_id, status):
        self.items[inquiry_id]["status"] = status


def args(**kw):
    return json.dumps(kw, ensure_ascii=False)


# ---------------------------------------------------------------------
# ツールの定義（演習手順4）
# ---------------------------------------------------------------------
def test_定義_検索のツールに名前と説明と引数のスキーマがある():
    definition = {d["function"]["name"]: d["function"] for d in tools.tool_definitions(tools.TOOLS)}["search_inquiries"]
    assert definition["description"]
    assert definition["parameters"]["required"] == ["keyword"]


def test_定義_ステータスの変更で選んでよい値がスキーマに書かれている():
    definition = {d["function"]["name"]: d["function"] for d in tools.tool_definitions(tools.TOOLS)}
    status = definition["update_inquiry_status"]["parameters"]["properties"]["status"]
    assert sorted(status["enum"]) == ["完了", "対応中"]
    assert status.get("description")


# ---------------------------------------------------------------------
# ツールの実行: 引数の検証と認可（演習手順5）
# ---------------------------------------------------------------------
def test_実行_担当者は検索で全員の問い合わせが見える():
    result = tools.execute_tool("search_inquiries", args(keyword="VPN"), SORA, FakeRepo())
    assert result["count"] == 2


def test_実行_一般の利用者は検索で自分の問い合わせだけが見える():
    result = tools.execute_tool("search_inquiries", args(keyword="VPN"), AOI, FakeRepo())
    assert [i["id"] for i in result["items"]] == [VPN_AOI]


def test_実行_担当者はステータスを変えられる():
    repo = FakeRepo()
    result = tools.execute_tool("update_inquiry_status", args(inquiry_id=VPN_KAI, status="対応中"), SORA, repo)
    assert result["after"] == "対応中" and repo.items[VPN_KAI]["status"] == "対応中"


def test_実行_決まりにない値は実行せずにエラーを返す():
    repo = FakeRepo()
    result = tools.execute_tool("update_inquiry_status", args(inquiry_id=VPN_KAI, status="解決済み"), SORA, repo)
    assert "error" in result and repo.items[VPN_KAI]["status"] == "未対応"


def test_実行_定義にない引数は実行せずにエラーを返す():
    repo = FakeRepo()
    result = tools.execute_tool("update_inquiry_status", args(inquiry_id=VPN_KAI, status="完了", force=True), SORA, repo)
    assert "error" in result and repo.items[VPN_KAI]["status"] == "未対応"


def test_実行_JSONとして読めない引数はエラーを返す():
    result = tools.execute_tool("search_inquiries", '{"keyword": "VPN"', SORA, FakeRepo())
    assert "error" in result


def test_実行_一般の利用者はステータスを変えられない():
    repo = FakeRepo()
    result = tools.execute_tool("update_inquiry_status", args(inquiry_id=VPN_AOI, status="完了"), AOI, repo)
    assert "error" in result and repo.items[VPN_AOI]["status"] == "未対応"


def test_実行_定義にないツールはエラーを返す():
    result = tools.execute_tool("delete_inquiry", args(inquiry_id=VPN_AOI), SORA, FakeRepo())
    assert "error" in result


# ---------------------------------------------------------------------
# 実行ループ（演習手順6）
# ---------------------------------------------------------------------
class FakeModel:
    """呼ばれるたびに、用意した応答を先頭から1つずつ返す。受け取った messages を記録する"""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.received = []

    def __call__(self, messages):
        self.received.append([dict(m) for m in messages])
        return self.responses.pop(0)


def call(name, **kw):
    return {"content": None, "tool_calls": [{"id": f"call_{name}", "name": name, "arguments": args(**kw)}]}


def test_ループ_ツールの結果をtoolのメッセージでモデルに返す():
    model = FakeModel(call("search_inquiries", keyword="VPN"), {"content": "2件ある", "tool_calls": []})
    messages = [{"role": "user", "content": "VPN を探して"}]
    reply, steps = tools.run_tool_loop(messages, model, lambda n, a: {"count": 2}, max_steps=4)
    assert reply == "2件ある" and len(steps) == 1
    second = model.received[1]
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["id"] == "call_search_inquiries"
    assert second[-1] == {"role": "tool", "tool_call_id": "call_search_inquiries", "content": '{"count": 2}'}


def test_ループ_ツールを要求しなければ1回で終わる():
    model = FakeModel({"content": "こんにちは", "tool_calls": []})
    reply, steps = tools.run_tool_loop([{"role": "user", "content": "こんにちは"}], model, None, max_steps=4)
    assert reply == "こんにちは" and steps == []


def test_ループ_上限の回数で止まる():
    model = FakeModel(*[call("search_inquiries", keyword="VPN") for _ in range(10)])
    reply, steps = tools.run_tool_loop([{"role": "user", "content": "探して"}], model, lambda n, a: {"count": 0}, max_steps=3)
    assert len(model.received) == 3 and "上限" in reply


def test_ループ_モックLLMで検索して答えるまで通る(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_FAULT", "none")
    provider = llm.MockProvider()
    definitions = tools.tool_definitions(tools.TOOLS)
    repo = FakeRepo()
    reply, steps = tools.run_tool_loop(
        [{"role": "user", "content": "「VPN」の問い合わせを探して"}],
        lambda m: provider.complete_tools("mock-model", m, definitions, 400),
        lambda n, a: tools.execute_tool(n, a, SORA, repo),
        max_steps=4,
    )
    assert steps[0]["tool"] == "search_inquiries" and "2 件見つかった" in reply
