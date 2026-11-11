"""MCP サーバー（コマ13）: 自作の API のツールを、MCP という共通の形で公開する

MCP（Model Context Protocol）では、クライアントは JSON-RPC 2.0 のメッセージを、1つの URL（/api/mcp）に POST する。
  tools/list      : 使えるツールの一覧（名前・説明・引数のスキーマ）を返す
  tools/call      : ツールを実行して結果を返す
  server/discover : サーバーの対応バージョンと機能を返す（2026-07-28 版の仕様）
  initialize      : 古い版（2025-11-25 まで）のクライアントのための最初のあいさつ

このファイルは、学ぶために仕様の必要な部分だけを手で書いたものである。
実務では、公式の MCP SDK や、Azure Functions の MCP 拡張を使うことも検討する。

このサーバーは、要求の Authorization ヘッダーのトークンで利用者を確かめ、ツールをその利用者の権限で実行する
（コマ11・12と同じ。function_app.py の mcp が principal を渡す）。
"""

import json

import tools

PROTOCOL_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"
SERVER_INFO = {"name": "kamome-inquiry-mcp", "version": "1.0.0"}
INSTRUCTIONS = "カモメ物産（架空の会社）の問い合わせを検索・更新するツールを提供する。"

# JSON-RPC のエラーの番号
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
HEADER_MISMATCH = -32020


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def list_tools(registry):
    """tools/list の結果を作る"""
    return {
        "resultType": "complete",
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": tools.schema_of(t.args_model),
                # 注釈は「ヒント」である。信頼できないサーバーの注釈を、クライアントが判断の根拠にしてはいけない
                "annotations": {"readOnlyHint": t.read_only},
            }
            for t in registry.values()
        ],
        "ttlMs": 60000,
        "cacheScope": "private",
    }


def tool_result(result):
    """execute_tool の結果（辞書）を、tools/call の結果の形にする

    ツールの実行の失敗（引数の誤り・権限がない など）は、プロトコルのエラーではなく、
    結果の isError を true にして返す。モデルがそれを読んで、自分で直せるようにするためである。
    """
    if "error" in result:
        return {"resultType": "complete", "content": [{"type": "text", "text": result["error"]}], "isError": True}
    text = json.dumps(result, ensure_ascii=False)
    return {
        "resultType": "complete",
        "content": [{"type": "text", "text": text}],
        "structuredContent": result,
        "isError": False,
    }


def call_tool(params, principal, repo, registry):
    """tools/call を処理する。ツールが見つからないのはプロトコルのエラー、実行の失敗は結果で返す"""
    name = params.get("name")
    if name not in registry:
        raise RpcError(INVALID_PARAMS, f"Unknown tool: {name}")
    arguments = json.dumps(params.get("arguments") or {}, ensure_ascii=False)
    return tool_result(tools.execute_tool(name, arguments, principal, repo, registry))


def discover():
    return {
        "resultType": "complete",
        "supportedVersions": [PROTOCOL_VERSION],
        "capabilities": {"tools": {}},
        "instructions": INSTRUCTIONS,
        "ttlMs": 3600000,
        "cacheScope": "public",
        "_meta": {"io.modelcontextprotocol/serverInfo": SERVER_INFO},
    }


def initialize():
    """古い版のクライアントのためのあいさつ（2026-07-28 版では不要になった）"""
    return {
        "protocolVersion": LEGACY_VERSION,
        "capabilities": {"tools": {}},
        "serverInfo": SERVER_INFO,
        "instructions": INSTRUCTIONS,
    }


def check_headers(message, headers):
    """本文の _meta のバージョンと、ヘッダー MCP-Protocol-Version が一致することを確かめる（2026-07-28 版の決まり）"""
    meta = (message.get("params") or {}).get("_meta") or {}
    version = meta.get("io.modelcontextprotocol/protocolVersion")
    if version is not None and headers.get("mcp-protocol-version") != version:
        raise RpcError(HEADER_MISMATCH, "MCP-Protocol-Version ヘッダーと本文のバージョンが一致しない")


def handle(message, principal, repo, registry=None):
    """JSON-RPC のメッセージ1件を処理し、応答（辞書）を返す。通知（id がない）には None を返す"""
    registry = tools.TOOLS if registry is None else registry
    if "id" not in message:
        return None  # 通知（notifications/initialized など）。応答しない
    try:
        method = message.get("method")
        params = message.get("params") or {}
        if method == "tools/list":
            result = list_tools(registry)
        elif method == "tools/call":
            result = call_tool(params, principal, repo, registry)
        elif method == "server/discover":
            result = discover()
        elif method == "initialize":
            result = initialize()
        elif method == "ping":
            result = {}
        else:
            raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")
    except RpcError as e:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": e.code, "message": e.message}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}
