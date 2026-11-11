"""MCP サーバーに JSON-RPC のメッセージを1件送り、応答をそのまま表示する（コマ13。教員が用意したもの）

使い方（azd up と enable-dev-login.sh の後に、Codespace のターミナルで）
  python lesson13/mcp_raw.py discover                      サーバーの対応バージョンと機能
  python lesson13/mcp_raw.py list                          ツールの一覧
  python lesson13/mcp_raw.py call <ツール名> '<引数のJSON>'    ツールを呼ぶ
  どれも、--user <利用者ID> でテスト利用者を選べる（既定は staff-sora）
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp_client import McpClient, McpError, http_post  # noqa: E402
from token_tool import api_base_url, get_token  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["discover", "list", "call"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("arguments", nargs="?", default="{}")
    parser.add_argument("--user", default="staff-sora")
    options = parser.parse_args()

    client = McpClient(http_post(f"{api_base_url()}/api/mcp", get_token(options.user)))
    try:
        if options.command == "discover":
            result = client.request("server/discover")
        elif options.command == "list":
            result = client.request("tools/list")
        else:
            result = client.request("tools/call", {"name": options.name, "arguments": json.loads(options.arguments)})
    except McpError as e:
        sys.exit(f"プロトコルのエラー: {e}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
