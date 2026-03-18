import { useState, useCallback } from 'react'
import Sidebar from './components/Sidebar'
import StepProfile from './components/steps/StepProfile'
import StepJD from './components/steps/StepJD'
import StepChat from './components/steps/StepChat'
import StepExport from './components/steps/StepExport'
import { createSession, getSessionState } from './api/client'

const STEP_ORDER = ['profile', 'jd', 'chat', 'export']

export default function App() {
  const [currentStep, setCurrentStep] = useState('profile')
  const [sessionId, setSessionId] = useState(null)
  const [sessionState, setSessionState] = useState(null)
  const [sessionError, setSessionError] = useState(null)

  // Called by Sidebar once API key is validated
  const handleSessionReady = useCallback(async (agent, apiKey) => {
    setSessionError(null)
    try {
      if (!sessionId) {
        const res = await createSession(agent, apiKey)
        setSessionId(res.session_id)
      }
    } catch (e) {
      setSessionError(e.message)
    }
  }, [sessionId])

  // Refresh session state after any upload / generation
  const refreshState = useCallback(async () => {
    if (!sessionId) return
    try {
      const state = await getSessionState(sessionId)
      setSessionState(state)
    } catch { /* silent */ }
  }, [sessionId])

  const goNext = () => {
    const idx = STEP_ORDER.indexOf(currentStep)
    if (idx < STEP_ORDER.length - 1) setCurrentStep(STEP_ORDER[idx + 1])
  }

  const goBack = () => {
    const idx = STEP_ORDER.indexOf(currentStep)
    if (idx > 0) setCurrentStep(STEP_ORDER[idx - 1])
  }

  const renderStep = () => {
    if (!sessionId && currentStep !== 'profile') {
      return (
        <div className="flex flex-col items-center justify-center h-full gap-4 px-12 text-center">
          <div className="w-14 h-14 rounded-2xl bg-amber-500/10 flex items-center justify-center">
            <span className="text-2xl">🔑</span>
          </div>
          <div>
            <p className="text-white font-semibold">Connect your AI engine first</p>
            <p className="text-sm mt-1" style={{ color: 'var(--text-muted)' }}>
              Add your API key in the sidebar and click Connect to get started.
            </p>
          </div>
        </div>
      )
    }

    switch (currentStep) {
      case 'profile':
        return (
          <StepProfile
            sessionId={sessionId}
            onNext={goNext}
            onUpdate={refreshState}
          />
        )
      case 'jd':
        return (
          <StepJD
            sessionId={sessionId}
            onNext={goNext}
            onBack={goBack}
            onUpdate={refreshState}
          />
        )
      case 'chat':
        return (
          <StepChat
            sessionId={sessionId}
            sessionState={sessionState}
            onNext={goNext}
            onBack={goBack}
            onUpdate={refreshState}
          />
        )
      case 'export':
        return (
          <StepExport
            sessionId={sessionId}
            sessionState={sessionState}
            onBack={goBack}
          />
        )
      default:
        return null
    }
  }

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        currentStep={currentStep}
        onStepChange={setCurrentStep}
        sessionState={sessionState}
        sessionReady={handleSessionReady}
      />

      {/* Main content */}
      <main className="flex-1 overflow-hidden flex flex-col min-w-0"
            style={{ background: 'linear-gradient(135deg, #0D1220 0%, #0B0F1A 100%)' }}>
        {sessionError && (
          <div className="flex items-center gap-2 px-6 py-2.5 text-xs text-red-400 bg-red-500/10 border-b border-red-500/20">
            ❌ {sessionError}
          </div>
        )}

        {/* Subtle background texture */}
        <div className="absolute inset-0 pointer-events-none overflow-hidden" style={{ zIndex: 0 }}>
          <div className="absolute top-0 right-0 w-96 h-96 rounded-full opacity-5"
               style={{ background: 'radial-gradient(circle, #F59E0B 0%, transparent 70%)', transform: 'translate(30%, -30%)' }} />

        </div>

        <div className="relative flex-1 overflow-hidden" style={{ zIndex: 1 }}>
          {renderStep()}
        </div>
      </main>
    </div>
  )
}
