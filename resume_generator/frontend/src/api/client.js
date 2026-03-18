const BASE = '/api'

async function request(method, path, body, isForm = false) {
  const opts = { method, headers: {} }
  if (body) {
    if (isForm) {
      opts.body = body
    } else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }
  const res = await fetch(`${BASE}${path}`, opts)
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail || 'Request failed')
  return data
}

// ── Session ──────────────────────────────
export const createSession = (agent, apiKey) =>
  request('POST', '/upload/session', { agent, api_key: apiKey })

export const getSessionState = (sessionId) =>
  request('GET', `/chat/session/${sessionId}`)

// ── API key validation ────────────────────
export const validateKey = (agent, apiKey) =>
  request('POST', '/chat/validate-key', { agent, api_key: apiKey })

// ── Uploads ──────────────────────────────
export const uploadResume = (sessionId, file) => {
  const fd = new FormData()
  fd.append('session_id', sessionId)
  fd.append('file', file)
  return request('POST', '/upload/resume', fd, true)
}

export const fetchLinkedIn = (sessionId, url) =>
  request('POST', '/upload/linkedin', { session_id: sessionId, url })

export const addGitHub = (sessionId, url) => {
  const fd = new FormData()
  fd.append('session_id', sessionId)
  fd.append('url', url)
  return request('POST', '/upload/github', fd, true)
}

export const addAdditionalInfo = (sessionId, info) => {
  const fd = new FormData()
  fd.append('session_id', sessionId)
  fd.append('info', info)
  return request('POST', '/upload/additional-info', fd, true)
}

// ── Job Description ───────────────────────
export const fetchJdUrl = (sessionId, url) =>
  request('POST', '/upload/jd-url', { session_id: sessionId, url })

export const uploadJdFile = (sessionId, file) => {
  const fd = new FormData()
  fd.append('session_id', sessionId)
  fd.append('file', file)
  return request('POST', '/upload/jd-file', fd, true)
}

export const saveJdText = (sessionId, text) => {
  const fd = new FormData()
  fd.append('session_id', sessionId)
  fd.append('text', text)
  return request('POST', '/upload/jd-text', fd, true)
}

// ── Chat ──────────────────────────────────
export const generateResume = (sessionId) =>
  request('POST', '/chat/generate-resume', { session_id: sessionId })

export const sendMessage = (sessionId, message) =>
  request('POST', '/chat/message', { session_id: sessionId, message })

export const approveResume = (sessionId) =>
  request('POST', '/chat/approve-resume', { session_id: sessionId })

export const generateCoverLetter = (sessionId, additionalContext = '') =>
  request('POST', '/chat/generate-cover-letter', {
    session_id: sessionId,
    additional_context: additionalContext,
  })

// ── Export ────────────────────────────────
export const exportDocument = async (sessionId, contentType, format) => {
  const res = await fetch(`${BASE}/export/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      content_type: contentType,
      format,
    }),
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Export failed')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${contentType}.${format}`
  a.click()
  URL.revokeObjectURL(url)
}
