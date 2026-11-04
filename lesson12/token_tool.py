"""テスト利用者のトークンを扱う道具（コマ11・12）

使い方（azd up と enable-dev-login.sh の後に、Codespace のターミナルで）
  python lesson12/token_tool.py get <利用者ID>              テスト利用者としてトークンを受け取り、表示する
  python lesson12/token_tool.py show <トークン>             トークンの中身（署名の前の部分）を読んで表示する
  python lesson12/token_tool.py tamper <トークン> <利用者ID>  中身の利用者 ID だけを書き換えたトークンを作る（署名はそのまま）

例
  TOKEN_KAI=$(python lesson12/token_tool.py get user-kai)
  curl -s -H "Authorization: Bearer $TOKEN_KAI" "$API_BASE_URL/api/me"; echo

トークンは演習用（テスト利用者・1時間で期限切れ）である。それでも、ファイルやリポジトリには書かない。
"""

import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def api_base_url():
    """環境変数 API_BASE_URL があればそれを、なければ azd の環境から読む"""
    # 注意: eval "$(azd env get-values)" で作った変数は export されないので、Python からは見えない
    if os.environ.get("API_BASE_URL"):
        return os.environ["API_BASE_URL"]
    try:
        result = subprocess.run(["azd", "env", "get-value", "API_BASE_URL"], capture_output=True, text=True)
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def get_token(user_id):
    base = api_base_url()
    if not base.startswith("https://"):
        sys.exit("API の URL が分からない。azd up が終わっているか、azd env list で環境を確かめる。")
    request = urllib.request.Request(
        f"{base}/api/dev/login",
        data=json.dumps({"userId": user_id}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())["token"]
    except urllib.error.HTTPError as e:
        sys.exit(f"トークンを受け取れなかった（HTTP {e.code}: {e.read().decode('utf-8', 'replace')}）")


def decode_part(text):
    return json.loads(base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)))


def encode_part(payload):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main(args):
    if len(args) == 2 and args[0] == "get":
        print(get_token(args[1]))
    elif len(args) == 2 and args[0] == "show":
        payload_part = args[1].split(".")[0]
        print(json.dumps(decode_part(payload_part), ensure_ascii=False, indent=2))
    elif len(args) == 3 and args[0] == "tamper":
        payload_part, signature_part = args[1].split(".")
        payload = decode_part(payload_part)
        payload["sub"] = args[2]  # 中身だけを書き換える。鍵を知らないので、署名は作り直せない
        print(f"{encode_part(payload)}.{signature_part}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
