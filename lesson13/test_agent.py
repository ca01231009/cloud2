"""api/mcp_server.py・api/agent.py を確かめるテスト（コマ13）

実行のしかた（Codespace のターミナルで。Azure にも OpenRouter にもつながない）
  pip install pytest pydantic
  python -m pytest lesson13/test_agent.py -v

Cosmos DB の代わりに「偽物の保存先」（FakeRepo）を使い、MCP クライアントは HTTP を通さずにサーバーの関数を直接呼ぶ。
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "lesson13"))

import agent  # noqa: E402
import auth  # noqa: E402
import llm  # noqa: E402
import mcp_server  # noqa: E402
import tools  # noqa: E402
from mcp_client import McpClient, McpError, to_llm_tools  # noqa: E402

KAI = auth.Principal("user-kai", "海野", ())
SORA = auth.Principal("staff-sora", "空木", ("staff",))
IDS = [f"aaaaaaaa-0000-4000-8000-00000000000{i}" for i in range(1, 5)]


class FakeRepo:
    def __init__(self):
        self.items = {
            i: {"id": i, "title": f"VPN の問い合わせ{n}", "body": "", "status": "未対応", "createdBy": "user-kai"}
            for n, i in enumerate(IDS, 1)
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


def client_for(principal, repo):
    return McpClient(lambda message: mcp_server.handle(message, principal, repo))


def limits(allow_write=True, **kw):
    values = dict(max_steps=8, max_repeats=2, max_errors=3, max_writes=3)
    values.update(kw)
    allowed = {"search_inquiries", "get_inquiry"} | ({"update_inquiry_status"} if allow_write else set())
    return agent.Limits(allowed=allowed, write_tools={"update_inquiry_status"}, **values)


def step(tool="search_inquiries", arguments='{"keyword": "VPN"}', result=None, refused=False):
    return {"tool": tool, "arguments": arguments, "result": result or {"count": 0}, "refused": refused}


# ---------------------------------------------------------------------
# MCP サーバー（教員が用意した部分）
# ---------------------------------------------------------------------
def test_MCP_ツールの一覧に名前とスキーマと注釈がある():
    listed = {t["name"]: t for t in client_for(SORA, FakeRepo()).list_tools()}
    assert set(listed) == {"search_inquiries", "get_inquiry", "update_inquiry_status"}
    assert listed["search_inquiries"]["inputSchema"]["required"] == ["keyword"]
    assert listed["get_inquiry"]["annotations"]["readOnlyHint"] is True
    assert listed["update_inquiry_status"]["annotations"]["readOnlyHint"] is False


def test_MCP_ツールを呼ぶと結果が返る():
    result = client_for(SORA, FakeRepo()).call_tool("search_inquiries", {"keyword": "VPN"})
    assert result["count"] == 4


def test_MCP_知らないメソッドはプロトコルのエラーになる():
    with pytest.raises(McpError):
        client_for(SORA, FakeRepo()).request("unknown/method")


def test_MCP_知らないツールはプロトコルのエラーになる():
    response = mcp_server.handle(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "delete_inquiry"}}, SORA, FakeRepo()
    )
    assert response["error"]["code"] == mcp_server.INVALID_PARAMS


def test_MCP_通知には応答しない():
    assert mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, SORA, FakeRepo()) is None


def test_MCP_ヘッダーと本文のバージョンが違えば断る():
    message = {"params": {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}}
    with pytest.raises(mcp_server.RpcError):
        mcp_server.check_headers(message, {"mcp-protocol-version": "2025-11-25"})


# ---------------------------------------------------------------------
# MCP の結果の形（演習手順4）
# ---------------------------------------------------------------------
def test_結果_ツールの失敗はisErrorで伝える():
    result = mcp_server.tool_result({"error": "その ID の問い合わせはない"})
    assert result["isError"] is True
    assert result["content"][0]["text"] == "その ID の問い合わせはない"
    assert "structuredContent" not in result


def test_結果_成功はisErrorがFalseで構造化された結果が付く():
    result = mcp_server.tool_result({"count": 1})
    assert result["isError"] is False and result["structuredContent"] == {"count": 1}


def test_結果_権限がないとクライアントにエラーとして届く():
    repo = FakeRepo()
    result = client_for(KAI, repo).call_tool("update_inquiry_status", {"inquiry_id": IDS[0], "status": "完了"})
    assert "担当者" in result["error"] and repo.items[IDS[0]]["status"] == "未対応"


# ---------------------------------------------------------------------
# 停止条件（演習手順5）
# ---------------------------------------------------------------------
def test_停止_別の呼び出しなら続ける():
    steps = [step(arguments='{"keyword": "VPN"}'), step(arguments='{"keyword": "鍵"}')]
    assert agent.stop_reason(steps, limits()) is None


def test_停止_同じ呼び出しが上限を超えたら止める():
    assert agent.stop_reason([step(), step()], limits()) is None
    assert agent.stop_reason([step(), step(), step()], limits()) == agent.REPEATED


def test_停止_失敗が続いたら止める():
    steps = [step(arguments=str(i), result={"error": "ない"}) for i in range(3)]
    assert agent.stop_reason(steps, limits()) == agent.ERRORS


def test_停止_途中で成功していれば失敗の数は続かない():
    steps = [
        step(arguments="1", result={"error": "ない"}),
        step(arguments="2", result={"error": "ない"}),
        step(arguments="3"),
        step(arguments="4", result={"error": "ない"}),
    ]
    assert agent.stop_reason(steps, limits()) is None


# ---------------------------------------------------------------------
# 権限の範囲（演習手順6）
# ---------------------------------------------------------------------
def definitions():
    return to_llm_tools(client_for(SORA, FakeRepo()).list_tools())


def test_権限_許したツールだけをモデルに見せる():
    names = {d["function"]["name"] for d in agent.visible_tools(definitions(), limits(allow_write=False))}
    assert names == {"search_inquiries", "get_inquiry"}


def test_権限_許していないツールの要求は断る():
    assert agent.refusal("update_inquiry_status", [], limits(allow_write=False))
    assert agent.refusal("search_inquiries", [], limits(allow_write=False)) is None


def test_権限_データを変える回数の上限で断る():
    done = [step(tool="update_inquiry_status") for _ in range(3)]
    assert agent.refusal("update_inquiry_status", done, limits())
    assert agent.refusal("update_inquiry_status", done[:2], limits()) is None
    assert agent.refusal("search_inquiries", done, limits()) is None


def test_権限_断った呼び出しは回数に数えない():
    done = [step(tool="update_inquiry_status", refused=True) for _ in range(3)]
    assert agent.refusal("update_inquiry_status", done, limits()) is None


# ---------------------------------------------------------------------
# 全体（モックLLM → エージェント → MCP クライアント → MCP サーバー）
# ---------------------------------------------------------------------
def run(monkeypatch, text, principal, allow_write, fault="none", **kw):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_FAULT", fault)
    provider = llm.MockProvider()
    repo = FakeRepo()
    client = client_for(principal, repo)
    result = agent.run_agent(
        [{"role": "system", "content": "テスト"}, {"role": "user", "content": text}],
        to_llm_tools(client.list_tools()),
        lambda m, t: provider.complete_tools("mock-model", m, t, 400),
        lambda n, a: client.call_tool(n, json.loads(a)),
        limits(allow_write, **kw),
    )
    return result, repo


def test_全体_検索して更新し上限で止める(monkeypatch):
    result, repo = run(monkeypatch, "「VPN」の未対応の問い合わせをすべて「対応中」にして", SORA, True)
    assert result.stop_reason == agent.ANSWERED
    assert [i["status"] for i in repo.items.values()].count("対応中") == 3


def test_全体_読むだけのエージェントは更新しない(monkeypatch):
    result, repo = run(monkeypatch, "「VPN」の未対応の問い合わせをすべて「対応中」にして", SORA, False)
    assert result.stop_reason == agent.ANSWERED
    assert all(i["status"] == "未対応" for i in repo.items.values())


def test_全体_範囲を守らないモデルでも更新されない(monkeypatch):
    result, repo = run(monkeypatch, "「VPN」の未対応の問い合わせをすべて「対応中」にして", SORA, False, fault="ignore_scope")
    assert any(s["refused"] for s in result.steps)
    assert all(i["status"] == "未対応" for i in repo.items.values())


def test_全体_同じ検索を繰り返すモデルを止める(monkeypatch):
    result, _ = run(monkeypatch, "「VPN」の問い合わせを探して", SORA, False, fault="tool_loop")
    assert result.stop_reason == agent.REPEATED


def test_全体_失敗が続くモデルを止める(monkeypatch):
    result, _ = run(monkeypatch, "「VPN」の問い合わせを探して", SORA, False, fault="error_loop")
    assert result.stop_reason == agent.ERRORS
