"""認可: 「この利用者に、この操作を許してよいか」を決める（コマ11）

認証（auth.py）は「誰か」を確かめる。認可は、その人に「何を許すか」を決める。
どちらも、画面ではなく API の側で、要求のたびに行う（画面は利用者の手元にあり、書き換えられる）。

失敗したときは、HTTP の状態コードを持った例外を出す。function_app.py が、それを応答に変える。
  401 Unauthorized : 誰か分からない（トークンがない・署名が合わない・期限切れ）
  403 Forbidden    : 誰かは分かったが、その操作は許されていない（ロールが足りない）
  404 Not Found    : 見つからない。他人のデータも「ない」として扱い、あるかどうかを教えない
"""

STAFF = "staff"  # 担当者のロール。問い合わせの分類・一括分類のジョブを実行できる


class AuthError(Exception):
    status = 500

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class Unauthorized(AuthError):
    status = 401


class Forbidden(AuthError):
    status = 403


class NotFound(AuthError):
    status = 404


class NotReady(AuthError):
    status = 503


def require_user(principal):
    """サインインしていること（トークンが正しいこと）を求める"""
    if principal is None:
        raise Unauthorized("サインインしていない（トークンがない・正しくない・期限切れ）")
    return principal


def require_role(principal, role):
    """サインインしていて、さらに role のロールを持つことを求める（ロールが足りなければ Forbidden）"""
    require_user(principal)
    if role not in principal.roles:
        raise Forbidden("この操作は担当者だけができる")


def check_owner(principal, owner_id):
    """データの所有者が、要求した本人であることを求める（違えば NotFound）

      owner_id : データの所有者の利用者 ID（データが存在しなければ None）
    """
    require_user(principal)
    if owner_id != principal.user_id:
        raise NotFound("会話が見つからない")
