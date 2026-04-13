import { useState } from 'react'
import FileUpload from './components/FileUpload'
import ProcessingStatus from './components/ProcessingStatus'
import WorkflowViewer from './components/WorkflowViewer'
import RuleEditor from './components/RuleEditor'
import ApiKeyModal from './components/ApiKeyModal'
import { apiClient, keyStore } from './api/client'
import type { WorkflowData, ValidationResult } from './types/workflow'

type Step = 'upload' | 'generating' | 'review'
type ReviewTab = 'json' | 'rules'

export default function App() {
  const [step, setStep] = useState<Step>('upload')
  const [status, setStatus] = useState('Uploading document...')
  const [workflowId, setWorkflowId] = useState<string | null>(null)
  const [workflow, setWorkflow] = useState<WorkflowData | null>(null)
  const [validation, setValidation] = useState<ValidationResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [reviewTab, setReviewTab] = useState<ReviewTab>('json')
  const [saving, setSaving] = useState(false)
  const [showKeyModal, setShowKeyModal] = useState(() => !keyStore.get())
  const [hasKey, setHasKey] = useState(() => Boolean(keyStore.get()))

  const handleFileUpload = async (file: File, context: string) => {
    setError(null)
    setStep('generating')

    try {
      setStatus('Uploading document...')
      const uploaded = await apiClient.uploadFile(file)

      setStatus('Parsing sheets & sections...')
      await apiClient.parseFile(uploaded.file_id)

      setStatus('Classifying policy sections...')
      await new Promise((r) => setTimeout(r, 600))

      setStatus('Extracting rules with Claude AI...')
      const result = await apiClient.generateWorkflow(uploaded.file_id, context)

      setWorkflowId(result.workflow_id)
      setWorkflow(result.workflow)
      setValidation(result.validation)
      setStep('review')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'An unexpected error occurred'
      setError(msg)
      setStep('upload')
    }
  }

  const handleRulesUpdate = async (updated: WorkflowData) => {
    if (!workflowId) return
    setSaving(true)
    try {
      const result = await apiClient.updateWorkflow(workflowId, updated)
      setWorkflow(result.workflow)
      setValidation(result.validation)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to save changes'
      setError(msg)
    } finally {
      setSaving(false)
    }
  }

  const handleExport = () => {
    if (!workflowId) return
    const a = document.createElement('a')
    a.href = `/api/export/${workflowId}`
    a.download = 'workflow.workflow'
    a.click()
  }

  const handleReset = () => {
    setStep('upload')
    setWorkflowId(null)
    setWorkflow(null)
    setValidation(null)
    setError(null)
    setStatus('Uploading document...')
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {showKeyModal && (
        <ApiKeyModal
          onClose={() => {
            setShowKeyModal(false)
            setHasKey(Boolean(keyStore.get()))
          }}
        />
      )}

      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <span className="font-bold text-gray-900 text-lg">Policy Converter</span>
          </div>

          {/* Step indicator */}
          <div className="flex items-center gap-2 text-sm">
            {(['upload', 'generating', 'review'] as Step[]).map((s, i) => (
              <div key={s} className="flex items-center gap-2">
                {i > 0 && <div className="w-8 h-px bg-gray-300" />}
                <div className={`flex items-center gap-1.5 ${step === s ? 'text-indigo-600 font-medium' : step === 'review' && s !== 'review' ? 'text-green-600' : 'text-gray-400'}`}>
                  <div className={`w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold ${step === s ? 'bg-indigo-600 text-white' : step === 'review' && s !== 'review' ? 'bg-green-500 text-white' : 'bg-gray-200 text-gray-500'}`}>
                    {step === 'review' && s !== 'review' ? '✓' : i + 1}
                  </div>
                  <span className="capitalize hidden sm:inline">{s === 'generating' ? 'Processing' : s}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-2">
            {/* API key button */}
            <button
              onClick={() => setShowKeyModal(true)}
              title="Configure Anthropic API key"
              className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border transition ${
                hasKey
                  ? 'border-green-200 bg-green-50 text-green-700 hover:bg-green-100'
                  : 'border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100'
              }`}
            >
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
              {hasKey ? 'API key set' : 'Add API key'}
            </button>

            {step === 'review' && (
              <button onClick={handleReset} className="text-sm text-gray-500 hover:text-gray-700 flex items-center gap-1.5">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                New Document
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main */}
      <main className="max-w-6xl mx-auto px-6 py-10">
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl flex items-start gap-3">
            <svg className="w-5 h-5 text-red-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="font-medium text-red-800">Error</p>
              <p className="text-sm text-red-600 mt-0.5">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* No-key banner */}
        {!hasKey && step === 'upload' && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <svg className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
              </svg>
              <div>
                <p className="font-medium text-amber-800 text-sm">Anthropic API key required</p>
                <p className="text-amber-600 text-xs mt-0.5">
                  Add your key to generate workflows. It stays in your browser only.
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowKeyModal(true)}
              className="shrink-0 px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium rounded-lg transition"
            >
              Add key
            </button>
          </div>
        )}

        {step === 'upload' && <FileUpload onUpload={handleFileUpload} />}
        {step === 'generating' && <ProcessingStatus status={status} />}

        {step === 'review' && workflow && validation && (
          <div className="space-y-6">
            {/* Validation summary */}
            <div className={`p-4 rounded-xl border flex items-center justify-between ${validation.valid ? 'bg-green-50 border-green-200' : 'bg-yellow-50 border-yellow-200'}`}>
              <div className="flex items-center gap-3">
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${validation.valid ? 'bg-green-100' : 'bg-yellow-100'}`}>
                  {validation.valid
                    ? <svg className="w-5 h-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                    : <svg className="w-5 h-5 text-yellow-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" /></svg>
                  }
                </div>
                <div>
                  <p className={`font-semibold text-sm ${validation.valid ? 'text-green-800' : 'text-yellow-800'}`}>
                    {validation.valid ? 'Workflow Valid' : `${validation.errors.length} validation error${validation.errors.length !== 1 ? 's' : ''}`}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {validation.stats.total_nodes} nodes · {validation.stats.total_rules} rules · {validation.stats.inputs} inputs
                    {validation.warnings.length > 0 && ` · ${validation.warnings.length} warning${validation.warnings.length !== 1 ? 's' : ''}`}
                  </p>
                </div>
              </div>
              <button
                onClick={handleExport}
                className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg text-sm font-medium transition"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Export JSON
              </button>
            </div>

            {/* Validation errors/warnings */}
            {(validation.errors.length > 0 || validation.warnings.length > 0) && (
              <div className="space-y-2">
                {validation.errors.map((e, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm text-red-600 bg-red-50 px-3 py-2 rounded-lg">
                    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                    {e}
                  </div>
                ))}
                {validation.warnings.map((w, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm text-yellow-700 bg-yellow-50 px-3 py-2 rounded-lg">
                    <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01" />
                    </svg>
                    {w}
                  </div>
                ))}
              </div>
            )}

            {/* Tab switcher */}
            <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
              <div className="flex border-b border-gray-200">
                {(['json', 'rules'] as ReviewTab[]).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setReviewTab(tab)}
                    className={`px-6 py-3 text-sm font-medium transition border-b-2 -mb-px ${
                      reviewTab === tab
                        ? 'border-indigo-600 text-indigo-600'
                        : 'border-transparent text-gray-500 hover:text-gray-700'
                    }`}
                  >
                    {tab === 'json' ? 'JSON Output' : 'Rule Editor'}
                  </button>
                ))}
              </div>

              <div className="p-6">
                {reviewTab === 'json' && <WorkflowViewer workflow={workflow} />}
                {reviewTab === 'rules' && (
                  <RuleEditor workflow={workflow} saving={saving} onSave={handleRulesUpdate} />
                )}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
