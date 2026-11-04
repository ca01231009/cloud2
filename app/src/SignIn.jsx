import { useEffect, useState } from 'react'
import { apiFetch, clearSession, getSession, saveSession } from './api.js'

// サインインの表示（コマ11。教員が用意したもの）
//   上段: Static Web Apps の組み込み認証（GitHub）で、画面にサインインしている人（/.auth/me で取得）
//   下段: API に対して「誰として」要求を送るか（テスト利用者。擬似認証のトークン）
//
// 演習の構成では、上段のサインインの情報は API に届かない（画面と API が別のサイトにあるため）。
// そこで、API には下段のトークンを送る。下段は誰にでもなれる演習用の仕組みであり、本番では使わない。

export default function SignIn({ onChange }) {
  const [swaUser, setSwaUser] = useState(null)
  const [testUsers, setTestUsers] = useState([])
  const [session, setSession] = useState(getSession)
  const [error, setError] = useState('')

  useEffect(() => {
    // Static Web Apps の組み込み認証: 画面と同じサイトの /.auth/me が、サインインしている人を返す
    fetch('/.auth/me')
      .then((res) => (res.ok ? res.json() : { clientPrincipal: null }))
      .then((data) => setSwaUser(data.clientPrincipal))
      .catch(() => setSwaUser(null))
    apiFetch('/api/dev/users')
      .then((res) => (res.ok ? res.json() : []))
      .then(setTestUsers)
      .catch(() => setTestUsers([]))
  }, [])

  async function signInAs(userId) {
    setError('')
    if (!userId) {
      clearSession()
      setSession(null)
      onChange(null)
      return
    }
    const res = await apiFetch('/api/dev/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId }),
    })
    const data = await res.json()
    if (!res.ok) {
      setError(data.error ?? `サインインできませんでした（HTTP ${res.status}）`)
      return
    }
    const user = { id: data.userId, name: data.name, roles: data.roles }
    saveSession(data.token, user)
    setSession({ token: data.token, user })
    onChange(user)
  }

  return (
    <section className="signin">
      <div>
        画面のサインイン（GitHub）:{' '}
        {swaUser ? (
          <>
            <strong>{swaUser.userDetails}</strong>（{swaUser.identityProvider}）{' '}
            <a href="/.auth/logout">サインアウト</a>
          </>
        ) : (
          <span>
            なし（<a href="/.auth/login/github">GitHub でサインイン</a>）
          </span>
        )}
      </div>
      <label className="test-user">
        API に送る利用者（テスト利用者・擬似認証）:
        <select value={session?.user.id ?? ''} onChange={(e) => signInAs(e.target.value)}>
          <option value="">選ばない（トークンなし）</option>
          {testUsers.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name}
            </option>
          ))}
        </select>
      </label>
      {testUsers.length === 0 && (
        <p className="hint">テスト利用者を読み込めません（lesson11/enable-dev-login.sh を実行したか確かめる）</p>
      )}
      {error && <p className="message">{error}</p>}
    </section>
  )
}
