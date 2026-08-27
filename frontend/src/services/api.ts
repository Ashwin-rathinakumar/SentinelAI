import type {
  ApiErrorResponse,
  HealthResponse,
  HomeResponse,
  UploadResponse,
} from '../types'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

async function request<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)

  if (!response.ok) {
    throw new Error(`API request failed: ${response.status} ${response.statusText}`)
  }

  return response.json() as Promise<T>
}

async function parseApiError(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as ApiErrorResponse
    if (typeof data.detail === 'string') {
      return data.detail
    }
    if (typeof data.detail === 'object' && data.detail !== null) {
      const detail = data.detail as ApiErrorResponse
      if (detail.detail && typeof detail.detail === 'string') {
        return detail.detail
      }
      if (detail.error && typeof detail.error === 'string') {
        return detail.error
      }
    }
    if (data.error) {
      return data.error
    }
  } catch {
    // fall through to status text
  }
  return `Upload failed: ${response.status} ${response.statusText}`
}

export const api = {
  getHome: () => request<HomeResponse>('/'),
  getHealth: () => request<HealthResponse>('/health'),

  uploadDocument: async (
    file: File,
    documentType: string,
    onUploadProgress?: (phase: 'uploading' | 'analyzing') => void,
  ): Promise<UploadResponse> => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('document_type', documentType)

    onUploadProgress?.('uploading')

    const progressTimer = window.setTimeout(() => {
      onUploadProgress?.('analyzing')
    }, 600)

    try {
      const response = await fetch(`${API_URL}/api/upload`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const message = await parseApiError(response)
        throw new Error(message)
      }

      return (await response.json()) as UploadResponse
    } finally {
      window.clearTimeout(progressTimer)
    }
  },
}

export { API_URL }
