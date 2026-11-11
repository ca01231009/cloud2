"""api/doc_search.py を確かめるテスト（コマ14）

実行のしかた（Codespace のターミナルで。Azure にも OpenRouter にもつながない）
  pip install pytest azure-search-documents azure-identity
  python -m pytest lesson14/test_search.py -v
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "api"))
sys.path.insert(0, str(ROOT / "lesson14"))

import doc_search  # noqa: E402
import embedding  # noqa: E402
from common import load_info, load_records, local_search  # noqa: E402


def fields():
    return {f.name: f for f in doc_search.build_index("test", 256).fields}


# ---------------------------------------------------------------------
# 配布データ（最初から通る）
# ---------------------------------------------------------------------
def test_データ_埋め込みの次元数が情報と一致する():
    info = load_info()
    assert all(len(r["embedding"]) == info["dimensions"] for r in load_records())


def test_データ_ローカルの形になっている():
    assert set(load_records()[0]) == {"source", "text", "embedding"}


def test_データ_ローカル版は言い換えの質問で正しい文書を見つける():
    hits = local_search(load_records(), embedding.mock_embed("会社を休むときの手続き"))
    assert any("有給休暇" in h["content"] for h in hits)


def test_データ_モック埋め込みは同じ文から同じベクトルを作る():
    assert embedding.mock_embed("経費精算") == embedding.mock_embed("経費精算")


# ---------------------------------------------------------------------
# インデックスの定義（演習手順4）
# ---------------------------------------------------------------------
def test_定義_キーのフィールドがある():
    assert fields()["id"].key is True


def test_定義_本文に日本語のアナライザーを指定している():
    assert str(fields()["content"].analyzer_name) in ("ja.microsoft", "LexicalAnalyzerName.JA_MICROSOFT")


def test_定義_ベクトルのフィールドの次元数が埋め込みと同じ():
    field = fields()["contentVector"]
    assert field.vector_search_dimensions == 256
    assert field.vector_search_profile_name == doc_search.VECTOR_PROFILE


# ---------------------------------------------------------------------
# ローカルのデータの変換（演習手順5）
# ---------------------------------------------------------------------
RECORDS = [
    {"source": "docs/faq_it.txt", "text": "本文1", "embedding": [0.1]},
    {"source": "docs/faq_it.txt", "text": "本文2", "embedding": [0.2]},
]


def test_変換_IDにキーで使えない文字がない():
    for d in doc_search.to_search_documents(RECORDS):
        assert re.fullmatch(r"[A-Za-z0-9_\-=]+", d["id"])


def test_変換_同じ文書の別の部分はIDが違う():
    a, b = doc_search.to_search_documents(RECORDS)
    assert a["id"] != b["id"]


def test_変換_やり直しても同じIDになる():
    assert doc_search.to_search_documents(RECORDS) == doc_search.to_search_documents(RECORDS)


def test_変換_本文とベクトルが入っている():
    d = doc_search.to_search_documents(RECORDS)[0]
    assert d["source"] == "docs/faq_it.txt" and d["content"] == "本文1" and d["contentVector"] == [0.1]


# ---------------------------------------------------------------------
# 検索（演習手順6）
# ---------------------------------------------------------------------
def test_検索_全文検索はベクトルを送らない():
    args = doc_search.build_search_args("keyword", "VPN", None, 3)
    assert args["search_text"] == "VPN" and "vector_queries" not in args


def test_検索_ベクトル検索は言葉を送らない():
    args = doc_search.build_search_args("vector", "VPN", [0.1], 3)
    assert args["search_text"] is None and len(args["vector_queries"]) == 1


def test_検索_ハイブリッド検索は言葉とベクトルの両方を送る():
    args = doc_search.build_search_args("hybrid", "VPN", [0.1], 3)
    assert args["search_text"] == "VPN" and len(args["vector_queries"]) == 1


class FakeClient:
    def search(self, select, **args):
        return [{"source": "docs/a.txt", "content": "本文", "@search.score": 0.03279}]


def test_検索_結果を決まった形で返す():
    hits = doc_search.run_search(FakeClient(), "keyword", "VPN", None)
    assert hits == [{"source": "docs/a.txt", "content": "本文", "score": 0.0328}]
