import { useState } from 'react'
import { FileText, Download, CheckCircle2, Copy, Check, ChevronLeft, Sparkles } from 'lucide-react'
import { exportDocument } from '../../api/client'

const FORMATS = [
  { id: 'txt',  label: 'Plain Text',   desc: 'Best for ATS copy-paste',    icon: '📄' },
  { id: 'pdf',  label: 'PDF',          desc: 'Formatted, print-ready',     icon: '🔴' },
  { id: 'docx', label: 'Word (.docx)', desc: 'Edit in Microsoft Word',     icon: '📘' },
]

function CopyArea({ content, label }) {
  const [copied, setCopied] = useState(false)

  if (!content) return null

  const handleCopy = () => {
    navigator.clipboard.writeText(content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{label}</span>
        <button onClick={handleCopy} className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-all duration-200"
          style={{ background: 'var(--surface)', border: '1px solid var(--border)', color: 'var(--text-muted)' }}>
          {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
          {copied ? 'Copied!' : 'Copy all'}
        </button>
      </div>
      <pre className="resume-preview card overflow-auto max-h-72 text-xs">{content}</pre>
    </div>
  )
}

export default function StepExport({ sessionId, sessionState, onBack }) {
  const [downloadingFormat, setDownloadingFormat] = useState(null)
  const [errors, setErrors] = useState({})

  const hasResume = sessionState?.has_generated_resume
  const hasCoverLetter = sessionState?.has_cover_letter
  const isApproved = sessionState?.resume_approved

  const [resumeContent, setResumeContent] = useState('')
  const [coverLetterContent, setCoverLetterContent] = useState('')
  const [fetched, setFetched] = useState(false)

  // Fetch plain text content for preview/copy on mount
  const fetchPreview = async () => {
    if (fetched || !sessionId) return
    setFetched(true)
    try {
      const res = await fetch('/api/export/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, content_type: 'resume', format: 'txt' }),
      })
      if (res.ok) setResumeContent(await res.text())
    } catch { /* silent */ }
    if (hasCoverLetter) {
      try {
        const res = await fetch('/api/export/download', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: sessionId, content_type: 'cover_letter', format: 'txt' }),
        })
        if (res.ok) setCoverLetterContent(await res.text())
      } catch { /* silent */ }
    }
  }

  // Lazy-load preview on render
  if (!fetched && hasResume) fetchPreview()

  const handleDownload = async (contentType, format) => {
    const key = `${contentType}-${format}`
    setDownloadingFormat(key)
    setErrors(prev => ({ ...prev, [key]: null }))
    try {
      await exportDocument(sessionId, contentType, format)
    } catch (e) {
      setErrors(prev => ({ ...prev, [key]: e.message }))
    } finally {
      setDownloadingFormat(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-8 pb-6 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2 mb-1">
          <span className="badge-warning">Step 4 of 4</span>
          {isApproved && <span className="badge-success">✓ Resume Approved</span>}
        </div>
        <h2 className="font-display text-2xl text-white font-semibold">Export</h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Download your tailored documents or copy them directly.
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-8">

        {/* Resume export */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <FileText size={16} className="text-amber-400" />
            <h3 className="text-base font-semibold text-white">Resume</h3>
            {hasResume && <span className="badge-success">Ready</span>}
          </div>

          {!hasResume ? (
            <div className="card text-center py-8">
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                Go to <strong className="text-gray-300">Build & Refine</strong> to generate your resume first.
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                {FORMATS.map(fmt => {
                  const key = `resume-${fmt.id}`
                  const isLoading = downloadingFormat === key
                  const error = errors[key]
                  return (
                    <div key={fmt.id} className="card space-y-3">
                      <div className="text-2xl">{fmt.icon}</div>
                      <div>
                        <p className="text-sm font-semibold text-gray-200">{fmt.label}</p>
                        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{fmt.desc}</p>
                      </div>
                      <button
                        onClick={() => handleDownload('resume', fmt.id)}
                        disabled={isLoading}
                        className="btn-ghost w-full text-xs py-2 gap-2"
                      >
                        {isLoading
                          ? 'Generating…'
                          : <><Download size={12} /> Download</>
                        }
                      </button>
                      {error && <p className="text-xs text-red-400">{error}</p>}
                    </div>
                  )
                })}
              </div>
              <CopyArea content={resumeContent} label="Resume — plain text (copy & paste)" />
            </>
          )}
        </section>

        {/* Cover letter export */}
        <section className="space-y-4">
          <div className="flex items-center gap-2">
            <Sparkles size={16} className="text-amber-400" />
            <h3 className="text-base font-semibold text-white">Cover Letter</h3>
            {hasCoverLetter && <span className="badge-success">Ready</span>}
          </div>

          {!hasCoverLetter ? (
            <div className="card text-center py-8 space-y-2">
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
                {!isApproved
                  ? 'Approve your resume first, then generate a cover letter from the Build tab.'
                  : 'Go to Build & Refine and ask to generate a cover letter.'}
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3">
                {FORMATS.map(fmt => {
                  const key = `cover_letter-${fmt.id}`
                  const isLoading = downloadingFormat === key
                  const error = errors[key]
                  return (
                    <div key={fmt.id} className="card space-y-3">
                      <div className="text-2xl">{fmt.icon}</div>
                      <div>
                        <p className="text-sm font-semibold text-gray-200">{fmt.label}</p>
                        <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{fmt.desc}</p>
                      </div>
                      <button
                        onClick={() => handleDownload('cover_letter', fmt.id)}
                        disabled={isLoading}
                        className="btn-ghost w-full text-xs py-2 gap-2"
                      >
                        {isLoading ? 'Generating…' : <><Download size={12} /> Download</>}
                      </button>
                      {error && <p className="text-xs text-red-400">{error}</p>}
                    </div>
                  )
                })}
              </div>
              <CopyArea content={coverLetterContent} label="Cover Letter — plain text" />
            </>
          )}
        </section>

        {/* ATS tips */}
        <section>
          <div className="card-amber space-y-2">
            <p className="text-xs font-semibold text-amber-400 uppercase tracking-wide">💡 ATS Tips</p>
            <ul className="text-xs space-y-1.5" style={{ color: 'var(--text-secondary)' }}>
              <li>• Use the <strong className="text-gray-300">Plain Text</strong> version when applying through ATS portals — paste directly into their text fields.</li>
              <li>• Use <strong className="text-gray-300">PDF</strong> for direct email applications or attaching to applications.</li>
              <li>• Use <strong className="text-gray-300">Word</strong> if a recruiter requests an editable version.</li>
              <li>• Always customize for each application — this resume is already tailored to this specific JD.</li>
            </ul>
          </div>
        </section>
      </div>

      {/* Footer */}
      <div className="px-8 py-5 border-t flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
        <button onClick={onBack} className="btn-ghost gap-2">
          <ChevronLeft size={15} /> Back to Chat
        </button>
        <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
          Reload the page to start a new application
        </p>
      </div>
    </div>
  )
}
