import { useEffect, useRef, useState } from 'react'
import { apiFetch } from './api.js'

// アシスタントの画面（コマ7。教員が用意したもの）
//   - 質問を API（/api/chat）に送り、応答を「少しずつ」受け取って表示する
//   - 会話の ID をブラウザに覚えておき、画面を開き直したら API から履歴を読み直す
//   - キーはここ（ブラウザ）には一切ない。ブラウザが知っているのは自分の API の URL だけ
// コマ11から
//   - 要求にテスト利用者のトークンを付ける（apiFetch）。覚えておく会話の ID も、利用者ごとに分ける
//   - 自分の会話の一覧（/api/conversations/list）を表示し、選んだ会話を開く

// SSE（text/event-stream）の本文を読み、イベント（JSON）を1つずつ onEvent に渡す
async function readEvents(response, onEvent) {
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // イベントとイベントの間は空行（\n\n）で区切られている
    let index
    while ((index = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, index)
      buffer = buffer.slice(index + 2)
      for (const line of block.split('\n')) {
        if (line.startsWith('data: ')) onEvent(JSON.parse(line.slice(6)))
      }
    }
  }
}

export default function Assistant({ user }) {
  const STORAGE_KEY = `cloud2-conversation-id-${user?.id ?? 'none'}`
  const [conversationId, setConversationId] = useState(() => localStorage.getItem(STORAGE_KEY))
  const [list, setList] = useState([]) // 自分の会話の一覧（コマ11）
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [info, setInfo] = useState('')
  const [error, setError] = useState('')
  const startedAt = useRef(0)

  // 会話の一覧を読む。画面は「自分の ID」を user として送っている（API がこれを信じてよいかは、コマ11の演習で考える）
  async function loadList() {
    if (!user) return
    const res = await apiFetch(`/api/conversations/list?user=${encodeURIComponent(user.id)}`)
    setList(res.ok ? await res.json() : [])
  }

  // 会話を開く: 履歴を API から読む
  async function openConversation(id) {
    setError('')
    setInfo('')
    const res = await apiFetch(`/api/conversations?id=${encodeURIComponent(id)}`)
    if (!res.ok) {
      setMessages([])
      setError(`会話の履歴を読めませんでした（HTTP ${res.status}）`)
      return
    }
    localStorage.setItem(STORAGE_KEY, id)
    setConversationId(id)
    setMessages(await res.json())
  }

  // 画面を開いたとき: 覚えている会話があれば、履歴を API から読み直す
  useEffect(() => {
    if (!user) return
    loadList()
    if (conversationId) openConversation(conversationId).catch(() => setError('会話の履歴を読めませんでした'))
  }, [])

  function newConversation() {
    localStorage.removeItem(STORAGE_KEY)
    setConversationId(null)
    setMessages([])
    setInfo('')
    setError('')
  }

  // 最後のメッセージ（応答中のアシスタントの吹き出し）に文字を足す
  function appendToLast(text) {
    setMessages((prev) => {
      const last = prev[prev.length - 1]
      return [...prev.slice(0, -1), { ...last, content: last.content + text }]
    })
  }

  async function send(e) {
    e.preventDefault()
    const question = input.trim()
    if (!question || busy) return
    setBusy(true)
    setError('')
    setInfo('')
    setInput('')
    setMessages((prev) => [
      ...prev,
      { role: 'user', content: question },
      { role: 'assistant', content: '' },
    ])
    startedAt.current = performance.now()
    let firstAt = 0

    try {
      const res = await apiFetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversationId, message: question }),
      })
      await readEvents(res, (event) => {
        if (event.type === 'start') {
          localStorage.setItem(STORAGE_KEY, event.conversationId)
          setConversationId(event.conversationId)
          setInfo(`モデルに送ったメッセージ: ${event.sentMessages} 件`)
        } else if (event.type === 'delta') {
          if (!firstAt) firstAt = performance.now()
          appendToLast(event.text)
        } else if (event.type === 'error') {
          setError(event.message)
        } else if (event.type === 'end') {
          const first = ((firstAt - startedAt.current) / 1000).toFixed(1)
          const total = ((performance.now() - startedAt.current) / 1000).toFixed(1)
          setInfo((prev) => `${prev} ／ 最初の文字まで ${first} 秒・全体 ${total} 秒`)
        }
      })
      await loadList()
    } catch (err) {
      setError(`応答を受け取れませんでした（${err.message}）`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="assistant">
      <div className="assistant-head">
        <h2>アシスタント</h2>
        <button type="button" className="secondary" onClick={newConversation} disabled={busy}>
          新しい会話
        </button>
      </div>

      {!user && <p className="hint">上の「API に送る利用者」で、テスト利用者を選ぶと使えます。</p>}

      {list.length > 0 && (
        <div className="conversation-list">
          自分の会話:
          {list.map((c) => (
            <button
              key={c.conversationId}
              type="button"
              className={`secondary small ${c.conversationId === conversationId ? 'current' : ''}`}
              onClick={() => openConversation(c.conversationId)}
              disabled={busy}
              title={c.conversationId}
            >
              {c.title}
            </button>
          ))}
        </div>
      )}

      <div className="chat-log">
        {messages.length === 0 && <p className="hint">社内の手続きなどについて質問できます（架空の会社の設定です）。</p>}
        {messages.map((m, i) => (
          // React は文字列を自動でエスケープして表示する。LLM の出力も「信頼できない入力」として扱う
          <div key={i} className={`bubble ${m.role}`}>
            {m.content || (busy && i === messages.length - 1 ? '…' : '')}
          </div>
        ))}
      </div>

      {info && <p className="info">{info}</p>}
      {error && <p className="message">{error}</p>}

      <form className="chat-form" onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={1000}
          placeholder="質問を入力（架空の内容だけ）"
          disabled={busy || !user}
        />
        <button type="submit" disabled={busy || !user}>
          {busy ? '応答中…' : '送信'}
        </button>
      </form>
    </section>
  )
}
