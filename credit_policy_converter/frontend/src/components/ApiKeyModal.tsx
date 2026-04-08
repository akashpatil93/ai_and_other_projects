import { useState } from 'react'
import { apiClient, keyStore } from '../api/client'

interface Props {
  onClose: () => void
}

export default function ApiKeyModal({ onClose }: Props) {
  const [value, setValue] = useState(keyStore.get())
  const [show, setShow] = useState(false)
  const [status, setStatus] = useState<'idle' | 'checking' | 'ok' | 'error'>('idle')
  const [message, setMessage] = useState('')

  const handleSave = async () => {
    const trimmed = value.trim()
    if (!trimmed) {
      setStatus('error')
      setMessage('Please enter an API key.')
      return
    }
    setStatus('checking')
    setMessage('')
    try {
      const res = await apiClient.verifyKey(trimmed)
      keyStore.set(trimmed)
      setStatus('ok')
      setMessage(`Key saved — ${res.masked}`)
      setTimeout(onClose, 1200)
    } catch (err: unknown) {
      const detail =
        err instanceof Error
          ? err.message
          : (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? 'Invalid key.'
      setStatus('error')
      setMessage(detail)
    }
  }

  const handleClear = () => {
    keyStore.clear()
    setValue('')
    setStatus('idle')
    setMessage('')
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-indigo-100 rounded-lg flex items-center justify-center">
              <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
            </div>
            <span className="font-semibold text-gray-900">Anthropic API Key</span>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5 space-y-4">
          <p className="text-sm text-gray-500">
            Your key is stored only in your browser's local storage and sent directly to the backend.
            It is never logged or stored server-side.
          </p>

          <div className="relative">
            <input
              type={show ? 'text' : 'password'}
              placeholder="sk-ant-api03-..."
              value={value}
              onChange={(e) => { setValue(e.target.value); setStatus('idle'); setMessage('') }}
              onKeyDown={(e) => e.key === 'Enter' && handleSave()}
              className="w-full border border-gray-200 rounded-xl px-4 py-2.5 pr-12 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300"
            />
            <button
              onClick={() => setShow((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              tabIndex={-1}
            >
              {show ? (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                </svg>
              ) : (
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                </svg>
              )}
            </button>
          </div>

          {/* Status message */}
          {message && (
            <p className={`text-xs flex items-center gap-1.5 ${status === 'ok' ? 'text-green-600' : status === 'error' ? 'text-red-500' : 'text-gray-500'}`}>
              {status === 'ok' && (
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              )}
              {status === 'error' && (
                <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              )}
              {message}
            </p>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 bg-gray-50 border-t border-gray-100 flex items-center justify-between gap-3">
          <button
            onClick={handleClear}
            disabled={!value}
            className="text-sm text-red-500 hover:text-red-700 disabled:opacity-30 disabled:cursor-not-allowed transition"
          >
            Clear key
          </button>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 rounded-lg border border-gray-200 hover:bg-gray-100 transition"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={status === 'checking'}
              className="px-4 py-2 text-sm font-medium bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg transition disabled:opacity-60 flex items-center gap-2"
            >
              {status === 'checking' && (
                <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              )}
              {status === 'checking' ? 'Verifying...' : 'Save & verify'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
