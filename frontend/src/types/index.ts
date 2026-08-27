export interface HealthResponse {
  status: string
  service: string
  version: string
  timestamp: string
}

export interface HomeResponse {
  message: string
  service: string
  version: string
  docs: string
}

export type ConnectionStatus = 'checking' | 'connected' | 'disconnected'

export type DocumentType =
  | 'passport'
  | 'visa'
  | 'national_id'
  | 'driving_license'
  | 'permit'

export interface QualityMetric {
  label: string
}

export interface ResolutionQuality extends QualityMetric {
  width: number
  height: number
}

export interface BrightnessQuality extends QualityMetric {
  value: number
}

export interface BlurQuality extends QualityMetric {
  score: number
}

export interface DocumentQuality {
  resolution: ResolutionQuality
  brightness: BrightnessQuality
  blur: BlurQuality
  ocr_readiness: number
}

export interface UploadResponse {
  success: boolean
  file_id: string
  filename: string
  document_type: string
  file_size: number
  quality: DocumentQuality
}

export interface ApiErrorResponse {
  success?: boolean
  error?: string
  detail?: string | unknown
}

export type UploadPhase = 'idle' | 'uploading' | 'analyzing' | 'complete' | 'error'

export type ScreeningStep = 1 | 2 | 3 | 4
