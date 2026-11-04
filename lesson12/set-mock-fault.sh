#!/bin/sh
# モックLLM に、わざと失敗させる（コマ8〜10・12）
#   使い方: sh lesson12/set-mock-fault.sh <値>
#     none             : 失敗させない（既定）
#     rate_limit_once  : 同じ要求の1回目だけ、429（Retry-After: 2秒）で失敗する（通信の失敗。コマ9）
#     all_rate_limited : どのモデルも、毎回 429 で失敗する（通信の失敗。コマ9）
#     bad_tool_args    : ステータスの変更で、決まりにない値（「解決済み」）を引数に入れる（コマ12）
#     unknown_tool     : 定義にないツール（delete_inquiry）を要求する（コマ12）
#     tool_loop        : ツールの結果を受け取っても、同じ検索を要求し続ける（コマ12）
#   アプリ設定を変えるとアプリが再起動する。1分ほど待ってから確かめる。
set -e
case "$1" in
  none|invalid_once|always_invalid|rate_limit_once|primary_down|all_rate_limited|bad_tool_args|unknown_tool|tool_loop) ;;
  *) echo "使い方: sh lesson12/set-mock-fault.sh none|rate_limit_once|all_rate_limited|bad_tool_args|unknown_tool|tool_loop" >&2; exit 1 ;;
esac
eval "$(azd env get-values)"
az functionapp config appsettings set \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --name "$AZURE_FUNCTION_NAME" \
  --settings "MOCK_FAULT=$1" \
  --output none
echo "MOCK_FAULT を $1 にした。1分ほど待ってから確かめる。"
