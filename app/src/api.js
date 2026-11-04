// API を呼ぶための共通の関数（コマ11。教員が用意したもの）
//   - API の URL は、ビルドのときに azd が設定ファイル（.env.production.local）に書き込む
//   - テスト利用者のトークンを、要求のヘッダー Authorization: Bearer … に付けて送る
//   - トークンは sessionStorage（タブごと）に置く。タブを2つ開けば、別々のテスト利用者として試せる

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

const TOKEN_KEY = 'cloud2-token'
const USER_KEY = 'cloud2-user'

export function getSession() {
  const token = sessionStorage.getItem(TOKEN_KEY)
  const user = sessionStorage.getItem(USER_KEY)
  return token && user ? { token, user: JSON.parse(user) } : null
}

export function saveSession(token, user) {
  sessionStorage.setItem(TOKEN_KEY, token)
  sessionStorage.setItem(USER_KEY, JSON.stringify(user))
}

export function clearSession() {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(USER_KEY)
}

// fetch と同じ使い方で、トークンを付けて API を呼ぶ
export function apiFetch(path, options = {}) {
  const session = getSession()
  const headers = { ...(options.headers ?? {}) }
  if (session) headers.Authorization = `Bearer ${session.token}`
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers })
}
