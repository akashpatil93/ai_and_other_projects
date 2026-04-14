import axios from 'axios'
import type { ValidationResult, WorkflowData } from '../types/workflow'

const LS_KEY = 'anthropic_api_key'

export const keyStore = {
  get: (): string => localStorage.getItem(LS_KEY) ?? '',
  set: (key: string) => localStorage.setItem(LS_KEY, key),
  clear: () => localStorage.removeItem(LS_KEY),
}

const api = axios.create({ baseURL: '' })

// Inject the API key header on every request
api.interceptors.request.use((config) => {
  const key = keyStore.get()
  if (key) config.headers['X-Anthropic-Key'] = key
  return config
})

export const apiClient = {
  async verifyKey(key: string): Promise<{ valid: boolean; masked: string }> {
    const res = await api.post(
      '/api/verify-key',
      {},
      { headers: { 'X-Anthropic-Key': key } },
    )
    return res.data
  },

  async uploadFile(file: File): Promise<{ file_id: string; filename: string; size: number }> {
    const form = new FormData()
    form.append('file', file)
    const res = await api.post('/api/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data
  },

  async parseFile(fileId: string): Promise<{
    parse_id: string
    sections: { name: string; row_count: number; headers: string[] }[]
    section_count: number
  }> {
    const res = await api.post('/api/parse', { file_id: fileId })
    return res.data
  },

  async generateWorkflow(fileId: string, context = '', samplePayload = ''): Promise<{
    workflow_id: string
    workflow: WorkflowData
    validation: ValidationResult
  }> {
    const res = await api.post('/api/generate', { file_id: fileId, context, sample_payload: samplePayload })
    return res.data
  },

  async updateWorkflow(
    workflowId: string,
    workflow: WorkflowData,
  ): Promise<{ workflow_id: string; workflow: WorkflowData; validation: ValidationResult }> {
    const res = await api.put(`/api/workflow/${workflowId}`, { workflow })
    return res.data
  },
}
