"""ローカルのデータ（vector_store.json）をインデックスに投入する（コマ14。教員が用意したもの）

使い方: python lesson14/upload_docs.py
配布データの埋め込みをそのまま使う。OpenRouter は呼ばない（埋め込みを作り直さない）。
"""

import sys

from common import load_records, search_clients

import doc_search

_, client, index_name = search_clients()
documents = doc_search.to_search_documents(load_records())
results = client.merge_or_upload_documents(documents)  # 同じ id があれば置き換える。やり直しても増えない
failed = [r for r in results if not r.succeeded]
print(f"{len(results) - len(failed)} 件を {index_name} に投入した。失敗 {len(failed)} 件")
if failed:
    sys.exit(f"失敗の例: {failed[0].error_message}")
