"""アナライザーが文を単語に分ける様子を見る（コマ14。教員が用意したもの）

使い方: python lesson14/analyze.py "在宅勤務の手続きを確認する"
インデックスが作ってあること（create_index.py の後）。standard.lucene と ja.microsoft の結果を並べる。
"""

import sys

from azure.search.documents.indexes.models import AnalyzeTextOptions
from common import search_clients

text = sys.argv[1] if len(sys.argv) > 1 else "在宅勤務の手続きを確認する"
index_client, _, index_name = search_clients()
for analyzer in ("standard.lucene", "ja.microsoft"):
    result = index_client.analyze_text(index_name, AnalyzeTextOptions(text=text, analyzer_name=analyzer))
    print(f"{analyzer}: " + " | ".join(t.token for t in result.tokens))
