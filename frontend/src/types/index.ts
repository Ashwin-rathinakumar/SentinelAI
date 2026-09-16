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
export type DocumentType = 'aadhaar' | 'unknown' | 'passport' | 'visa' | 'national_id' | 'driving_license' | 'permit'

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

export interface FieldItem {
  raw?: string | null
  normalized?: string | null
  status?: string
}

export interface OCRResult {
  status: string
  raw_text: string
  confidence: number | null
  fields: Record<string, FieldItem>
  mrz: Record<string, any> | null
  warnings?: string[]
}

export interface MRZData {
  applicable?: boolean
  format?: string
  raw_lines?: string[]
  mrz_detected: boolean
  mrz_valid: boolean
  status: string
  checks?: Record<string, boolean>
  mrz_errors?: string[]
  document_code?: FieldItem
  issuing_country?: FieldItem
  surname?: FieldItem
  given_names?: FieldItem
  full_name?: FieldItem
  passport_number?: FieldItem
  nationality?: FieldItem
  date_of_birth?: FieldItem
  sex?: FieldItem
  date_of_expiry?: FieldItem
  optional_data?: FieldItem
}

export interface ValidationResult {
  valid: boolean
  status: 'VALID' | 'REVIEW' | 'INVALID'
  reason_codes: string[]
  messages: string[]
  consistency: Record<string, string>
}

export interface ForensicIndicator {
  type: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH'
  description: string
}

export interface ForensicResult {
  tamper_status?: string
  recompression_detected?: boolean
  content_tamper_detected?: boolean
  tamper_risk: 'LOW' | 'MEDIUM' | 'HIGH'
  score: number
  indicators: ForensicIndicator[]
}

export interface FaceResult {
  face_detected_document: boolean
  face_detected_selfie: boolean
  image_quality: string
  similarity: number | null
  match: boolean | null
  status: 'MATCH' | 'MISMATCH' | 'NOT_PROVIDED' | 'UNABLE_TO_VERIFY' | 'FAILED'
  reason: string
  document_face_crop?: string | null
  selfie_face_crop?: string | null
  model?: string
  threshold?: number | null
}

export interface DatabaseResult {
  found: boolean
  status: string
  blacklisted: boolean
  source: string
  note: string
  record?: {
    document_number?: string
    full_name?: string
    date_of_birth?: string
    nationality?: string
    date_of_expiry?: string
    registered_status?: string
  }
  field_matches?: Record<string, string>
  duplicate_identity?: boolean
  matched_person_id?: number | null
  duplicate_reason?: string | null
}

export interface RiskReason {
  code: string
  points: number
  severity: string
  description: string
}

export interface RiskResult {
  risk_score: number
  risk_level: 'LOW RISK' | 'MEDIUM RISK' | 'HIGH PRIORITY REVIEW' | 'CRITICAL'
  recommendation: string
  reasons: RiskReason[]
}

export interface OfficerDecision {
  decision: 'APPROVE' | 'REJECT' | 'MANUAL_VERIFICATION'
  notes?: string | null
  officer_id: string
  timestamp: string
}

export interface ScreeningResponse {
  blockchain_audit?: Partial<BlockchainAuditRecord> | null
  document?: { type: string; signals: string[] }
  expiry?: { applicable: boolean; status: string }
  qr?: { status: string }
  success: boolean
  case_id: string
  timestamp: string
  file_id: string
  document_type: string
  filename: string
  officer_id?: string
  quality: DocumentQuality
  ocr: OCRResult
  mrz: MRZData
  validation: ValidationResult
  tamper: ForensicResult
  face: FaceResult
  database: DatabaseResult
  risk: RiskResult
  officer_decision?: OfficerDecision | null
}

export type BlockchainAuditStatus = 'NOT_ANCHORED' | 'PENDING' | 'ANCHORED' | 'VERIFIED' | 'TAMPER_DETECTED' | 'CHAIN_UNAVAILABLE' | 'FAILED'
export interface BlockchainAuditRecord {
  id: number
  record_type: 'SCREENING_RESULT' | 'OFFICER_DECISION'
  version: number
  status: BlockchainAuditStatus
  transaction_hash: string | null
  block_number: number | null
  chain_id: number
  contract_address: string
  anchored_at: string | null
  last_verified_at: string | null
  error_message: string | null
}
export interface IntegrityVerificationResult extends Partial<BlockchainAuditRecord> {
  status: BlockchainAuditStatus
  digest_match?: boolean | null
}
export interface BlockchainNetworkStatus {
  enabled: boolean
  rpc_reachable: boolean
  contract_reachable: boolean
  chain_id: number | null
  contract_address: string | null
}

export interface CaseSummary {
  case_id: string
  timestamp: string
  document_type: string
  document_number: string
  holder_name?: string
  validation?: string
  risk?: {
    risk_score: number
    risk_level: string
    recommendation: string
  }
  officer_decision?: OfficerDecision | null
}

export interface ApiErrorResponse {
  success?: boolean
  error?: string
  detail?: string | unknown
}

export type UploadPhase = 'idle' | 'uploading' | 'analyzing' | 'complete' | 'error'
export type ScreeningStep = 1 | 2 | 3 | 4

