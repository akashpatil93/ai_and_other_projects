import { useState, useRef } from 'react'
import { Link2, Upload, AlignLeft, ChevronRight, ChevronLeft, CheckCircle2, AlertCircle } from 'lucide-react'
import { fetchJdUrl, uploadJdFile, saveJdText } from '../../api/client'

const TABS = [
  { id: 'url',  label: 'Paste URL',    icon: Link2 },
  { id: 'file', label: 'Upload File',  icon: Upload },
  { id: 'text', label: 'Paste Text',   icon: AlignLeft },
]

function StatusMessage({ status }) {
  if (!status) return null
  const isError = status.type === 'error'
  return (
    <div className={`flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs ${
      isError
        ? 'bg-red-500/10 text-red-400 border border-red-500/20'
        : 'bg-green-500/10 text-green-400 border border-green-500/20'
    }`}>
      {isError
        ? <AlertCircle size={13} className="mt-0.5 flex-shrink-0" />
        : <CheckCircle2 size={13} className="mt-0.5 flex-shrink-0" />}
      <span className="leading-relaxed">{status.message}</span>
    </div>
  )
}

export default function StepJD({ sessionId, onNext, onBack, onUpdate }) {
  const [activeTab, setActiveTab] = useState('url')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState(null)
  const [jdDone, setJdDone] = useState(false)
  const [preview, setPreview] = useState('')

  const [url, setUrl] = useState('')
  const [text, setText] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileInputRef = useRef(null)

  const succeed = (msg, prev) => {
    setStatus({ type: 'success', message: msg })
    setPreview(prev || '')
    setJdDone(true)
    onUpdate()
  }

  const fail = (msg) => setStatus({ type: 'error', message: msg })

  // ── URL ──────────────────────────────────
  const handleUrl = async () => {
    if (!url.trim()) return
    setLoading(true); setStatus(null)
    try {
      const res = await fetchJdUrl(sessionId, url.trim())
      succeed(res.message, res.preview)
    } catch (e) { fail(e.message) }
    finally { setLoading(false) }
  }

  // ── File ─────────────────────────────────
  const handleFile = async (file) => {
    if (!file) return
    setLoading(true); setStatus(null)
    try {
      const res = await uploadJdFile(sessionId, file)
      succeed(res.message, res.preview)
    } catch (e) { fail(e.message) }
    finally { setLoading(false) }
  }

  // ── Text ─────────────────────────────────
  const handleText = async () => {
    if (!text.trim()) return
    setLoading(true); setStatus(null)
    try {
      const res = await saveJdText(sessionId, text.trim())
      succeed(res.message, text.slice(0, 300))
    } catch (e) { fail(e.message) }
    finally { setLoading(false) }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-8 pb-6 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2 mb-1">
          <span className="badge-warning">Step 2 of 4</span>
        </div>
        <h2 className="font-display text-2xl text-white font-semibold">Job Description</h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Provide the JD via URL, file, or by pasting the text directly.
        </p>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-5">

        {/* Tab selector */}
        <div className="flex rounded-xl p-1 gap-1" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
          {TABS.map(tab => {
            const Icon = tab.icon
            return (
              <button
                key={tab.id}
                onClick={() => { setActiveTab(tab.id); setStatus(null) }}
                className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                  activeTab === tab.id
                    ? 'bg-amber-500/15 text-amber-400'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            )
          })}
        </div>

        {/* Tab panels */}
        <div className="card space-y-3">
          {activeTab === 'url' && (
            <>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Works with LinkedIn Jobs, Indeed, Greenhouse, Lever, Workday, and most job boards.
                If a site blocks access, use Paste Text instead.
              </p>
              <div className="flex gap-2">
                <input
                  type="url"
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleUrl()}
                  placeholder="https://jobs.lever.co/company/job-id"
                  className="input-field flex-1"
                />
                <button
                  onClick={handleUrl}
                  disabled={!url.trim() || loading}
                  className="btn-primary px-4 flex-shrink-0"
                >
                  {loading ? 'Fetching…' : 'Fetch'}
                </button>
              </div>
            </>
          )}

          {activeTab === 'file' && (
            <>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>PDF or DOCX</p>
              <div
                className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
                onDragOver={e => { e.preventDefault(); setDragOver(true) }}
                onDragLeave={() => setDragOver(false)}
                onDrop={e => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files?.[0]) }}
                onClick={() => fileInputRef.current?.click()}
              >
                <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
                  <Upload size={18} className="text-amber-400" />
                </div>
                <p className="text-sm font-medium text-gray-300">
                  {loading ? 'Parsing file…' : 'Drop JD file here or click to browse'}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>PDF or DOCX</p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".pdf,.docx"
                onChange={e => handleFile(e.target.files?.[0])}
              />
            </>
          )}

          {activeTab === 'text' && (
            <>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                Copy the full job description and paste it below.
              </p>
              <textarea
                value={text}
                onChange={e => setText(e.target.value)}
                placeholder="Paste the full job description here…"
                rows={10}
                className="input-field resize-y text-sm font-body"
              />
              <button
                onClick={handleText}
                disabled={!text.trim() || loading}
                className="btn-primary w-full"
              >
                {loading ? 'Saving…' : 'Save Job Description'}
              </button>
            </>
          )}

          <StatusMessage status={status} />
        </div>

        {/* Preview */}
        {preview && (
          <div className="card-amber space-y-2">
            <p className="text-xs font-semibold text-amber-400">Preview — first 300 chars</p>
            <p className="text-xs leading-relaxed font-mono" style={{ color: 'var(--text-secondary)' }}>
              {preview}
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-8 py-5 border-t flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
        <button onClick={onBack} className="btn-ghost gap-2">
          <ChevronLeft size={15} /> Back
        </button>
        <button
          onClick={onNext}
          disabled={!jdDone}
          className="btn-primary gap-2"
        >
          Build Resume <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}
