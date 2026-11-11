"""MCP クライアント（コマ13。教員が用意したもの）

MCP サーバーの URL に JSON-RPC のメッセージを POST し、ツールの一覧を受け取り、ツールを呼ぶ。
学ぶために仕様の必要な部分だけを手で書いたものである（実務では公式の MCP SDK も検討する）。
"""

import json
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2026-07-28"
CLIENT_INFO = {"name": "lesson13-agent", "version": "1.0.0"}


class McpError(Exception):
    """プロトコルのエラー（ツールが見つからない・認証の失敗 など）"""


def http_post(url, token):
    """本物の HTTP でメッセージを送る関数を作る。テストでは、これをサーバーを直接呼ぶ関数に置き換える"""

    def post(message):
        params = message.get("params", {})
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {token}",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "Mcp-Method": message["method"],
        }
        if message["method"] == "tools/call":
            headers["Mcp-Name"] = params["name"]
        request = urllib.request.Request(
            url, data=json.dumps(message, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as e:
            raise McpError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')}") from e

    return post


class McpClient:
    def __init__(self, post):
        self.post = post
        self.next_id = 0

    def request(self, method, params=None):
        self.next_id += 1
        params = dict(params or {})
        # 2026-07-28 版では、接続のあいさつがない。要求ごとに、バージョンと機能を _meta で知らせる
        params["_meta"] = {
            "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
            "io.modelcontextprotocol/clientInfo": CLIENT_INFO,
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        response = self.post({"jsonrpc": "2.0", "id": self.next_id, "method": method, "params": params})
        if "error" in response:
            raise McpError(f"{response['error']['code']}: {response['error']['message']}")
        return response["result"]

    def list_tools(self):
        return self.request("tools/list")["tools"]

    def call_tool(self, name, arguments):
        """ツールを呼び、結果の辞書を返す。失敗は {"error": …} の形にする（モデルに読ませて、直させるため）"""
        try:
            result = self.request("tools/call", {"name": name, "arguments": arguments})
        except McpError as e:
            return {"error": str(e)}
        text = "".join(c.get("text", "") for c in result.get("content", []))
        if result.get("isError"):
            return {"error": text}
        return result.get("structuredContent") or {"text": text}


def to_llm_tools(mcp_tools):
    """MCP のツールの一覧を、モデルに渡す tools の形（OpenAI 互換）に変える"""
    return [
        {
            "type": "function",
            "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t["inputSchema"]},
        }
        for t in mcp_tools
    ]
