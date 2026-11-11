"""エージェントを動かす（コマ13。教員が用意したもの）

使い方（Codespace のターミナルで。azd up と enable-dev-login.sh の後に）
  python lesson13/agent_cli.py "依頼" [--user user-kai] [--allow-write]

  --user        : MCP サーバーに送るテスト利用者（既定は staff-sora）
  --allow-write : データを変えるツールも、このエージェントに許す（既定は読むだけ）

モデルはこのプログラムの中から呼び、ツールは Azure の MCP サーバー（/api/mcp）を通して使う。
既定はモックLLM。わざと失敗させるときは、環境変数 MOCK_FAULT を付ける。
  MOCK_FAULT=tool_loop python lesson13/agent_cli.py "「VPN」の問い合わせを探して"
本物のモデルは、教員の合図があったときだけ、LLM_PROVIDER=openrouter を付けて1回だけ呼ぶ。
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "lesson13"))

import agent  # noqa: E402
import llm  # noqa: E402
import resilience  # noqa: E402
from mcp_client import McpClient, McpError, http_post, to_llm_tools  # noqa: E402
from token_tool import api_base_url, get_token  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("message")
    parser.add_argument("--user", default="staff-sora")
    parser.add_argument("--allow-write", action="store_true")
    options = parser.parse_args()

    config = llm.load_config()
    models = llm.tool_model_candidates(config)
    if not models:
        sys.exit("ツール呼び出しに使うモデルが設定されていない（教員の指示を待つ）")

    client = McpClient(http_post(f"{api_base_url()}/api/mcp", get_token(options.user)))
    try:
        definitions = to_llm_tools(client.list_tools())
    except McpError as e:
        sys.exit(f"MCP サーバーからツールの一覧を受け取れなかった（{e}）")
    print("サーバーのツール:", ", ".join(d["function"]["name"] for d in definitions))

    limits = agent.limits_from_config(config, options.allow_write)
    provider = llm.get_provider()
    budget = resilience.CallBudget(config["max_agent_llm_calls"])  # 全体で LLM を呼ぶ回数の上限

    def call_model(messages, tools_for_model):
        print("モデルに見せたツール:", ", ".join(t["function"]["name"] for t in tools_for_model) or "（なし）")
        outcome = resilience.call_with_resilience(
            lambda model: provider.complete_tools(model, messages, tools_for_model, config["tool_max_output_tokens"]),
            models,
            budget,
            max_retries_per_model=config["max_retries_per_model"],
            base_delay=config["retry_base_delay_seconds"],
            max_delay=config["retry_max_delay_seconds"],
            max_wait=config["retry_max_wait_seconds"],
        )
        return outcome.text

    def execute(name, arguments):
        return client.call_tool(name, json.loads(arguments))

    messages = [
        {"role": "system", "content": config["agent_system_prompt"]},
        {"role": "user", "content": options.message},
    ]
    try:
        result = agent.run_agent(messages, definitions, call_model, execute, limits)
    except llm.LLMError as e:
        sys.exit(f"LLM を呼べなくなったので止めた（{e}）。LLM を呼んだ回数 {budget.used}")

    for i, step in enumerate(result.steps, 1):
        mark = "（エージェントが断った）" if step["refused"] else ""
        print(f"{i}. {step['tool']} {step['arguments']}{mark}")
        print(f"   → {json.dumps(step['result'], ensure_ascii=False)[:200]}")
    print("答え:", result.reply)
    print(f"止まった理由: {result.stop_reason} ／ LLM を呼んだ回数: {budget.used}")


if __name__ == "__main__":
    main()
