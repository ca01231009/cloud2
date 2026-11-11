import { useState } from 'react'
import { apiFetch } from './api.js'

// 社内文書の検索（コマ14。教員が用意したもの）
//   検索の種類（全文検索・ベクトル検索・ハイブリッド検索）を選んで、API（/api/search）に送る

const MODES = [
  ['hybrid', 'ハイブリッド検索'],
  ['keyword', '全文検索'],
  ['vector', 'ベクトル検索'],
]

export default function DocSearch({ user }) {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState('hybrid')
  const [hits, setHits] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function search(e) {
    e.preventDefault()
    if (!query.trim() || busy) return
    setBusy(true)
    setError('')
    setHits(null)
    try {
      const res = await apiFetch('/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, mode }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? `検索できませんでした（HTTP ${res.status}）`)
        return
      }
      setHits(data.hits)
    } catch (err) {
      setError(`検索できませんでした（${err.message}）`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="assistant">
      <div className="assistant-head">
        <h2>社内文書の検索</h2>
      </div>
      <form className="chat-form" onSubmit={search}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          maxLength={1000}
          placeholder="検索の言葉（架空の内容だけ）"
          disabled={busy || !user}
        />
        <select value={mode} onChange={(e) => setMode(e.target.value)}>
          {MODES.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <button type="submit" disabled={busy || !user}>
          {busy ? '検索中…' : '検索'}
        </button>
      </form>
      {error && <p className="message">{error}</p>}
      {hits && hits.length === 0 && <p className="hint">見つかりませんでした。</p>}
      {hits?.map((h, i) => (
        <div key={i} className="tool-step">
          <div className="item-id">
            {i + 1}. {h.source}（スコア {h.score}）
          </div>
          <div>{h.content}</div>
        </div>
      ))}
    </section>
  )
}
