import { useCallback, useState } from 'react'

interface Props {
  onUpload: (file: File) => void
}

const ACCEPTED = ['.xlsx', '.xls', '.pdf', '.docx', '.json', '.csv']

export default function FileUpload({ onUpload }: Props) {
  const [dragging, setDragging] = useState(false)
  const [selected, setSelected] = useState<File | null>(null)

  const pick = useCallback((file: File) => setSelected(file), [])

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
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <div>
              <p className="font-medium text-gray-900 text-sm">{selected.name}</p>
              <p className="text-xs text-gray-400">{(selected.size / 1024).toFixed(1)} KB</p>
            </div>
          </div>
          <button
            onClick={() => onUpload(selected)}
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
