"""コマ14の道具で共通に使うもの（教員が用意したもの）"""

import json
import math
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "api"))


def azd_value(name):
    """環境変数 name があればそれを、なければ azd の環境から読む"""
    # 注意: eval "$(azd env get-values)" で作った変数は export されないので、Python からは見えない
    if os.environ.get(name):
        return os.environ[name]
    try:
        result = subprocess.run(["azd", "env", "get-value", name], capture_output=True, text=True)
    except FileNotFoundError:
        result = None
    if result is None or result.returncode != 0:
        sys.exit(f"{name} が分からない。azd up が終わっているか、azd env list で環境を確かめる。")
    return result.stdout.strip()


def load_records():
    return json.loads((HERE / "vector_store.json").read_text(encoding="utf-8"))


def load_info():
    return json.loads((HERE / "embedding_info.json").read_text(encoding="utf-8"))


def local_search(records, vector, top=3):
    """ローカルのベクトル検索（ローカルの RAG の search と同じ。全件とのコサイン類似度を計算して並べる）"""

    def cosine(a, b):
        dot = sum(x * y for x, y in zip(a, b))
        norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
        return dot / norm if norm else 0.0

    scored = sorted(((cosine(vector, r["embedding"]), r) for r in records), key=lambda x: x[0], reverse=True)
    return [{"source": r["source"], "content": r["text"], "score": round(s, 4)} for s, r in scored[:top]]


def search_clients():
    """自分のサインイン（az login）で AI Search に接続する。キーは使わない"""
    from azure.identity import AzureCliCredential
    from azure.search.documents import SearchClient
    from azure.search.documents.indexes import SearchIndexClient

    endpoint = azd_value("AZURE_SEARCH_ENDPOINT")
    index_name = azd_value("AZURE_SEARCH_INDEX")
    credential = AzureCliCredential()
    return SearchIndexClient(endpoint, credential), SearchClient(endpoint, index_name, credential), index_name
