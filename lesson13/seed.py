"""架空の問い合わせを、テスト利用者として API に登録する（コマ11〜13）

使い方（azd up と enable-dev-login.sh の後に、Codespace のターミナルで）
  python lesson13/seed.py

sample_inquiries.json の各件を、"as" に書いたテスト利用者のトークンで POST /api/inquiries に送る。
登録した人（createdBy）は、API がトークンから決める。LLM は呼ばない。
"""

import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from token_tool import api_base_url, get_token  # noqa: E402

base = api_base_url()
if not base.startswith("https://"):
    sys.exit("API の URL が分からない。azd up が終わっているか、azd env list で環境を確かめる。")

items = json.loads(Path(__file__).with_name("sample_inquiries.json").read_text(encoding="utf-8"))
tokens = {}
for item in items:
    user_id = item["as"]
    if user_id not in tokens:
        tokens[user_id] = get_token(user_id)
    request = urllib.request.Request(
        f"{base}/api/inquiries",
        data=json.dumps({"title": item["title"], "body": item["body"]}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {tokens[user_id]}"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print(response.status, user_id, item["title"])
print(f"{len(items)} 件を登録した。")
