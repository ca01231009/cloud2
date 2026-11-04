import { useState } from 'react'
import { apiFetch } from './api.js'

// ツールを使うアシスタント（コマ12。教員が用意したもの）
//   - 依頼を API（/api/assist）に送る。モデルがツールを要求し、API がツールを実行する
//   - どのツールを、どの引数で呼び、何が返ったか（steps）を表示する
//   - 会話の履歴は持たない（1回の依頼ごとに完結する）

export default function ToolAssistant({ user, onChanged }) {
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  async function send(e) {
    e.preventDefault()
    const message = input.trim()
    if (!message || busy) return
    setBusy(true)
    setError('')
    setResult(null)
    try {
      const res = await apiFetch('/api/assist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? `依頼できませんでした（HTTP ${res.status}）`)
        // 途中で失敗しても、それまでに実行したツール（steps）は取り消されない。記録を表示する
        setResult(data.callLog ? { steps: data.steps ?? [], callLog: data.callLog } : null)
      } else {
        setResult(data)
      }
      if ((data.steps ?? []).some((s) => s.tool === 'update_inquiry_status')) await onChanged()
    } catch (err) {
      setError(`依頼できませんでした（${err.message}）`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="assistant">
      <div className="assistant-head">
        <h2>ツールを使うアシスタント</h2>
      </div>
      <p className="hint">
        例: 「VPN」の問い合わせを探して ／ 問い合わせ（ID）のステータスを「対応中」にして（架空の内容だけ）
      </p>

      <form className="chat-form" onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          maxLength={1000}
          placeholder="依頼を入力"
          disabled={busy || !user}
        />
        <button type="submit" disabled={busy || !user}>
          {busy ? '実行中…' : '依頼する'}
        </button>
      </form>

      {error && <p className="message">{error}</p>}

      {result && (
        <>
          {/* モデルが要求し、アプリが実行したツールの記録 */}
          <div className="tool-steps">
            {result.steps.map((s, i) => (
              <div key={i} className={`tool-step ${s.result.error ? 'error' : ''}`}>
                <div>
                  {i + 1}. ツール <strong>{s.tool}</strong> 引数 <code>{s.arguments}</code>
                </div>
                <div>
                  結果 <code>{JSON.stringify(s.result)}</code>
                </div>
              </div>
            ))}
          </div>
          {result.reply !== undefined && <div className="bubble assistant">{result.reply}</div>}
          <p className="info">
            LLM を呼んだ回数: {result.llmCalls ?? '-'}
          </p>
          {result.callLog?.length > 0 && (
            <ol className="call-log">
              {result.callLog.map((line, i) => (
                <li key={i}>{line}</li>
              ))}
            </ol>
          )}
        </>
      )}
    </section>
  )
}
