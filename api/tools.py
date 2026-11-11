"""ツール呼び出し（コマ12。コマ13で get_inquiry を追加し、MCP サーバーからも使う）

LLM は関数を実行しない。「この関数を、この引数で呼びたい」という**要求**（tool_calls）を返すだけである。
実際に関数を実行するのは、このアプリである。だから、次の3つはアプリの責任になる。

  1. ツールの定義: 名前・説明・引数のスキーマ（JSON Schema）を、要求のたびにモデルに渡す
  2. ツールの実行: モデルが作った引数を検証し、利用者の権限で実行する（モデルの言うとおりにしない）
  3. 実行ループ : 結果を tool のメッセージとしてモデルに返し、最終的な答えが出るまで繰り返す（回数に上限を付ける）

このファイルの関数は、Azure にも OpenRouter にもつながずにテストできる
（データの保存先 repo と、モデルを呼ぶ関数 call_model を、引数で受け取るようにしてある）。
"""

import json
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import authz

STATUSES = ("未対応", "振り分け済み", "要確認", "対応中", "完了")


# =====================================================================
# 1. ツールの定義（引数のスキーマは Pydantic のモデルから作る）
# =====================================================================
class SearchArgs(BaseModel):
    """search_inquiries の引数"""

    model_config = ConfigDict(extra="forbid")  # 定義にない引数は受け付けない

    keyword: str = Field(min_length=1, max_length=50, description="件名か本文に含まれる言葉（例: VPN）")
    status: Optional[Literal["未対応", "振り分け済み", "要確認", "対応中", "完了"]] = Field(
        default=None, description="この状態の問い合わせだけに絞る。指定しなければ、すべての状態"
    )


class UpdateStatusArgs(BaseModel):
    """update_inquiry_status の引数"""

    model_config = ConfigDict(extra="forbid")

    inquiry_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="問い合わせの ID（search_inquiries の結果の id）",
    )
    status: Literal["対応中", "完了"] = Field(description="変えた後のステータス（対応中・完了のどちらか）")


class GetInquiryArgs(BaseModel):
    """get_inquiry の引数"""

    model_config = ConfigDict(extra="forbid")

    inquiry_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        description="問い合わせの ID（search_inquiries の結果の id）",
    )


@dataclass
class Tool:
    name: str
    description: str
    args_model: type
    run: Callable  # run(args, principal, repo) -> 結果の辞書
    read_only: bool = False  # データを変えないツールか（MCP の注釈 readOnlyHint に使う）


def schema_of(args_model):
    """Pydantic のモデルから、ツールの引数の JSON Schema を作る"""
    schema = args_model.model_json_schema()
    schema.pop("title", None)
    schema.pop("description", None)
    return schema


def tool_definitions(tools):
    """モデルに渡すツールの定義（OpenAI 互換 API の tools の形）"""
    return [
        {
            "type": "function",
            "function": {"name": t.name, "description": t.description, "parameters": schema_of(t.args_model)},
        }
        for t in tools.values()
    ]


# =====================================================================
# 2. ツールの実行（アプリの責任: 引数の検証と認可）
# =====================================================================
MAX_RESULTS = 5  # 検索の結果としてモデルに渡す件数の上限（入力トークンを増やしすぎない）


def run_search(args, principal, repo):
    """問い合わせを検索する。担当者はすべて、それ以外は自分が登録したものだけ（コマ11と同じ範囲）"""
    authz.require_user(principal)
    owner = None if authz.STAFF in principal.roles else principal.user_id
    items = repo.search(args.keyword, args.status, owner, MAX_RESULTS)
    return {
        "count": len(items),
        "items": [{"id": i["id"], "title": i["title"], "status": i["status"]} for i in items],
    }


def run_get_inquiry(args, principal, repo):
    """問い合わせ1件の詳細を返す。担当者はすべて、それ以外は自分が登録したものだけ（他人のものは「ない」とする）"""
    authz.require_user(principal)
    item = repo.get(args.inquiry_id)
    if item is None or (authz.STAFF not in principal.roles and item.get("createdBy") != principal.user_id):
        raise authz.NotFound("その ID の問い合わせはない")
    return {
        "id": item["id"],
        "title": item["title"],
        "body": item.get("body", ""),
        "status": item["status"],
        "assignee": item.get("assignee"),
    }


def run_update_status(args, principal, repo):
    """問い合わせのステータスを変える（担当者だけ）"""
    authz.require_role(principal, authz.STAFF)
    item = repo.get(args.inquiry_id)
    if item is None:
        raise authz.NotFound("その ID の問い合わせはない")
    before = item["status"]
    repo.update_status(args.inquiry_id, args.status)
    return {"id": args.inquiry_id, "title": item["title"], "before": before, "after": args.status}


TOOLS = {
    t.name: t
    for t in [
        Tool(
            "search_inquiries",
            "社内の問い合わせを、言葉で検索する。問い合わせの ID・件名・状態を返す（最大5件）。"
            "ステータスを変える前に、対象の問い合わせの ID を調べるのにも使う。",
            SearchArgs,
            run_search,
            read_only=True,
        ),
        Tool(
            "get_inquiry",
            "問い合わせ1件の詳細（本文・状態・担当）を返す。ID は search_inquiries で調べたものを使う。",
            GetInquiryArgs,
            run_get_inquiry,
            read_only=True,
        ),
        Tool(
            "update_inquiry_status",
            "問い合わせ1件のステータスを変える。担当者だけが使える。ID は search_inquiries で調べたものを使う。",
            UpdateStatusArgs,
            run_update_status,
        ),
    ]
}


def execute_tool(name, arguments, principal, repo, tools=TOOLS):
    """モデルが要求したツールを、アプリが実行する。結果（辞書）を返す

      arguments : モデルが作った引数（JSON の文字列）。モデルの出力なので、信頼できない入力として扱う
    失敗も例外にせず {"error": "…"} の形で返す。それをモデルに渡せば、モデルは利用者に事情を説明できる。
    """
    tool = tools.get(name)
    if tool is None:
        return {"error": f"{name} というツールはない"}

    try:
        args = tool.args_model.model_validate(json.loads(arguments))
    except (ValueError, ValidationError) as e:
        return {"error": f"引数が正しくない: {e}"}

    try:
        return tool.run(args, principal, repo)
    except authz.AuthError as e:
        return {"error": e.message}


# =====================================================================
# 3. 実行ループ
# =====================================================================
def assistant_message(response):
    """モデルの応答（tool_calls を含む）を、会話に加えるメッセージの形にする"""
    return {
        "role": "assistant",
        "content": response.get("content"),
        "tool_calls": [
            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in response["tool_calls"]
        ],
    }


def run_tool_loop(messages, call_model, execute, max_steps, steps=None):
    """モデルを呼び、ツールの要求があれば実行して結果を返す、を繰り返す

      call_model(messages) : モデルを1回呼び、{"content": 文字列か None, "tool_calls": [{"id", "name", "arguments"}]} を返す
      execute(name, arguments) : ツールを実行し、結果の辞書を返す
      max_steps            : モデルを呼ぶ回数の上限（ツールを呼び続けて止まらないことに備える）
      steps                : 実行したツールの記録を書き足すリスト（途中で失敗しても、どこまで実行したかが残る）

    戻り値: (最終的な答えの文字列, 実行したツールの記録のリスト)
    """
    steps = [] if steps is None else steps
    for _ in range(max_steps):
        response = call_model(messages)
        calls = response.get("tool_calls") or []
        if not calls:
            return response.get("content") or "", steps  # ツールの要求がない → これが最終的な答え

        messages.append(assistant_message(response))
        for call in calls:
            result = execute(call["name"], call["arguments"])
            steps.append({"tool": call["name"], "arguments": call["arguments"], "result": result})
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}
            )

    return f"ツールを使う回数の上限（{max_steps}回）に達したので、ここで止めた", steps


# =====================================================================
# Cosmos DB を使った問い合わせの保存先（教員が用意したもの）
# =====================================================================
class CosmosInquiryRepo:
    def __init__(self, container):
        self.container = container

    def search(self, keyword, status, owner, limit):
        query = (
            "SELECT TOP @limit c.id, c.title, c.status FROM c "
            "WHERE (CONTAINS(c.title, @kw, true) OR CONTAINS(c.body, @kw, true))"
        )
        params = [{"name": "@limit", "value": limit}, {"name": "@kw", "value": keyword}]
        if status:
            query += " AND c.status = @status"
            params.append({"name": "@status", "value": status})
        if owner:
            query += " AND c.createdBy = @owner"
            params.append({"name": "@owner", "value": owner})
        return list(self.container.query_items(query=query, parameters=params, enable_cross_partition_query=True))

    def get(self, inquiry_id):
        from azure.cosmos.exceptions import CosmosResourceNotFoundError

        try:
            return self.container.read_item(item=inquiry_id, partition_key=inquiry_id)
        except CosmosResourceNotFoundError:
            return None

    def update_status(self, inquiry_id, status):
        self.container.patch_item(
            item=inquiry_id,
            partition_key=inquiry_id,
            patch_operations=[{"op": "set", "path": "/status", "value": status}],
        )
