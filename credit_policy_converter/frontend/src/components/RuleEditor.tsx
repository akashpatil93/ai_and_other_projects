import { useState, useEffect } from 'react'
import type { WorkflowData, WorkflowNode, Rule, Expression, MatrixData, DecisionTableRules } from '../types/workflow'

interface Props {
  workflow: WorkflowData
  saving: boolean
  onSave: (workflow: WorkflowData) => void
}

export default function RuleEditor({ workflow, saving, onSave }: Props) {
  const [local, setLocal] = useState<WorkflowData>(() => deepClone(workflow))
  const [dirty, setDirty] = useState(false)

  useEffect(() => {
    setLocal(deepClone(workflow))
    setDirty(false)
  }, [workflow])

  const updateNode = (nodeIdx: number, updated: WorkflowNode) => {
    setLocal((prev) => {
      const nodes = [...prev.nodes]
      nodes[nodeIdx] = updated
      return { ...prev, nodes }
    })
    setDirty(true)
  }

  const handleSave = () => onSave(local)

  const ruleSets = local.nodes
    .map((n, i) => ({ node: n, idx: i }))
    .filter(({ node }) => node.type === 'ruleSet' || node.type === 'modelSet' || node.type === 'branch')

  if (ruleSets.length === 0) {
    return (
      <div className="text-center py-12 text-gray-400">
        <p>No editable rule sets found in this workflow.</p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Save bar */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          Edit rule conditions inline. Changes are saved when you click <strong>Save Changes</strong>.
        </p>
        <button
          onClick={handleSave}
          disabled={!dirty || saving}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition ${
            dirty && !saving
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white'
              : 'bg-gray-100 text-gray-400 cursor-not-allowed'
          }`}
        >
          {saving ? (
            <>
              <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
              Saving...
            </>
          ) : (
            <>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Save Changes
            </>
          )}
        </button>
      </div>

      {ruleSets.map(({ node, idx }) => (
        <NodeSection
          key={idx}
          node={node}
          nodeIdx={idx}
          onUpdate={updateNode}
        />
      ))}
    </div>
  )
}

function NodeSection({
  node,
  nodeIdx,
  onUpdate,
}: {
  node: WorkflowNode
  nodeIdx: number
  onUpdate: (idx: number, node: WorkflowNode) => void
}) {
  const [expanded, setExpanded] = useState(true)

  const nodeTypeLabel: Record<string, string> = {
    ruleSet: 'Rule Set',
    modelSet: 'Model Set',
    branch: 'Branch',
  }

  const nodeTypeColor: Record<string, string> = {
    ruleSet: 'bg-blue-50 text-blue-700 border-blue-200',
    modelSet: 'bg-purple-50 text-purple-700 border-purple-200',
    branch: 'bg-orange-50 text-orange-700 border-orange-200',
  }

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setExpanded((e) => !e)}
        className="w-full flex items-center justify-between px-5 py-3.5 bg-gray-50 hover:bg-gray-100 transition text-left"
      >
        <div className="flex items-center gap-3">
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${nodeTypeColor[node.type] ?? 'bg-gray-100 text-gray-600 border-gray-200'}`}>
            {nodeTypeLabel[node.type] ?? node.type}
          </span>
          <span className="font-medium text-gray-900 text-sm">{node.name}</span>
          {node.tag && (
            <span className="text-xs text-gray-400">#{node.tag}</span>
          )}
        </div>
        <svg
          className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="divide-y divide-gray-100">
          {node.type === 'ruleSet' && node.rules && (
            <RuleTable
              rules={node.rules}
              onChange={(rules) => onUpdate(nodeIdx, { ...node, rules })}
            />
          )}
          {(node.type === 'modelSet' || node.type === 'branch') && node.expressions && (
            <ExpressionTable
              expressions={node.expressions}
              onChange={(expressions) => onUpdate(nodeIdx, { ...node, expressions })}
            />
          )}
        </div>
      )}
    </div>
  )
}

function RuleTable({
  rules,
  onChange,
}: {
  rules: Rule[]
  onChange: (rules: Rule[]) => void
}) {
  const updateRule = (i: number, field: keyof Rule, value: string) => {
    const updated = [...rules]
    updated[i] = { ...updated[i], [field]: value }
    onChange(updated)
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-gray-50 text-gray-500 uppercase tracking-wide text-[10px]">
            <th className="px-4 py-2 text-left w-8">#</th>
            <th className="px-4 py-2 text-left min-w-[140px]">Rule Name</th>
            <th className="px-4 py-2 text-left">Approve Condition</th>
            <th className="px-4 py-2 text-left">Can't Decide Condition</th>
            <th className="px-4 py-2 text-left w-24">Tag</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {rules.map((rule, i) => (
            <tr key={rule.id} className="hover:bg-gray-50">
              <td className="px-4 py-2 text-gray-400">{rule.seqNo}</td>
              <td className="px-4 py-2">
                <input
                  className="w-full bg-transparent border-0 outline-none focus:ring-1 focus:ring-indigo-300 rounded px-1 py-0.5 font-medium text-gray-800"
                  value={rule.name}
                  onChange={(e) => updateRule(i, 'name', e.target.value)}
                />
              </td>
              <td className="px-4 py-2">
                <textarea
                  rows={2}
                  className="w-full bg-transparent border border-gray-200 rounded px-2 py-1 font-mono text-[11px] text-gray-700 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-300 focus:border-indigo-300"
                  value={rule.approveCondition}
                  onChange={(e) => updateRule(i, 'approveCondition', e.target.value)}
                />
              </td>
              <td className="px-4 py-2">
                <textarea
                  rows={2}
                  className="w-full bg-transparent border border-gray-200 rounded px-2 py-1 font-mono text-[11px] text-gray-500 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-300 focus:border-indigo-300"
                  value={rule.cantDecideCondition}
                  onChange={(e) => updateRule(i, 'cantDecideCondition', e.target.value)}
                />
              </td>
              <td className="px-4 py-2">
                <input
                  className="w-full bg-transparent border-0 outline-none text-gray-400 focus:ring-1 focus:ring-indigo-300 rounded px-1 py-0.5"
                  value={rule.tag}
                  onChange={(e) => updateRule(i, 'tag', e.target.value)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const EXPR_TYPE_STYLE: Record<string, string> = {
  expression: 'bg-sky-50 text-sky-700 border-sky-100',
  decisionTable: 'bg-amber-50 text-amber-700 border-amber-100',
  matrix: 'bg-emerald-50 text-emerald-700 border-emerald-100',
}

function ExpressionTable({
  expressions,
  onChange,
}: {
  expressions: Expression[]
  onChange: (expressions: Expression[]) => void
}) {
  const updateExpr = (i: number, field: keyof Expression, value: string) => {
    const updated = [...expressions]
    updated[i] = { ...updated[i], [field]: value }
    onChange(updated)
  }

  return (
    <div className="divide-y divide-gray-100">
      {expressions.map((expr, i) => (
        <div key={expr.id} className="px-5 py-4 hover:bg-gray-50">
          {/* Row header */}
          <div className="flex items-center gap-3 mb-2">
            <span className="text-xs text-gray-400 w-5 shrink-0">{expr.seqNo}</span>
            <input
              className="font-medium text-sm text-gray-900 bg-transparent border-0 outline-none focus:ring-1 focus:ring-indigo-300 rounded px-1"
              value={expr.name}
              onChange={(e) => updateExpr(i, 'name', e.target.value)}
            />
            <span className={`ml-auto text-[10px] font-semibold px-2 py-0.5 rounded-full border ${EXPR_TYPE_STYLE[expr.type] ?? 'bg-gray-100 text-gray-600 border-gray-200'}`}>
              {expr.type}
            </span>
          </div>

          {/* expression: editable condition */}
          {expr.type === 'expression' && (
            <textarea
              rows={2}
              placeholder="condition expression"
              className="w-full ml-8 bg-white border border-gray-200 rounded px-2 py-1 font-mono text-[11px] text-gray-700 resize-none focus:outline-none focus:ring-1 focus:ring-indigo-300"
              value={expr.condition}
              onChange={(e) => updateExpr(i, 'condition', e.target.value)}
            />
          )}

          {/* decisionTable: preview */}
          {expr.type === 'decisionTable' && expr.decisionTableRules?.rows && (
            <DecisionTablePreview dt={expr.decisionTableRules} />
          )}

          {/* matrix: preview */}
          {expr.type === 'matrix' && expr.matrix?.rows && (
            <MatrixPreview matrix={expr.matrix} />
          )}
        </div>
      ))}
    </div>
  )
}

function DecisionTablePreview({ dt }: { dt: DecisionTableRules }) {
  if (!dt.rows || !dt.headers) return null
  const headers = dt.headers
  return (
    <div className="ml-8 mt-1 overflow-x-auto">
      <table className="text-[10px] border border-gray-200 rounded">
        <thead>
          <tr className="bg-amber-50">
            <th className="px-2 py-1 text-left text-gray-500 font-semibold">Sl.</th>
            {headers.map((h) => (
              <th key={h} className="px-2 py-1 text-left text-amber-700 font-semibold font-mono">{h}</th>
            ))}
            <th className="px-2 py-1 text-left text-gray-500 font-semibold">Output</th>
          </tr>
          {dt.default !== '' && (
            <tr className="bg-gray-50 border-b border-gray-200">
              <td className="px-2 py-0.5 text-gray-400 italic" colSpan={headers.length + 1}>default</td>
              <td className="px-2 py-0.5 font-mono text-gray-700">{dt.default}</td>
            </tr>
          )}
        </thead>
        <tbody className="divide-y divide-gray-100">
          {dt.rows.map((row, ri) => (
            <tr key={ri} className="hover:bg-amber-50/40">
              <td className="px-2 py-1 text-gray-400">{ri + 1}</td>
              {row.columns.map((col) => (
                <td key={col.name} className="px-2 py-1 font-mono text-gray-700">{col.value}</td>
              ))}
              <td className="px-2 py-1 font-mono font-semibold text-amber-800">{row.output}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function MatrixPreview({ matrix }: { matrix: MatrixData }) {
  if (!matrix.rows || !matrix.columns || !matrix.values) return null

  const colCount = matrix.columns.reduce((s, c) => s + c.conditions.length, 0)
  const rowDefs = matrix.rows

  return (
    <div className="ml-8 mt-1 overflow-x-auto">
      <table className="text-[10px] border border-gray-200 rounded">
        <thead>
          <tr className="bg-emerald-50">
            {/* top-left corner: row variable header */}
            <th className="px-2 py-1 text-left text-gray-400 font-semibold border-r border-gray-200">
              {matrix.rows.find((r) => !r.isNoMatches)?.header ?? ''}
            </th>
            {/* column variable header spanning all cols */}
            <th
              className="px-2 py-1 text-center text-emerald-700 font-semibold"
              colSpan={colCount}
            >
              {matrix.columns.find((c) => !c.isNoMatches)?.header ?? ''}
            </th>
          </tr>
          <tr className="bg-emerald-50/50 border-b border-gray-200">
            <th className="px-2 py-1 border-r border-gray-200" />
            {matrix.columns.map((col) =>
              col.conditions.map((cond) => (
                <th key={`${col.index}-${cond.index}`} className="px-2 py-1 font-mono text-gray-600 font-medium">
                  {cond.condition}
                </th>
              ))
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {rowDefs.map((row, ri) => (
            <tr key={ri} className={row.isNoMatches ? 'bg-gray-50' : 'hover:bg-emerald-50/30'}>
              {row.conditions.map((cond, ci) =>
                ci === 0 ? (
                  <td key={ci} className="px-2 py-1 font-mono text-gray-600 border-r border-gray-200 bg-emerald-50/50">
                    {cond.condition}
                  </td>
                ) : null
              )}
              {(matrix.values?.[ri] ?? []).map((val, vi) => (
                <td key={vi} className="px-2 py-1 font-mono text-center font-semibold text-emerald-800">
                  {val}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}
