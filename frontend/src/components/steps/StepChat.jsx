import { useState, useEffect, useRef } from 'react'
import { Send, ChevronLeft, CheckCircle, FileText, Sparkles, Copy, Check } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import {
  generateResume, sendMessage, approveResume,
  generateCoverLetter
} from '../../api/client'

const RESUME_SECTION_HINTS = [
  'PROFESSIONAL EXPERIENCE', 'WORK EXPERIENCE', 'EDUCATION',
  'SKILLS', 'SUMMARY', 'CERTIFICATIONS', 'PROJECTS',
]

function containsResume(text) {
  const upper = text.toUpperCase()
  return RESUME_SECTION_HINTS.filter(kw => upper.includes(kw)).length >= 2
}

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-4 py-3">
      <div className="typing-dot" />
      <div className="typing-dot" />
      <div className="typing-dot" />
    </div>
  )
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 text-xs px-2.5 py-1.5 rounded-lg transition-all duration-200"
      style={{
        background: 'rgba(255,255,255,0.06)',
        border: '1px solid var(--border)',
        color: 'var(--text-muted)',
      }}
      title="Copy to clipboard"
    >
      {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

function Message({ msg }) {
  const isUser = msg.role === 'user'
  const hasResume = !isUser && containsResume(msg.content)

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="bubble-user">{msg.content}</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-1.5 animate-slide-up">
      <div className={`bubble-assistant ${hasResume ? 'has-resume' : ''}`}>
        {hasResume ? (
          <pre className="resume-preview">{msg.content}</pre>
        ) : (
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              ul: ({ children }) => <ul className="list-disc list-inside space-y-1 mb-2">{children}</ul>,
              li: ({ children }) => <li className="text-sm">{children}</li>,
              strong: ({ children }) => <strong className="text-amber-300 font-semibold">{children}</strong>,
            }}
          >
            {msg.content}
          </ReactMarkdown>
        )}
      </div>
      {hasResume && (
        <div className="flex items-center gap-2 ml-1">
          <CopyButton text={msg.content} />
          <span className="badge-success text-xs">
            <FileText size={11} /> ATS-formatted resume
          </span>
        </div>
      )}
    </div>
  )
}

export default function StepChat({ sessionId, sessionState, onBack, onNext, onUpdate }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [started, setStarted] = useState(false)
  const [approved, setApproved] = useState(false)
  const [approvingLoading, setApprovingLoading] = useState(false)
  const [coverLetterLoading, setCoverLetterLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // ── Generate resume on mount ───────────────
  useEffect(() => {
    if (!started && sessionId) {
      setStarted(true)
      handleGenerateResume()
    }
  }, [sessionId])

  const handleGenerateResume = async () => {
    setLoading(true)
    try {
      const res = await generateResume(sessionId)
      const aiMsg = { role: 'assistant', content: res.response }
      setMessages([aiMsg])
      if (res.has_resume) onUpdate()
    } catch (e) {
      setMessages([{
        role: 'assistant',
        content: `❌ ${e.message}\n\nPlease make sure your API key is set and you've uploaded a resume and job description.`,
      }])
    } finally {
      setLoading(false)
    }
  }

  // ── Send refinement message ────────────────
  const handleSend = async () => {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    const userMsg = { role: 'user', content: text }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    try {
      const res = await sendMessage(sessionId, text)
      setMessages(prev => [...prev, { role: 'assistant', content: res.response }])
      if (res.has_resume) onUpdate()
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `❌ ${e.message}` }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  // ── Approve resume ─────────────────────────
  const handleApprove = async () => {
    setApprovingLoading(true)
    try {
      await approveResume(sessionId)
      setApproved(true)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: '✅ **Resume approved!**\n\nYou can now export it or generate a cover letter.\n\n👉 Head to the **Export** tab, or ask me to write a cover letter for you.',
      }])
      onUpdate()
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `❌ ${e.message}` }])
    } finally {
      setApprovingLoading(false)
    }
  }

  // ── Generate cover letter ──────────────────
  const handleCoverLetter = async () => {
    setCoverLetterLoading(true)
    const userMsg = { role: 'user', content: 'Generate a cover letter for this role.' }
    setMessages(prev => [...prev, userMsg])
    try {
      const res = await generateCoverLetter(sessionId)
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `📄 **Cover Letter**\n\n${res.cover_letter}`,
      }])
      onUpdate()
    } catch (e) {
      setMessages(prev => [...prev, { role: 'assistant', content: `❌ ${e.message}` }])
    } finally {
      setCoverLetterLoading(false)
    }
  }

  const hasGeneratedResume = sessionState?.has_generated_resume
  const isApproved = approved || sessionState?.resume_approved

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-8 pt-8 pb-5 border-b flex items-center justify-between flex-shrink-0"
           style={{ borderColor: 'var(--border)' }}>
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="badge-warning">Step 3 of 4</span>
            {isApproved && <span className="badge-success">✓ Approved</span>}
          </div>
          <h2 className="font-display text-2xl text-white font-semibold">Build & Refine</h2>
          <p className="text-sm mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Chat to refine your resume. Approve when you're ready to export.
          </p>
        </div>
        <div className="flex gap-2">
          {hasGeneratedResume && !isApproved && (
            <button
              onClick={handleApprove}
              disabled={approvingLoading}
              className="btn-success gap-2 text-sm"
            >
              <CheckCircle size={15} />
              {approvingLoading ? 'Approving…' : 'Approve Resume'}
            </button>
          )}
          {isApproved && (
            <button
              onClick={handleCoverLetter}
              disabled={coverLetterLoading}
              className="btn-ghost gap-2 text-sm"
            >
              <Sparkles size={14} />
              {coverLetterLoading ? 'Writing…' : 'Cover Letter'}
            </button>
          )}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-8 py-6 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="flex flex-col items-center justify-center h-full gap-3 opacity-50">
            <div className="w-12 h-12 rounded-2xl bg-amber-500/10 flex items-center justify-center">
              <Sparkles size={22} className="text-amber-400" />
            </div>
            <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Starting resume generation…</p>
          </div>
        )}
        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        {loading && (
          <div className="flex animate-fade-in">
            <div className="bubble-assistant">
              <TypingDots />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Quick suggestions */}
      {!loading && messages.length > 0 && !isApproved && (
        <div className="px-8 pb-2 flex flex-wrap gap-1.5 flex-shrink-0">
          {[
            'Make the summary punchier',
            'Strengthen the bullet points',
            'Add more keywords from the JD',
            'Reorder experience by relevance',
          ].map(s => (
            <button
              key={s}
              onClick={() => { setInput(s); inputRef.current?.focus() }}
              className="text-xs px-3 py-1.5 rounded-full transition-all duration-200"
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                color: 'var(--text-muted)',
              }}
              onMouseEnter={e => {
                e.target.style.borderColor = 'rgba(251,191,36,0.4)'
                e.target.style.color = 'var(--text-secondary)'
              }}
              onMouseLeave={e => {
                e.target.style.borderColor = 'var(--border)'
                e.target.style.color = 'var(--text-muted)'
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div className="px-8 py-4 border-t flex-shrink-0" style={{ borderColor: 'var(--border)' }}>
        <div className="flex gap-3 items-end">
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder={isApproved ? 'Ask to generate cover letter or make tweaks…' : 'Ask for changes — e.g. "highlight my Python skills more"'}
            rows={2}
            disabled={loading}
            className="input-field flex-1 resize-none text-sm"
            style={{ lineHeight: '1.5' }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="btn-primary w-10 h-10 p-0 flex-shrink-0 rounded-xl"
            title="Send (Enter)"
          >
            <Send size={15} />
          </button>
        </div>
        <p className="text-xs mt-2 text-center" style={{ color: 'var(--text-muted)' }}>
          Enter to send · Shift+Enter for new line · Approve resume to unlock Export
        </p>
      </div>

      {/* Footer nav */}
      <div className="px-8 pb-5 flex items-center justify-between flex-shrink-0">
        <button onClick={onBack} className="btn-ghost gap-2 text-xs py-2">
          <ChevronLeft size={14} /> Back to JD
        </button>
        {(isApproved || hasGeneratedResume) && (
          <button onClick={onNext} className="btn-primary gap-2 text-sm">
            Go to Export
          </button>
        )}
      </div>
    </div>
  )
}
