import { useState, useRef } from 'react'
import { Upload, Link2, FileText, Plus, CheckCircle2, AlertCircle, ChevronRight, Github } from 'lucide-react'
import { uploadResume, fetchLinkedIn, addGitHub, addAdditionalInfo } from '../../api/client'

function StatusLine({ status }) {
  if (!status) return null
  const isError = status.type === 'error'
  const isWarning = status.type === 'warning'
  return (
    <div className={`flex items-start gap-2 rounded-lg px-3 py-2.5 text-xs mt-2 ${
      isError ? 'bg-red-500/10 text-red-400 border border-red-500/20' :
      isWarning ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20' :
      'bg-green-500/10 text-green-400 border border-green-500/20'
    }`}>
      {isError || isWarning
        ? <AlertCircle size={13} className="mt-0.5 flex-shrink-0" />
        : <CheckCircle2 size={13} className="mt-0.5 flex-shrink-0" />}
      <span className="leading-relaxed">{status.message}</span>
    </div>
  )
}

function SectionCard({ icon: Icon, title, badge, children }) {
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-amber-500/15 flex items-center justify-center">
            <Icon size={14} className="text-amber-400" />
          </div>
          <span className="text-sm font-semibold text-gray-200">{title}</span>
        </div>
        {badge}
      </div>
      {children}
    </div>
  )
}

export default function StepProfile({ sessionId, onNext, onUpdate }) {
  const [resumeStatus, setResumeStatus] = useState(null)
  const [resumeLoading, setResumeLoading] = useState(false)
  const [resumeDone, setResumeDone] = useState(false)
  const [dragOver, setDragOver] = useState(false)

  const [linkedInUrl, setLinkedInUrl] = useState('')
  const [linkedInStatus, setLinkedInStatus] = useState(null)
  const [linkedInLoading, setLinkedInLoading] = useState(false)
  const [linkedInDone, setLinkedInDone] = useState(false)

  const [githubUrl, setGithubUrl] = useState('')
  const [githubStatus, setGithubStatus] = useState(null)
  const [githubLoading, setGithubLoading] = useState(false)

  const [otherInfo, setOtherInfo] = useState('')
  const [otherSaved, setOtherSaved] = useState(false)

  const fileInputRef = useRef(null)

  // ── Resume upload ──────────────────────────
  const handleResumeFile = async (file) => {
    if (!file) return
    setResumeLoading(true)
    setResumeStatus(null)
    try {
      const res = await uploadResume(sessionId, file)
      setResumeStatus({ type: 'success', message: res.message })
      setResumeDone(true)
      onUpdate()
    } catch (e) {
      setResumeStatus({ type: 'error', message: e.message })
    } finally {
      setResumeLoading(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleResumeFile(file)
  }

  // ── LinkedIn ───────────────────────────────
  const handleLinkedIn = async () => {
    if (!linkedInUrl.trim()) return
    setLinkedInLoading(true)
    setLinkedInStatus(null)
    try {
      const res = await fetchLinkedIn(sessionId, linkedInUrl.trim())
      if (res.success) {
        setLinkedInStatus({ type: 'success', message: res.message })
        setLinkedInDone(true)
      } else {
        setLinkedInStatus({ type: 'warning', message: res.message })
      }
      onUpdate()
    } catch (e) {
      setLinkedInStatus({ type: 'error', message: e.message })
    } finally {
      setLinkedInLoading(false)
    }
  }

  // ── GitHub ─────────────────────────────────
  const handleGitHub = async () => {
    if (!githubUrl.trim()) return
    setGithubLoading(true)
    setGithubStatus(null)
    try {
      const res = await addGitHub(sessionId, githubUrl.trim())
      setGithubStatus({ type: res.success ? 'success' : 'error', message: res.message })
    } catch (e) {
      setGithubStatus({ type: 'error', message: e.message })
    } finally {
      setGithubLoading(false)
    }
  }

  // ── Additional info ────────────────────────
  const handleSaveOther = async () => {
    if (!otherInfo.trim()) return
    await addAdditionalInfo(sessionId, otherInfo.trim())
    setOtherSaved(true)
    setTimeout(() => setOtherSaved(false), 2000)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-8 pb-6 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2 mb-1">
          <span className="badge-warning">Step 1 of 4</span>
        </div>
        <h2 className="font-display text-2xl text-white font-semibold">Your Profile</h2>
        <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
          Upload your resume and any additional context you'd like the AI to use.
        </p>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-5">

        {/* Resume upload — required */}
        <SectionCard
          icon={FileText}
          title="Resume"
          badge={<span className={resumeDone ? 'badge-success' : 'badge-warning'}>{resumeDone ? '✓ Uploaded' : 'Required'}</span>}
        >
          <div
            className={`drop-zone ${dragOver ? 'drag-over' : ''}`}
            onDragOver={e => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 flex items-center justify-center">
              <Upload size={18} className="text-amber-400" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-300">
                {resumeLoading ? 'Parsing resume…' : 'Drop your resume here'}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>
                PDF, DOCX, or TXT · Click to browse
              </p>
            </div>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.docx,.txt"
            onChange={e => handleResumeFile(e.target.files?.[0])}
          />
          <StatusLine status={resumeStatus} />
        </SectionCard>

        {/* LinkedIn */}
        <SectionCard
          icon={Link2}
          title="LinkedIn Profile"
          badge={linkedInDone ? <span className="badge-success">✓ Linked</span> : <span className="badge-neutral">Optional</span>}
        >
          <div className="flex gap-2">
            <input
              type="url"
              value={linkedInUrl}
              onChange={e => setLinkedInUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleLinkedIn()}
              placeholder="https://linkedin.com/in/your-name"
              className="input-field flex-1"
            />
            <button
              onClick={handleLinkedIn}
              disabled={!linkedInUrl.trim() || linkedInLoading}
              className="btn-ghost px-3 flex-shrink-0"
            >
              {linkedInLoading ? '…' : <Plus size={15} />}
            </button>
          </div>
          <StatusLine status={linkedInStatus} />
        </SectionCard>

        {/* GitHub */}
        <SectionCard
          icon={Github}
          title="GitHub / Portfolio"
          badge={<span className="badge-neutral">Optional</span>}
        >
          <div className="flex gap-2">
            <input
              type="url"
              value={githubUrl}
              onChange={e => setGithubUrl(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleGitHub()}
              placeholder="https://github.com/username"
              className="input-field flex-1"
            />
            <button
              onClick={handleGitHub}
              disabled={!githubUrl.trim() || githubLoading}
              className="btn-ghost px-3 flex-shrink-0"
            >
              {githubLoading ? '…' : <Plus size={15} />}
            </button>
          </div>
          <StatusLine status={githubStatus} />
        </SectionCard>

        {/* Extra info */}
        <SectionCard
          icon={Plus}
          title="Additional Information"
          badge={<span className="badge-neutral">Optional</span>}
        >
          <textarea
            value={otherInfo}
            onChange={e => setOtherInfo(e.target.value)}
            placeholder="Patents, publications, awards, languages, volunteer work, or anything relevant not on your resume…"
            rows={3}
            className="input-field resize-none text-sm"
          />
          <button
            onClick={handleSaveOther}
            disabled={!otherInfo.trim()}
            className="btn-ghost text-xs py-2"
          >
            {otherSaved ? '✓ Saved' : 'Save info'}
          </button>
        </SectionCard>
      </div>

      {/* Footer */}
      <div className="px-8 py-5 border-t flex justify-end" style={{ borderColor: 'var(--border)' }}>
        <button
          onClick={onNext}
          disabled={!resumeDone}
          className="btn-primary gap-2"
        >
          Continue to Job Description
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}
