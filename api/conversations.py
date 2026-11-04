"""会話の履歴を、利用者ごとに分ける（コマ11）

コマ7では、会話の履歴を Cosmos DB のコンテナー conversations に保存した（メッセージ1件＝1ドキュメント、
パーティションキーは会話の ID）。利用者が自分一人なら、それで困らなかった。
コマ11から、メッセージに所有者（userId）を記録し、読むとき・続きを書くときに所有者を確かめる。

ドキュメントの形
  {"id": ランダム, "conversationId": 会話の ID, "userId": 所有者の利用者 ID,
   "role": "user" または "assistant", "content": 本文, "createdAt": 時刻}
"""

import uuid

import authz


def list_conversations(store, principal, requested_user=None):
    """利用者の会話の一覧を返す（GET /api/conversations/list）

      requested_user : 画面が送ってきた「誰の一覧か」（クエリ文字列の user）
    """
    authz.require_user(principal)
    user_id = principal.user_id  # 画面が送ってきた requested_user は使わない
    return store.list_for_user(user_id)


def read_conversation(store, principal, conversation_id, limit):
    """会話の履歴を返す（GET /api/conversations?id=…）。所有者でなければ NotFound"""
    authz.check_owner(principal, store.owner_of(conversation_id))
    return store.load(conversation_id, limit)


def check_can_continue(store, principal, conversation_id):
    """既存の会話に続けて質問してよいかを確かめる（POST /api/chat）。所有者でなければ NotFound"""
    authz.check_owner(principal, store.owner_of(conversation_id))


# =====================================================================
# Cosmos DB を使った保存先（教員が用意したもの）
# =====================================================================
class CosmosConversationStore:
    def __init__(self, container):
        self.container = container

    def owner_of(self, conversation_id):
        """会話の所有者（最初のメッセージの userId）。会話がなければ None"""
        items = list(
            self.container.query_items(
                query="SELECT TOP 1 c.userId FROM c WHERE c.conversationId = @id ORDER BY c.createdAt",
                parameters=[{"name": "@id", "value": conversation_id}],
                partition_key=conversation_id,
            )
        )
        return items[0].get("userId") if items else None

    def list_for_user(self, user_id, limit=200):
        """利用者の会話を、新しい順に返す。見出しは、その会話の最初の質問"""
        items = self.container.query_items(
            query=(
                "SELECT TOP @limit c.conversationId, c.content, c.createdAt FROM c "
                "WHERE c.userId = @user AND c.role = 'user'"
            ),
            parameters=[{"name": "@limit", "value": limit}, {"name": "@user", "value": user_id}],
            enable_cross_partition_query=True,  # 利用者の会話は、いくつものパーティション（会話）にまたがる
        )
        return summarize(items)

    def load(self, conversation_id, limit):
        """この会話の履歴のうち、新しいほうから limit 件を、古い順に並べて返す"""
        items = list(
            self.container.query_items(
                query=(
                    "SELECT TOP @limit c.role, c.content, c.createdAt FROM c "
                    "WHERE c.conversationId = @id ORDER BY c.createdAt DESC"
                ),
                parameters=[{"name": "@limit", "value": limit}, {"name": "@id", "value": conversation_id}],
                partition_key=conversation_id,
            )
        )
        items.reverse()
        return [{"role": i["role"], "content": i["content"]} for i in items]

    def save_message(self, conversation_id, user_id, role, content, created_at):
        self.container.create_item(
            {
                "id": str(uuid.uuid4()),
                "conversationId": conversation_id,
                "userId": user_id,
                "role": role,
                "content": content,
                "createdAt": created_at,
            }
        )


def summarize(items):
    """利用者の質問のリストから、会話ごとの見出し（最初の質問）と最終更新の時刻を作り、新しい順に並べる"""
    conversations = {}
    for item in sorted(items, key=lambda i: i["createdAt"]):
        c = conversations.setdefault(
            item["conversationId"],
            {"conversationId": item["conversationId"], "title": item["content"][:30], "updatedAt": item["createdAt"]},
        )
        c["updatedAt"] = item["createdAt"]
    return sorted(conversations.values(), key=lambda c: c["updatedAt"], reverse=True)
