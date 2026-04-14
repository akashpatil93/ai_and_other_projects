import { useCallback, useState } from 'react'

interface Props {
  onUpload: (file: File, context: string, samplePayload: string) => void
}

const ACCEPTED = ['.xlsx', '.xls', '.pdf', '.docx', '.json', '.csv']

export default function FileUpload({ onUpload }: Props) {
  const [dragging, setDragging] = useState(false)
  const [selected, setSelected] = useState<File | null>(null)
  const [context, setContext] = useState('')
  const [samplePayload, setSamplePayload] = useState('')
  const [samplePayloadFile, setSamplePayloadFile] = useState<File | null>(null)
  const [samplePayloadTab, setSamplePayloadTab] = useState<'paste' | 'file'>('paste')
  const [samplePayloadError, setSamplePayloadError] = useState<string | null>(null)

  const pick = useCallback((file: File) => setSelected(file), [])

  const validateJson = (text: string): boolean => {
    if (!text.trim()) return true
    try { JSON.parse(text); return true } catch { return false }
  }

  const handleSampleFileChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (!f) return
    setSamplePayloadFile(f)
    setSamplePayloadError(null)
    const reader = new FileReader()
    reader.onload = (ev) => {
      const text = ev.target?.result as string
      if (!validateJson(text)) {
        setSamplePayloadError('File is not valid JSON.')
      } else {
        setSamplePayload(text)
      }
    }
    reader.readAsText(f)
  }, [])

  const handleSubmit = () => {
    if (!selected) return
    if (samplePayload.trim() && !validateJson(samplePayload)) {
      setSamplePayloadError('Pasted text is not valid JSON.')
      return
    }
    onUpload(selected, context, samplePayload.trim())
  }

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const f = e.dataTransfer.files[0]
      if (f) pick(f)
    },
    [pick],
  )

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const f = e.target.files?.[0]
      if (f) pick(f)
    },
    [pick],
  )

  return (
    <div className="max-w-2xl mx-auto">
      <div className="text-center mb-8">
        <h2 className="text-2xl font-bold text-gray-900">Upload Policy Document</h2>
        <p className="text-gray-500 mt-2">
          Drop your credit policy document below. Claude AI will extract the rules and
          generate a workflow JSON ready for your BRE platform.
        </p>
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-2xl p-12 text-center transition-colors ${
          dragging
            ? 'border-indigo-500 bg-indigo-50'
            : 'border-gray-300 bg-white hover:border-indigo-400 hover:bg-gray-50'
        }`}
      >
        <div className="flex justify-center mb-4">
          <svg
            className="w-14 h-14 text-gray-300"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>

        <p className="text-gray-600 mb-3">Drag and drop your policy document here, or</p>

        <label className="cursor-pointer">
          <span className="inline-block bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2.5 rounded-lg font-medium text-sm transition">
            Browse Files
          </span>
          <input
            type="file"
            accept={ACCEPTED.join(',')}
            onChange={handleChange}
            className="hidden"
          />
        </label>

        <p className="text-xs text-gray-400 mt-4">Supported: {ACCEPTED.join(', ')}</p>
      </div>

      {/* Context input */}
      <div className="mt-6">
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Additional context
          <span className="ml-1.5 font-normal text-gray-400">(optional)</span>
        </label>
        <textarea
          value={context}
          onChange={(e) => setContext(e.target.value)}
          rows={4}
          placeholder={
            'Describe any specifics the AI should follow when building the workflow.\n' +
            'e.g. "This is a personal loan policy for salaried customers. ' +
            'DPD threshold for rejection is 30+ in last 12 months. ' +
            'Bureau score must be ≥ 700 for CIBIL HIT cases."'
          }
          className="w-full rounded-xl border border-gray-300 bg-white px-4 py-3 text-sm text-gray-800 placeholder-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none"
        />
        <p className="mt-1.5 text-xs text-gray-400">
          This context is passed directly to Claude alongside your document to guide rule extraction.
        </p>
      </div>

      {/* Sample payload */}
      <div className="mt-6">
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Sample input payload
          <span className="ml-1.5 font-normal text-gray-400">(optional — populates input schemas)</span>
        </label>

        {/* Tab switcher */}
        <div className="flex border border-gray-200 rounded-lg overflow-hidden w-fit mb-2">
          {(['paste', 'file'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => { setSamplePayloadTab(t); setSamplePayloadError(null) }}
              className={`px-4 py-1.5 text-xs font-medium transition ${
                samplePayloadTab === t
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white text-gray-500 hover:text-gray-700'
              }`}
            >
              {t === 'paste' ? 'Paste JSON' : 'Upload file'}
            </button>
          ))}
        </div>

        {samplePayloadTab === 'paste' ? (
          <textarea
            value={samplePayload}
            onChange={(e) => { setSamplePayload(e.target.value); setSamplePayloadError(null) }}
            rows={5}
            placeholder={'{\n  "applicants": [{"age": 30, "income": 60000}],\n  "bank": {"abb": 45000}\n}'}
            className={`w-full rounded-xl border px-4 py-3 text-sm font-mono text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-1 resize-none ${
              samplePayloadError
                ? 'border-red-400 focus:border-red-400 focus:ring-red-400'
                : 'border-gray-300 focus:border-indigo-500 focus:ring-indigo-500'
            }`}
          />
        ) : (
          <div className="flex items-center gap-3">
            <label className="cursor-pointer flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-600 hover:border-indigo-400 bg-white transition">
              <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
              </svg>
              {samplePayloadFile ? samplePayloadFile.name : 'Choose JSON file'}
              <input type="file" accept=".json" onChange={handleSampleFileChange} className="hidden" />
            </label>
            {samplePayloadFile && (
              <span className="text-xs text-gray-400">{(samplePayloadFile.size / 1024).toFixed(1)} KB</span>
            )}
          </div>
        )}

        {samplePayloadError && (
          <p className="mt-1 text-xs text-red-500">{samplePayloadError}</p>
        )}
        <p className="mt-1.5 text-xs text-gray-400">
          A representative API input payload. Used to populate the <code>schema</code> field on object inputs in the generated workflow.
        </p>
      </div>

      {/* Selected file + action */}
      {selected && (
        <div className="mt-4 p-4 bg-white border border-gray-200 rounded-xl flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center shrink-0">
              <svg
                className="w-5 h-5 text-indigo-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.293.707l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <div>
              <p className="font-medium text-gray-900 text-sm">{selected.name}</p>
              <p className="text-xs text-gray-400">{(selected.size / 1024).toFixed(1)} KB</p>
            </div>
          </div>
          <button
            onClick={handleSubmit}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2 rounded-lg font-medium text-sm transition flex items-center gap-2"
          >
            Generate Workflow
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 7l5 5m0 0l-5 5m5-5H6"
              />
            </svg>
          </button>
        </div>
      )}

      {/* Feature callouts */}
      <div className="grid grid-cols-3 gap-4 mt-10">
        {[
          {
            icon: '📋',
            title: 'Policy Rules',
            desc: 'Extracts Go/No-Go and surrogate policy rules from any format',
          },
          {
            icon: '🤖',
            title: 'AI-Powered',
            desc: 'Claude AI interprets natural language and converts to expressions',
          },
          {
            icon: '⚡',
            title: 'Export-Ready JSON',
            desc: 'Generates workflow JSON matching your BRE platform schema',
          },
        ].map((c) => (
          <div key={c.title} className="bg-white rounded-xl p-4 border text-center">
            <div className="text-2xl mb-2">{c.icon}</div>
            <h3 className="font-semibold text-gray-900 text-sm">{c.title}</h3>
            <p className="text-xs text-gray-500 mt-1">{c.desc}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
