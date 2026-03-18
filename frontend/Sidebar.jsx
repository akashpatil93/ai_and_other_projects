import { useState } from 'react'
import {
  KeyRound, ChevronDown, CheckCircle2, Circle, Lock,
  FileText, Briefcase, MessageSquare, Download, Sparkles
} from 'lucide-react'
import { validateKey } from '../api/client'

const AGENTS = [
  { value: 'claude', label: 'Claude (Anthropic)', color: '#F59E0B' },
  { value: 'gemini', label: 'Gemini (Google)', color: '#4285F4' },
]

const STEPS = [
  { id: 'profile',  label: 'Your Profile',      icon: FileText,      desc: 'Resume + LinkedIn' },
  { id: 'jd',       label: 'Job Description',   icon: Briefcase,     desc: 'URL, PDF, or paste' },
  { id: 'chat',     label: 'Build Resume',       icon: MessageSquare, desc: 'AI tailoring + refine' },
  { id: 'export',   label: 'Export',             icon: Download,      desc: 'TXT, PDF, or Word' },
]

export default function Sidebar({ currentStep, onStepChange, sessionState, sessionReady }) {
  const [agent, setAgent] = useState('claude')
  const [apiKey, setApiKey] = useState('')
  const [showKey, setShowKey] = useState(false)
  const [showAgentMenu, setShowAgentMenu] = useState(false)
  const [validating, setValidating] = useState(false)
  const [keyStatus, setKeyStatus] = useState(null) // null | 'valid' | 'invalid'
  const [keyMessage, setKeyMessage] = useState('')

  const selectedAgent = AGENTS.find(a => a.value === agent)

  const handleValidate = async () => {
    if (!apiKey.trim()) return
    setValidating(true)
    setKeyStatus(null)
    try {
      const res = await validateKey(agent, apiKey.trim())
      setKeyStatus(res.success ? 'valid' : 'invalid')
      setKeyMessage(res.message)
      if (res.success) sessionReady(agent, apiKey.trim())
    } catch (e) {
      setKeyStatus('invalid')
      setKeyMessage(e.message)
    } finally {
      setValidating(false)
    }
  }

  function stepStatus(stepId) {
    if (!sessionState) return 'locked'
    const s = sessionState
    switch (stepId) {
      case 'profile': return (s.has_resume_uploaded) ? 'completed' : 'active'
      case 'jd':      return !s.has_resume_uploaded ? 'locked'
                           : s.has_jd ? 'completed' : 'active'
      case 'chat':    return !s.has_jd ? 'locked'
                           : s.resume_approved ? 'completed' : 'active'
      case 'export':  return !s.has_generated_resume ? 'locked' : 'active'
      default: return 'active'
    }
  }

  return (
    <aside className="sidebar flex flex-col h-full w-72 flex-shrink-0">
      {/* Logo */}
      <div className="px-6 pt-7 pb-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center"
               style={{ background: 'linear-gradient(135deg, #F59E0B, #FBBF24)' }}>
            <Sparkles size={15} color="#0B0F1A" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="font-display text-white font-semibold text-lg leading-none">ResumeAI</h1>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>Tailored. ATS-ready.</p>
          </div>
        </div>
      </div>

      <hr className="divider mx-4" />

      {/* ── API Config ─────────────────────── */}
      <div className="px-4 pt-5 pb-4 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-widest px-1"
           style={{ color: 'var(--text-muted)' }}>AI Engine</p>

        {/* Agent selector */}
        <div className="relative">
          <button
            onClick={() => setShowAgentMenu(!showAgentMenu)}
            className="w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm transition-all duration-200"
            style={{
              background: 'var(--surface)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          >
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full" style={{ background: selectedAgent.color }} />
              <span>{selectedAgent.label}</span>
            </div>
            <ChevronDown size={14} style={{ color: 'var(--text-muted)' }}
              className={`transition-transform ${showAgentMenu ? 'rotate-180' : ''}`} />
          </button>

          {showAgentMenu && (
            <div className="absolute top-full left-0 right-0 mt-1 rounded-lg overflow-hidden z-20"
                 style={{ background: '#131B2A', border: '1px solid var(--border)', boxShadow: '0 8px 24px rgba(0,0,0,0.4)' }}>
              {AGENTS.map(a => (
                <button
                  key={a.value}
                  onClick={() => { setAgent(a.value); setShowAgentMenu(false); setKeyStatus(null) }}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-left transition-colors"
                  style={{
                    color: agent === a.value ? a.color : 'var(--text-secondary)',
                    background: agent === a.value ? 'rgba(255,255,255,0.05)' : 'transparent',
                  }}
                >
                  <div className="w-2 h-2 rounded-full" style={{ background: a.color }} />
                  {a.label}
                  {agent === a.value && <CheckCircle2 size={13} className="ml-auto" />}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* API Key input */}
        <div className="space-y-2">
          <div className="relative">
            <KeyRound size={14} className="absolute left-3 top-1/2 -translate-y-1/2"
                      style={{ color: 'var(--text-muted)' }} />
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={e => { setApiKey(e.target.value); setKeyStatus(null) }}
              onKeyDown={e => e.key === 'Enter' && handleValidate()}
              placeholder="Paste API key…"
              className="input-field pl-8 pr-10 font-mono text-xs"
            />
            <button
              onClick={() => setShowKey(!showKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-xs transition-colors"
              style={{ color: 'var(--text-muted)' }}
            >
              {showKey ? '●●' : '👁'}
            </button>
          </div>

          <button
            onClick={handleValidate}
            disabled={!apiKey.trim() || validating}
            className="btn-primary w-full text-xs py-2"
          >
            {validating ? 'Validating…' : keyStatus === 'valid' ? '✓ Connected' : 'Connect'}
          </button>

          {keyMessage && (
            <p className={`text-xs px-1 ${keyStatus === 'valid' ? 'text-green-400' : 'text-red-400'}`}>
              {keyMessage}
            </p>
          )}
        </div>
      </div>

      <hr className="divider mx-4" />

      {/* ── Step Navigation ─────────────────── */}
      <nav className="flex-1 px-3 pt-5 pb-4 space-y-1 overflow-y-auto">
        <p className="text-xs font-semibold uppercase tracking-widest px-3 pb-2"
           style={{ color: 'var(--text-muted)' }}>Workflow</p>

        {STEPS.map((step, idx) => {
          const status = stepStatus(step.id)
          const isDisabled = status === 'locked'
          const isActive = currentStep === step.id
          const isDone = status === 'completed'
          const Icon = step.icon

          return (
            <button
              key={step.id}
              onClick={() => !isDisabled && onStepChange(step.id)}
              className={`step-item w-full text-left ${isActive ? 'active' : ''} ${isDone && !isActive ? 'completed' : ''} ${isDisabled ? 'disabled' : ''}`}
            >
              <div className="flex items-center gap-3 flex-1">
                <div className="relative">
                  <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-all duration-200 ${
                    isActive ? 'bg-amber-500/20' : isDone ? 'bg-green-500/15' : 'bg-white/5'
                  }`}>
                    {isDone
                      ? <CheckCircle2 size={14} className="text-green-400" />
                      : isDisabled
                      ? <Lock size={13} style={{ color: 'var(--text-muted)' }} />
                      : <Icon size={14} className={isActive ? 'text-amber-400' : ''} />
                    }
                  </div>
                  {idx < STEPS.length - 1 && (
                    <div className="absolute left-3.5 top-7 w-px h-3 -translate-x-1/2"
                         style={{ background: isDone ? 'rgba(52,211,153,0.3)' : 'var(--border)' }} />
                  )}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium leading-none truncate">{step.label}</p>
                  <p className="text-xs mt-0.5 truncate" style={{ color: 'var(--text-muted)' }}>{step.desc}</p>
                </div>
              </div>
            </button>
          )
        })}
      </nav>

      {/* ── Footer ─────────────────────────── */}
      <div className="px-4 pb-5 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
        <p className="text-xs text-center" style={{ color: 'var(--text-muted)' }}>
          Your data stays local · No storage
        </p>
      </div>
    </aside>
  )
}
