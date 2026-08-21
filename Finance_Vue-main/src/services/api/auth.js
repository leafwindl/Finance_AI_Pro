const apiBase = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export async function login(name, password) {
  const res = await fetch(`${apiBase}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ name, password })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error?.message || err.detail?.message || err.detail || '登录失败')
  }
  return res.json()
}

export async function register(name, email, password) {
  const res = await fetch(`${apiBase}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ name, email, password })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.error?.message || err.detail?.message || err.detail || '注册失败')
  }
  return res.json()
}

export async function getMe() {
  const res = await fetch(`${apiBase}/auth/me`, {
    credentials: 'include'
  })
  if (!res.ok) throw new Error('未登录')
  return res.json()
}

export async function logout() {
  await fetch(`${apiBase}/auth/logout`, {
    method: 'POST',
    credentials: 'include'
  })
}
