export interface WorkflowData {
  nodes: WorkflowNode[]
  inputs: InputVariable[]
  outputs: OutputVariable[]
  settings: Record<string, unknown>
}

export interface WorkflowNode {
  type: 'start' | 'dataSource' | 'modelSet' | 'ruleSet' | 'switch' | 'branch' | 'end'
  name: string
  tag?: string
  metadata?: { x: number; y: number; nodeColor?: number }
  nextState?: { name: string; type: string }
  // ruleSet
  rules?: Rule[]
  // modelSet / branch
  expressions?: Expression[]
  // dataSource
  sources?: DataSource[]
  // switch
  dataConditions?: DataCondition[]
  // end
  endNodeName?: string
  decisionNode?: { output: string }
}

export interface Rule {
  name: string
  id: string
  seqNo: number
  approveCondition: string
  cantDecideCondition: string
  tag: string
}

export type ExpressionType = 'expression' | 'decisionTable' | 'matrix'

export interface Expression {
  name: string
  id: string
  seqNo: number
  condition: string
  type: ExpressionType
  tag: string
  // Always present — populated for decisionTable, nulled-out for others
  decisionTableRules: DecisionTableRules
  // Always present — populated for matrix, nulled-out for others
  matrix: MatrixData
}

export interface DecisionTableRules {
  default: string
  headers: string[] | null
  rows: DecisionTableRow[] | null
}

export interface DecisionTableRow {
  columns: { name: string; value: string }[]
  output: string
}

export interface MatrixData {
  globalRowIndex: number
  globalColumnIndex: number
  rows: MatrixAxis[] | null
  columns: MatrixAxis[] | null
  values: string[][] | null
}

export interface MatrixAxis {
  header: string
  index: number
  isNoMatches?: boolean
  conditions: { index: number; condition: string; child: null }[]
}

export interface DataSource {
  name: string
  id: number
  seqNo: number
  type: string
  tag: string
}

export interface DataCondition {
  name: string
  nextState: { name: string; type: string }
}

export interface InputVariable {
  id: string
  name: string
  dataType: 'number' | 'text'
  isNullable: boolean
  defaultInput: string
  is_array: boolean
  schema: null
}

export interface OutputVariable {
  name: string
  dataType: string
}

export interface ValidationResult {
  valid: boolean
  errors: string[]
  warnings: string[]
  stats: {
    total_nodes: number
    node_types: Record<string, number>
    rule_sets: number
    total_rules: number
    inputs: number
  }
}
