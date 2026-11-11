"""AI エージェントのループ（コマ13）

エージェントは、目的を与えられると、モデルが「次に何をするか」を決め（計画）、ツールを使い（実行）、
結果を見て（観察）、また次を決める、を目的が達成されるまで繰り返す。
コマ12の実行ループとの違いは、どのツールをどの順で何回使うかをモデルに任せる範囲が広いことである。
だから、アプリの側で「いつ止めるか」（停止条件）と「何を許すか」（権限の範囲）を決めておく。

このファイルの関数は、Azure にも OpenRouter にもつながずにテストできる
（モデルを呼ぶ関数 call_model と、ツールを実行する関数 execute を、引数で受け取るようにしてある）。
"""

import json
from dataclasses import dataclass, field

from tools import assistant_message

# 止まった理由
ANSWERED = "answered"  # モデルが答えを出した（正常な終わり）
MAX_STEPS = "max_steps"  # モデルを呼ぶ回数の上限に達した
REPEATED = "repeated"  # 同じ呼び出しを繰り返した
ERRORS = "errors"  # 失敗が続いた


@dataclass
class Limits:
    """エージェントに与える上限と権限の範囲"""

    max_steps: int  # モデルを呼ぶ回数の上限
    max_repeats: int  # 同じツールを同じ引数で呼んでよい回数
    max_errors: int  # ツールの失敗が、続けて何回まで許されるか
    max_writes: int  # データを変えるツールを呼んでよい回数
    allowed: set = field(default_factory=set)  # このエージェントが使ってよいツールの名前
    write_tools: set = field(default_factory=set)  # データを変えるツールの名前


@dataclass
class AgentResult:
    reply: str
    steps: list
    stop_reason: str


def limits_from_config(config, allow_write=False):
    """設定ファイルから上限を作る。既定では読むだけのツールしか許さない（更新は --allow-write のときだけ）"""
    write_tools = set(config["agent_write_tools"])
    allowed = set(config["agent_read_tools"]) | (write_tools if allow_write else set())
    return Limits(
        max_steps=config["max_agent_steps"],
        max_repeats=config["max_agent_repeats"],
        max_errors=config["max_agent_errors"],
        max_writes=config["max_agent_writes"],
        allowed=allowed,
        write_tools=write_tools,
    )


# =====================================================================
# 権限の範囲
# =====================================================================
def visible_tools(definitions, limits):
    """モデルに見せるツールの定義を選ぶ（definitions は OpenAI 互換の tools の形のリスト）"""
    # TODO(コマ13 演習手順6-1): limits.allowed に名前があるツールだけを返す（名前は d["function"]["name"]）。
    #   いまは、サーバーのツールをすべてモデルに見せている。
    return definitions


def refusal(name, steps, limits):
    """このツールの呼び出しを、エージェントの側で断る理由を返す（断らないなら None）

    モデルに見せなかったツールでも、モデルが要求してくることはある。だから、実行の前にも確かめる。
    """
    # TODO(コマ13 演習手順6-2): 次の2つを確かめる。
    #   1. name が limits.allowed になければ、"このエージェントには許されていないツールである" を返す
    #   2. name が limits.write_tools にあり、steps の中で実際に実行した同じ種類のツールの数が limits.max_writes 以上なら、
    #      "データを変える回数の上限に達した" を返す（断った呼び出しは、step["refused"] が True になっている。数えない）
    #   いまは、何も断っていない。
    return None


# =====================================================================
# 停止条件
# =====================================================================
def stop_reason(steps, limits):
    """これまでの記録 steps を見て、止めるべきなら理由（REPEATED か ERRORS）を、続けてよいなら None を返す

      steps の各要素: {"tool": 名前, "arguments": 引数の JSON の文字列, "result": 結果の辞書}
      失敗した呼び出しは、result に "error" がある
    """
    # TODO(コマ13 演習手順5): 2つの停止条件を書く。
    #   1. 同じツールを同じ引数で呼んだ回数が limits.max_repeats を超えたら、REPEATED を返す
    #      （同じことを繰り返しても、結果は変わらない。LLM を呼ぶ回数を無駄にするだけである）
    #   2. 最後から数えて、続けて limits.max_errors 回失敗していたら、ERRORS を返す
    #   いまは、回数の上限（max_steps）に達するまで止まらない。
    return None


# =====================================================================
# エージェントのループ
# =====================================================================
def run_agent(messages, definitions, call_model, execute, limits):
    """目的が達成されるか、停止条件に当たるまで、モデルとツールの呼び出しを繰り返す

      messages               : system と user のメッセージ（モデルの要求と結果が書き足されていく）
      definitions            : サーバーから受け取ったツールの定義
      call_model(messages, tools) : モデルを1回呼び、{"content", "tool_calls"} を返す
      execute(name, arguments)    : ツールを実行し、結果の辞書を返す
    """
    tools_for_model = visible_tools(definitions, limits)
    steps = []
    for _ in range(limits.max_steps):
        # 計画: モデルが、これまでの結果を見て、次に何をするかを決める
        response = call_model(messages, tools_for_model)
        calls = response.get("tool_calls") or []
        if not calls:
            return AgentResult(response.get("content") or "", steps, ANSWERED)

        messages.append(assistant_message(response))
        for call in calls:
            # 実行: 許される呼び出しだけを実行する
            reason = refusal(call["name"], steps, limits)
            result = {"error": reason} if reason else execute(call["name"], call["arguments"])
            steps.append(
                {"tool": call["name"], "arguments": call["arguments"], "result": result, "refused": bool(reason)}
            )
            # 観察: 結果をモデルに返す
            messages.append(
                {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}
            )

        reason = stop_reason(steps, limits)
        if reason:
            return AgentResult(f"停止条件（{reason}）に当たったので、ここで止めた", steps, reason)

    return AgentResult(f"モデルを呼ぶ回数の上限（{limits.max_steps}回）に達したので、ここで止めた", steps, MAX_STEPS)
