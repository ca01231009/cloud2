"""api/auth.py・api/authz.py・api/conversations.py を確かめるテスト（コマ11）

実行のしかた（Codespace のターミナルで。Azure にも OpenRouter にもつながない）
  pip install pytest
  python -m pytest lesson11/test_auth.py -v

Cosmos DB の代わりに、メモリに置いた「偽物の保存先」（FakeStore）を使う。
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))

import auth  # noqa: E402
import authz  # noqa: E402
import conversations  # noqa: E402

SECRET = "test-secret-" + "x" * 40  # テスト用の鍵（本物の鍵ではない）
NOW = 1_800_000_000

AOI = auth.Principal("user-aoi", "青井", ())
KAI = auth.Principal("user-kai", "海野", ())
SORA = auth.Principal("staff-sora", "空木", ("staff",))

CONV_AOI = "aaaaaaaa-0000-0000-0000-000000000001"
CONV_KAI = "bbbbbbbb-0000-0000-0000-000000000002"


class FakeStore:
    """会話の保存先の偽物。青井の会話と海野の会話が1つずつある"""

    def __init__(self):
        self.messages = [
            {"conversationId": CONV_AOI, "userId": "user-aoi", "role": "user", "content": "青井の質問", "createdAt": "1"},
            {"conversationId": CONV_AOI, "userId": "user-aoi", "role": "assistant", "content": "回答", "createdAt": "2"},
            {"conversationId": CONV_KAI, "userId": "user-kai", "role": "user", "content": "海野の質問", "createdAt": "3"},
        ]

    def owner_of(self, conversation_id):
        for m in self.messages:
            if m["conversationId"] == conversation_id:
                return m["userId"]
        return None

    def list_for_user(self, user_id):
        return conversations.summarize(
            [m for m in self.messages if m["userId"] == user_id and m["role"] == "user"]
        )

    def load(self, conversation_id, limit):
        return [{"role": m["role"], "content": m["content"]} for m in self.messages if m["conversationId"] == conversation_id]


# ---------------------------------------------------------------------
# 認証（auth.py。教員が用意したもの。最初から通る）
# ---------------------------------------------------------------------
def test_発行したトークンを確かめると本人になる():
    token = auth.issue_token("user-aoi", "青井", [], SECRET, NOW)
    assert auth.verify_token(token, SECRET, NOW + 10) == auth.Principal("user-aoi", "青井", ())


def test_中身を書き換えたトークンは通らない():
    token = auth.issue_token("user-kai", "海野", [], SECRET, NOW)
    payload_part, signature_part = token.split(".")
    other = auth.issue_token("user-aoi", "青井", [], SECRET, NOW).split(".")[0]
    assert auth.verify_token(f"{other}.{signature_part}", SECRET, NOW) is None


def test_別の鍵で署名したトークンは通らない():
    token = auth.issue_token("staff-sora", "空木", ["staff"], "another-key-" + "y" * 40, NOW)
    assert auth.verify_token(token, SECRET, NOW) is None


def test_期限切れのトークンは通らない():
    token = auth.issue_token("user-aoi", "青井", [], SECRET, NOW, ttl=60)
    assert auth.verify_token(token, SECRET, NOW + 61) is None


def test_ヘッダーがなければ利用者は決まらない():
    assert auth.principal_from_headers({}, SECRET, NOW) is None
    assert auth.principal_from_headers({"authorization": "Basic abc"}, SECRET, NOW) is None


# ---------------------------------------------------------------------
# ロール（authz.require_role。演習手順6）
# ---------------------------------------------------------------------
def test_ロール_担当者は担当者の操作ができる():
    authz.require_role(SORA, authz.STAFF)  # 例外が出なければよい


def test_ロール_一般の利用者は担当者の操作ができない():
    with pytest.raises(authz.Forbidden):
        authz.require_role(AOI, authz.STAFF)


def test_ロール_サインインしていなければ401():
    with pytest.raises(authz.Unauthorized):
        authz.require_role(None, authz.STAFF)


# ---------------------------------------------------------------------
# 会話の所有者（authz.check_owner と conversations.py。演習手順5）
# ---------------------------------------------------------------------
def test_所有者_自分の会話は読める():
    assert conversations.read_conversation(FakeStore(), AOI, CONV_AOI, 100)[0]["content"] == "青井の質問"


def test_所有者_他人の会話は見つからないことにする():
    with pytest.raises(authz.NotFound):
        conversations.read_conversation(FakeStore(), KAI, CONV_AOI, 100)


def test_所有者_担当者でも他人の会話は読めない():
    with pytest.raises(authz.NotFound):
        conversations.read_conversation(FakeStore(), SORA, CONV_AOI, 100)


def test_所有者_存在しない会話も見つからない():
    with pytest.raises(authz.NotFound):
        conversations.read_conversation(FakeStore(), AOI, "cccccccc-0000-0000-0000-000000000003", 100)


def test_所有者_他人の会話に続きを書けない():
    with pytest.raises(authz.NotFound):
        conversations.check_can_continue(FakeStore(), KAI, CONV_AOI)
    conversations.check_can_continue(FakeStore(), AOI, CONV_AOI)  # 自分の会話なら例外が出ない


def test_一覧_自分の会話だけが返る():
    result = conversations.list_conversations(FakeStore(), KAI, None)
    assert [c["conversationId"] for c in result] == [CONV_KAI]


def test_一覧_画面が他人のIDを送ってきても自分の会話だけが返る():
    result = conversations.list_conversations(FakeStore(), KAI, "user-aoi")
    assert [c["conversationId"] for c in result] == [CONV_KAI]


def test_一覧_サインインしていなければ401():
    with pytest.raises(authz.Unauthorized):
        conversations.list_conversations(FakeStore(), None, "user-aoi")
