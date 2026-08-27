import type {
  ApiErrorResponse,
  CaseSummary,
  HealthResponse,
  HomeResponse,
  ScreeningResponse,
  UploadResponse,
} from '../types'

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) throw new Error(`API request failed: ${response.status} ${response.statusText}`)
  return response.json() as Promise<T>
}

async function parseApiError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as ApiErrorResponse
    if (typeof data.detail === 'string') return data.detail
    if (data.detail && typeof data.detail === 'object') {
      const detail = data.detail as ApiErrorResponse
      return detail.detail?.toString() || detail.error || 'Request failed.'
    }
    return data.error || 'Request failed.'
  } catch {
    return `Request failed: ${response.status} ${response.statusText}`
  }
}

async function postJson<T>(path: string, body: any): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(await parseApiError(response))
  return response.json() as Promise<T>
}

async function multipart(path: string, formData: FormData): Promise<any> {
  const response = await fetch(`${API_URL}${path}`, { method: 'POST', body: formData })
  if (!response.ok) throw new Error(await parseApiError(response))
  return response.json()
}

export const api = {
  getHome: () => request<HomeResponse>('/'),
  getHealth: () => request<HealthResponse>('/health'),
  getCases: () => request<{ success: boolean; cases: CaseSummary[] }>('/api/cases'),
  getCaseDetails: (caseId: string) => request<{ success: boolean; case: ScreeningResponse }>(`/api/cases/${case_encode(caseId)}`),
  recordOfficerDecision: (caseId: string, decision: 'APPROVE' | 'REJECT' | 'MANUAL_VERIFICATION', notes?: string, officerId?: string) =>
    postJson<{ success: boolean; message: string; case: ScreeningResponse }>(`/api/cases/${case_encode(caseId)}/decision`, {
      decision,
      notes,
      officer_id: officerId || 'OFFICER-DEMO',
    }),
  uploadDocument: async (
    file: File,
    documentType: string,
    onUploadProgress?: (phase: 'uploading' | 'analyzing') => void
  ): Promise<UploadResponse> => {
    const data = new FormData()
    data.append('file', file)
    data.append('document_type', documentType)
    onUploadProgress?.('uploading')
    const timer = window.setTimeout(() => onUploadProgress?.('analyzing'), 400)
    try {
      return await multipart('/api/upload', data)
    } finally {
      window.clearTimeout(timer)
    }
  },
  screenDocument: async (
    file: File,
    documentType: string,
    selfie?: File | null,
    onUploadProgress?: (phase: 'uploading' | 'analyzing') => void
  ): Promise<ScreeningResponse> => {
    const data = new FormData()
    data.append('file', file)
    data.append('document_type', documentType)
    if (selfie) data.append('selfie', selfie)
    onUploadProgress?.('uploading')
    const timer = window.setTimeout(() => onUploadProgress?.('analyzing'), 400)
    try {
      return (await multipart('/api/screen', data)) as ScreeningResponse
    } finally {
      window.clearTimeout(timer)
    }
  },
}

function case_encode(id: string): string {
  return encodeURIComponent(id)
}

