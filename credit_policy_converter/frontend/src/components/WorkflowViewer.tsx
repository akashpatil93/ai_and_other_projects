import { useState } from 'react'
import type { WorkflowData } from '../types/workflow'

interface Props {
  workflow: WorkflowData
}

export default function WorkflowViewer({ workflow }: Props) {
  const [copied, setCopied] = useState(false)
  const json = JSON.stringify(workflow, null, 2)

  const handleCopy = () => {
    navigator.clipboard.writeText(json).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-4 text-sm text-gray-500">
          <span>{workflow.nodes.length} nodes</span>
          <span>{workflow.inputs.length} inputs</span>
          <span>{workflow.outputs.length} outputs</span>
        </div>
        <button
          onClick={handleCopy}
          className={`flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg border transition ${
            copied
              ? 'border-green-300 bg-green-50 text-green-700'
              : 'border-gray-200 bg-white text-gray-600 hover:border-gray-300 hover:bg-gray-50'
          }`}
        >
          {copied ? (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Copied!
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy JSON
            </>
          )}
        </button>
      </div>

      {/* Node type summary chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        {Object.entries(
          workflow.nodes.reduce<Record<string, number>>((acc, n) => {
            acc[n.type] = (acc[n.type] ?? 0) + 1
            return acc
          }, {}),
        ).map(([type, count]) => (
          <span
            key={type}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-100"
          >
            {type}
            <span className="bg-indigo-200 text-indigo-800 rounded-full w-4 h-4 flex items-center justify-center text-[10px] font-bold">
              {count}
            </span>
          </span>
        ))}
      </div>

      {/* JSON display */}
      <div className="relative bg-gray-900 rounded-xl overflow-hidden">
        <pre className="p-4 text-xs text-gray-100 overflow-auto max-h-[560px] leading-relaxed font-mono">
          {json.length > 40_000 ? json : <SyntaxHighlight json={json} />}
        </pre>
      </div>
    </div>
  )
}

function SyntaxHighlight({ json }: { json: string }) {
  // Simple tokenizer-based highlighting
  const tokens = tokenize(json)
  return (
    <>
      {tokens.map((t, i) => (
        <span key={i} style={{ color: TOKEN_COLORS[t.type] }}>
          {t.value}
        </span>
      ))}
    </>
  )
}

type TokenType = 'key' | 'string' | 'number' | 'boolean' | 'null' | 'punctuation' | 'whitespace'

const TOKEN_COLORS: Record<TokenType, string> = {
  key: '#7dd3fc',      // sky-300
  string: '#86efac',   // green-300
  number: '#fda4af',   // rose-300
  boolean: '#fbbf24',  // amber-400
  null: '#a78bfa',     // violet-400
  punctuation: '#94a3b8', // slate-400
  whitespace: 'inherit',
}

function tokenize(json: string): { type: TokenType; value: string }[] {
  const result: { type: TokenType; value: string }[] = []
  let i = 0
  let expectKey = false

  while (i < json.length) {
    const ch = json[i]

    if (ch === '{' || ch === '[') {
      result.push({ type: 'punctuation', value: ch })
      expectKey = ch === '{'
      i++
    } else if (ch === '}' || ch === ']') {
      result.push({ type: 'punctuation', value: ch })
      expectKey = false
      i++
    } else if (ch === ':') {
      result.push({ type: 'punctuation', value: ch })
      expectKey = false
      i++
    } else if (ch === ',') {
      result.push({ type: 'punctuation', value: ch })
      // next non-whitespace string inside object is a key
      const peek = json.slice(i + 1).trimStart()
      expectKey = peek.startsWith('"') && !peek.startsWith('"http')
      i++
    } else if (ch === '"') {
      // Read the whole string literal
      let j = i + 1
      while (j < json.length) {
        if (json[j] === '\\') { j += 2; continue }
        if (json[j] === '"') { j++; break }
        j++
      }
      const raw = json.slice(i, j)
      result.push({ type: expectKey ? 'key' : 'string', value: raw })
      expectKey = false
      i = j
    } else if (ch === '-' || (ch >= '0' && ch <= '9')) {
      let j = i + 1
      while (j < json.length && /[\d.eE+\-]/.test(json[j])) j++
      result.push({ type: 'number', value: json.slice(i, j) })
      i = j
    } else if (json.startsWith('true', i) || json.startsWith('false', i)) {
      const v = json.startsWith('true', i) ? 'true' : 'false'
      result.push({ type: 'boolean', value: v })
      i += v.length
    } else if (json.startsWith('null', i)) {
      result.push({ type: 'null', value: 'null' })
      i += 4
    } else {
      // whitespace and anything else
      let j = i + 1
      while (j < json.length && !' \t\n\r{}[],:"\'-0123456789'.includes(json[j]) && !json.startsWith('true', j) && !json.startsWith('false', j) && !json.startsWith('null', j)) j++
      result.push({ type: 'whitespace', value: json.slice(i, j) })
      i = j
    }
  }

  return result
}
