"""同じ質問で、ローカル版と AI Search の各検索の結果を比べる（コマ14。教員が用意したもの）

使い方
  python lesson14/compare.py              questions.json の質問をすべて比べる
  python lesson14/compare.py "質問の文"    1つの質問だけを比べる

検索の結果の1位〜3位の先頭を表示する。questions.json の expect を含む文書には ★ を付ける。
質問の埋め込みは、環境変数 EMBEDDING_PROVIDER で決める（既定はモック埋め込み）。
"""

import json
import sys

from common import HERE, load_info, load_records, local_search, search_clients

import doc_search
import embedding


def show(label, hits, expect):
    print(f"  [{label}]")
    if not hits:
        print("     （結果なし）")
    for i, h in enumerate(hits, 1):
        mark = "★" if expect and expect in h["content"] else "  "
        print(f"     {i}. {mark} {h['content'][:32].replace(chr(10), ' ')}…（{h['score']}）")


def main():
    if len(sys.argv) > 1:
        questions = [{"question": sys.argv[1], "kind": "自分の質問", "expect": ""}]
    else:
        questions = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))

    records = load_records()
    info = load_info()
    _, client, _ = search_clients()
    for q in questions:
        print(f"\n■ {q['question']}（{q['kind']}）")
        try:
            vector = embedding.embed_query(q["question"], info)
        except embedding.EmbeddingError as e:
            sys.exit(str(e))
        show("ローカル版（ベクトルのみ）", local_search(records, vector), q["expect"])
        for mode, label in (("keyword", "全文検索"), ("vector", "ベクトル検索"), ("hybrid", "ハイブリッド検索")):
            show(label, doc_search.run_search(client, mode, q["question"], vector), q["expect"])


if __name__ == "__main__":
    main()
