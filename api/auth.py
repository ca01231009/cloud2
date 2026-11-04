"""認証: 「この要求は誰からか」を API 自身が確かめる（コマ11。教員が用意したもの）

演習の構成では、画面（Static Web Apps）と API（Functions）が別のサイトにある。
Static Web Apps の組み込み認証で画面にサインインしても、その情報は API には届かない（Free プランの制約）。
そこで、API は「署名付きの利用者トークン」を受け取り、その署名を確かめて、利用者を決める。

トークンの形（JWT の考え方を、最小限に真似たもの）
  <中身を Base64URL にしたもの>.<署名を Base64URL にしたもの>
  中身: {"sub": 利用者の ID, "name": 表示名, "roles": [ロール], "exp": 有効期限（UNIX 時刻）}
  署名: 中身を、サーバーだけが知る鍵（AUTH_SIGNING_KEY。Key Vault に置く）で HMAC-SHA256 したもの

鍵を知らない人は、中身を書き換えると署名を作り直せない。だから、署名が合えば「サーバーが発行した
トークンで、中身は書き換えられていない」と分かる。

注意（演習のための擬似認証）
  - トークンを発行する POST /api/dev/login は、パスワードなしで、テスト利用者の誰にでもなれる。
    本番では、ここを本物の ID プロバイダー（GitHub・Microsoft Entra ID など）でのサインインに置き換える。
  - トークンの形式・署名の確かめ方を自作しているのは、仕組みを見るためである。
    本番では自作せず、実績のあるライブラリ（JWT のライブラリなど）と ID プロバイダーを使う。
"""

import base64
import hashlib
import hmac
import json
import os
from dataclasses import dataclass, field

TOKEN_TTL_SECONDS = 3600  # トークンの有効期間（1時間）


@dataclass(frozen=True)
class Principal:
    """認証された利用者（「誰か」と「何の役割か」）"""

    user_id: str
    name: str
    roles: tuple = field(default_factory=tuple)


def _b64encode(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(payload_part, secret):
    return hmac.new(secret.encode("utf-8"), payload_part.encode("ascii"), hashlib.sha256).digest()


def issue_token(user_id, name, roles, secret, now, ttl=TOKEN_TTL_SECONDS):
    """利用者トークンを発行する（now は UNIX 時刻の秒）"""
    payload = {"sub": user_id, "name": name, "roles": list(roles), "exp": int(now) + ttl}
    payload_part = _b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    return f"{payload_part}.{_b64encode(_sign(payload_part, secret))}"


def verify_token(token, secret, now):
    """トークンを確かめ、正しければ Principal を、正しくなければ None を返す

    確かめること
      1. 形が「中身.署名」になっている
      2. 署名が、サーバーの鍵で計算し直した署名と一致する（書き換えられていない）
      3. 有効期限が切れていない
    """
    try:
        payload_part, signature_part = token.split(".")
        signature = _b64decode(signature_part)
    except (ValueError, AttributeError):
        return None
    # 署名の比較は compare_digest で行う（== で比べると、一致した文字数で時間が変わり、手がかりを与える）
    if not hmac.compare_digest(signature, _sign(payload_part, secret)):
        return None
    try:
        payload = json.loads(_b64decode(payload_part))
    except ValueError:
        return None
    if int(payload.get("exp", 0)) <= now:
        return None
    return Principal(user_id=str(payload["sub"]), name=str(payload.get("name", "")), roles=tuple(payload.get("roles", [])))


def principal_from_headers(headers, secret, now):
    """要求のヘッダー Authorization: Bearer <トークン> から、利用者を決める（なければ None）"""
    value = headers.get("authorization", "")
    if not value.startswith("Bearer "):
        return None
    return verify_token(value[len("Bearer "):].strip(), secret, now)


def signing_key():
    """トークンの署名に使う鍵（アプリ設定 AUTH_SIGNING_KEY。Key Vault 参照）。使えなければ None

    Key Vault にシークレットがまだないと、Key Vault 参照が解決されず、
    「@Microsoft.KeyVault(...)」という文字列のまま届く（コマ6）。それは鍵として使わない。
    """
    value = os.environ.get("AUTH_SIGNING_KEY", "")
    if len(value) < 32 or value.startswith("@Microsoft.KeyVault("):
        return None
    return value
