import { useState, useRef } from 'react'
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Database,
  FileCheck,
  FileSearch,
  Fingerprint,
  RefreshCw,
  Shield,
  ShieldAlert,
  ShieldCheck,
  User,
  UserCheck,
  XCircle,
} from 'lucide-react'
import { DocumentTypeSelector } from '../components/DocumentTypeSelector'
import { QualityCheckCard } from '../components/QualityCheckCard'
import { ScreeningStepper } from '../components/ScreeningStepper'
import { UploadDropzone } from '../components/UploadDropzone'
import { api } from '../services/api'
import type { DocumentType, ScreeningResponse, ScreeningStep, UploadPhase } from '../types'
import './NewScreeningPage.css'

const fieldLabels: Record<string, string> = {
  full_name: 'Full Name',
  surname: 'Surname',
  given_names: 'Given Names',
  passport_number: 'Document Number',
  nationality: 'Nationality',
  date_of_birth: 'Date of Birth',
  gender: 'Sex / Gender',
  date_of_issue: 'Date of Issue',
  date_of_expiry: 'Date of Expiry',
  issuing_country: 'Issuing Authority / Country',
  place_of_birth: 'Place of Birth',
}

export function NewScreeningPage() {
  const [documentType, setDocumentType] = useState<DocumentType | null>('passport')
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [selfie, setSelfie] = useState<File | null>(null)
  const [phase, setPhase] = useState<UploadPhase>('idle')
  const [result, setResult] = useState<ScreeningResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [officerNotes, setOfficerNotes] = useState('')
  const [decisionSaving, setDecisionSaving] = useState(false)
  const [decisionMessage, setDecisionMessage] = useState<string | null>(null)
  const selfieInputRef = useRef<HTMLInputElement>(null)

  const selected = documentType !== null
  const complete = phase === 'complete' && !!result
  const currentStep: ScreeningStep = complete ? 3 : selected ? 2 : 1

  const handleScreen = async () => {
    if (!selectedFile || !documentType) return
    setError(null)
    setResult(null)
    setDecisionMessage(null)
    setPhase('uploading')
    try {
      const data = await api.screenDocument(selectedFile, documentType, selfie, (p) => setPhase(p))
      setResult(data)
      setPhase('complete')
    } catch (e) {
      setPhase('error')
      setError(e instanceof Error ? e.message : 'Screening failed. Please try again.')
    }
  }

  const handleOfficerDecision = async (decision: 'APPROVE' | 'REJECT' | 'MANUAL_VERIFICATION') => {
    if (!result) return
    setDecisionSaving(true)
    setDecisionMessage(null)
    try {
      const resp = await api.recordOfficerDecision(result.case_id, decision, officerNotes)
      setResult(resp.case)
      setDecisionMessage(`Decision '${decision}' successfully recorded in audit log.`)
    } catch (err) {
      setDecisionMessage(err instanceof Error ? err.message : 'Failed to record officer decision.')
    } finally {
      setDecisionSaving(false)
    }
  }

  const handleReset = () => {
    setSelectedFile(null)
    setSelfie(null)
    setResult(null)
    setPhase('idle')
    setError(null)
    setOfficerNotes('')
    setDecisionMessage(null)
    if (selfieInputRef.current) selfieInputRef.current.value = ''
  }

  const getRiskBadgeClass = (level: string) => {
    if (level.includes('HIGH')) return 'risk-badge-high'
    if (level.includes('MEDIUM')) return 'risk-badge-medium'
    return 'risk-badge-low'
  }

  return (
    <div className="screening-page">
      <ScreeningStepper currentStep={currentStep} documentTypeSelected={selected} uploadComplete={complete} />

      {!result && (
        <>
          <div className="screening-config-panel">
            <DocumentTypeSelector
              selected={documentType}
              onSelect={(type) => {
                setDocumentType(type)
                setResult(null)
              }}
            />

            <UploadDropzone
              disabled={!selected}
              uploadPhase={phase}
              selectedFile={selectedFile}
              onFileSelect={(file) => {
                setSelectedFile(file)
                setResult(null)
                setPhase('idle')
                setError(null)
              }}
              onUpload={() => void handleScreen()}
              error={error}
            />

            {selected && (
              <div className="biometric-upload-card">
                <div className="biometric-header">
                  <Fingerprint size={20} className="text-accent" />
                  <div>
                    <h4>Live Selfie Biometric Verification (Optional)</h4>
                    <p>Upload a webcam capture or portrait selfie to perform 1:1 facial biometric cross-matching.</p>
                  </div>
                </div>
                <div className="biometric-file-row">
                  <input
                    ref={selfieInputRef}
                    type="file"
                    accept="image/*"
                    id="selfie-upload"
                    className="selfie-file-input"
                    onChange={(e) => setSelfie(e.target.files?.[0] ?? null)}
                  />
                  <label htmlFor="selfie-upload" className="selfie-upload-btn">
                    {selfie ? `Selected: ${selfie.name}` : 'Browse Selfie Image…'}
                  </label>
                  {selfie && (
                    <button
                      type="button"
                      className="clear-btn"
                      onClick={() => {
                        setSelfie(null)
                        if (selfieInputRef.current) selfieInputRef.current.value = ''
                      }}
                    >
                      Remove
                    </button>
                  )}
                </div>
              </div>
            )}

            <div className="screening-actions">
              <button
                type="button"
                className="next-step-btn"
                disabled={!selectedFile || phase === 'uploading' || phase === 'analyzing'}
                onClick={() => void handleScreen()}
              >
                {phase === 'analyzing' ? (
                  <>
                    <RefreshCw size={18} className="spin-icon" /> Analyzing Document & MRZ…
                  </>
                ) : phase === 'uploading' ? (
                  <>
                    <RefreshCw size={18} className="spin-icon" /> Uploading Capture…
                  </>
                ) : (
                  <>
                    Run Complete Automated Screening <ArrowRight size={18} />
                  </>
                )}
              </button>
            </div>
          </div>
        </>
      )}

      {result && (
        <div className="screening-results-dashboard">
          {/* Action header */}
          <div className="results-top-bar">
            <div>
              <span className="case-badge">CASE ID: {result.case_id}</span>
              <span className="timestamp-badge">{new Date(result.timestamp).toLocaleString()}</span>
            </div>
            <button type="button" className="btn-secondary" onClick={handleReset}>
              <RefreshCw size={16} /> Screen Another Document
            </button>
          </div>

          {/* 1. Executive Risk Banner */}
          <section className={`executive-risk-banner ${getRiskBadgeClass(result.risk.risk_level)}`}>
            <div className="banner-left">
              <div className="risk-level-tag">
                {result.risk.risk_level.includes('HIGH') ? (
                  <ShieldAlert size={28} />
                ) : result.risk.risk_level.includes('MEDIUM') ? (
                  <AlertTriangle size={28} />
                ) : (
                  <ShieldCheck size={28} />
                )}
                <div>
                  <span className="eyebrow">AUTOMATED SCREENING ASSESSMENT</span>
                  <h2>{result.risk.risk_level}</h2>
                </div>
              </div>
              <p className="recommendation-text">
                <b>RECOMMENDATION:</b> {result.risk.recommendation.replaceAll('_', ' ')}
              </p>
            </div>
            <div className="banner-score">
              <div className="score-circle">
                <span className="score-num">{result.risk.risk_score}</span>
                <span className="score-denom">/ 100</span>
              </div>
              <span className="score-caption">Composite Risk Score</span>
            </div>
          </section>

          {/* 2. Quality & Image Readiness */}
          <QualityCheckCard quality={result.quality} />

          {/* 3. Grid: Extracted Info & MRZ Inspection */}
          <div className="dashboard-grid-two">
            {/* Extracted Information Card */}
            <div className="result-card">
              <div className="card-header">
                <FileTextIcon size={20} className="card-icon" />
                <div>
                  <h3>Extracted Document Information</h3>
                  <p className="card-subtitle">Visual Inspection Zone (VIZ) OCR extraction</p>
                </div>
                <span className="badge-confidence">
                  OCR Conf: {result.ocr.confidence !== null ? `${result.ocr.confidence}%` : 'N/A'}
                </span>
              </div>
              <div className="field-table">
                {Object.entries(fieldLabels).map(([key, label]) => {
                  const item = result.ocr.fields[key]
                  const val = item?.normalized || item?.raw
                  const status = item?.status || 'NOT_DETECTED'
                  return (
                    <div key={key} className="field-row">
                      <span className="field-label">{label}</span>
                      <div className="field-value-group">
                        <span className={`field-value ${!val ? 'val-missing' : ''}`}>
                          {val || 'Not Detected'}
                        </span>
                        {status === 'DETECTED' && <span className="status-pill pill-detected">✓ Extracted</span>}
                        {status === 'REQUIRED_MISSING' && (
                          <span className="status-pill pill-required">Missing (Required)</span>
                        )}
                        {status === 'OPTIONAL_MISSING' && (
                          <span className="status-pill pill-optional">Optional</span>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* MRZ & Check Digit Inspection Card */}
            <div className="result-card">
              <div className="card-header">
                <FileSearch size={20} className="card-icon" />
                <div>
                  <h3>ICAO 9303 MRZ Verification</h3>
                  <p className="card-subtitle">
                    {result.mrz.format ? `${result.mrz.format} Machine-Readable Zone` : 'MRZ Check'}
                  </p>
                </div>
                <span className={`status-pill ${result.mrz.mrz_valid ? 'pill-pass' : 'pill-fail'}`}>
                  {result.mrz.mrz_valid ? '✓ MRZ VALID' : result.mrz.mrz_detected ? '✕ MRZ INVALID' : 'NOT DETECTED'}
                </span>
              </div>

              {result.mrz.mrz_detected && result.mrz.raw_lines && (
                <div className="mrz-box">
                  <span className="mrz-label">Raw MRZ Lines:</span>
                  <pre className="mrz-raw">{result.mrz.raw_lines.join('\n')}</pre>
                </div>
              )}

              {/* Check digits breakdown */}
              {result.mrz.checks && Object.keys(result.mrz.checks).length > 0 && (
                <div className="checks-subpanel">
                  <h4>Check Digits & Math Validation</h4>
                  <div className="checks-chips-grid">
                    {Object.entries(result.mrz.checks).map(([checkKey, passed]) => (
                      <div key={checkKey} className={`check-chip ${passed ? 'chip-pass' : 'chip-fail'}`}>
                        {passed ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                        <span>{checkKey.replace('_', ' ').toUpperCase()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* OCR vs MRZ Cross-Check Table */}
              <div className="consistency-subpanel">
                <h4>Visual Zone (OCR) vs MRZ Consistency</h4>
                <div className="consistency-table">
                  {Object.entries(result.validation.consistency).map(([key, matchStatus]) => (
                    <div key={key} className="consistency-row">
                      <span className="consistency-field">{key.replace('_', ' ').toUpperCase()}</span>
                      <span
                        className={`match-badge ${
                          matchStatus === 'MATCH'
                            ? 'match-ok'
                            : matchStatus === 'MISMATCH'
                            ? 'match-bad'
                            : 'match-na'
                        }`}
                      >
                        {matchStatus === 'MATCH' ? '✓ MATCH' : matchStatus === 'MISMATCH' ? '✕ CONFLICT' : 'N/A'}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 4. Grid: Biometrics, Database & Forensics */}
          <div className="dashboard-grid-three">
            {/* Biometric Face Verification */}
            <div className="result-card">
              <div className="card-header">
                <User size={20} className="card-icon" />
                <div>
                  <h3>Face Verification</h3>
                  <p className="card-subtitle">1:1 Biometric Cross-Match</p>
                </div>
              </div>

              <div className="face-preview-row">
                <div className="face-box">
                  <span className="face-label">Document Photo</span>
                  {result.face.document_face_crop ? (
                    <img src={result.face.document_face_crop} alt="Document face" className="face-img" />
                  ) : (
                    <div className="face-placeholder">
                      <User size={36} />
                      <span>{result.face.face_detected_document ? 'Detected' : 'Not detected'}</span>
                    </div>
                  )}
                </div>

                <div className="face-vs-divider">
                  <span className="vs-badge">VS</span>
                  <div className="sim-gauge">
                    <span className="sim-val">
                      {result.face.similarity !== null ? `${Math.round(result.face.similarity * 100)}%` : '—'}
                    </span>
                    <span className="sim-label">Similarity</span>
                  </div>
                </div>

                <div className="face-box">
                  <span className="face-label">Live Selfie</span>
                  {result.face.selfie_face_crop ? (
                    <img src={result.face.selfie_face_crop} alt="Selfie face" className="face-img" />
                  ) : (
                    <div className="face-placeholder">
                      <User size={36} />
                      <span>{result.face.face_detected_selfie ? 'Detected' : 'No Selfie'}</span>
                    </div>
                  )}
                </div>
              </div>

              <div className="card-footer-status">
                <span
                  className={`status-pill ${
                    result.face.status === 'MATCH'
                      ? 'pill-pass'
                      : result.face.status === 'MISMATCH'
                      ? 'pill-fail'
                      : 'pill-neutral'
                  }`}
                >
                  STATUS: {result.face.status}
                </span>
                <p className="status-note">{result.face.reason}</p>
              </div>
            </div>

            {/* Synthetic Database Verification */}
            <div className="result-card">
              <div className="card-header">
                <Database size={20} className="card-icon" />
                <div>
                  <h3>Registry Database</h3>
                  <p className="card-subtitle">Immigration Watchlist & Verification</p>
                </div>
              </div>

              <div className="db-details-box">
                <div className="db-row">
                  <span className="db-key">Registry Lookup:</span>
                  <span
                    className={`status-pill ${
                      result.database.status === 'FOUND' || result.database.status === 'MATCH'
                        ? 'pill-pass'
                        : result.database.status === 'BLACKLISTED'
                        ? 'pill-fail'
                        : result.database.status === 'EXPIRED'
                        ? 'pill-medium'
                        : 'pill-neutral'
                    }`}
                  >
                    {result.database.status}
                  </span>
                </div>

                {result.database.blacklisted && (
                  <div className="blacklist-alert">
                    <ShieldAlert size={18} />
                    <strong>WATCHLIST / INTERPOL ALERT: Subject is flagged in registry!</strong>
                  </div>
                )}

                {result.database.record && (
                  <div className="db-record-details">
                    <p>
                      <b>DB Name:</b> <span>{result.database.record.full_name}</span>
                    </p>
                    <p>
                      <b>DB DOB:</b> <span>{result.database.record.date_of_birth}</span>
                    </p>
                    <p>
                      <b>DB Expiry:</b> <span>{result.database.record.date_of_expiry}</span>
                    </p>
                    <p>
                      <b>DB Status:</b> <span>{result.database.record.registered_status}</span>
                    </p>
                  </div>
                )}

                <p className="db-note">{result.database.note}</p>
              </div>
            </div>

            {/* Forensics & Tamper Analysis */}
            <div className="result-card">
              <div className="card-header">
                <Shield size={20} className="card-icon" />
                <div>
                  <h3>Tamper & Authenticity</h3>
                  <p className="card-subtitle">Forensic Image Heuristics</p>
                </div>
                <span
                  className={`status-pill ${
                    result.tamper.tamper_risk === 'LOW'
                      ? 'pill-pass'
                      : result.tamper.tamper_risk === 'MEDIUM'
                      ? 'pill-medium'
                      : 'pill-fail'
                  }`}
                >
                  {result.tamper.tamper_risk} RISK ({result.tamper.score}/100)
                </span>
              </div>

              <div className="forensic-indicators-list">
                {result.tamper.indicators.map((ind, i) => (
                  <div key={i} className={`indicator-row ind-${ind.severity.toLowerCase()}`}>
                    <span className="ind-severity">{ind.severity}</span>
                    <p className="ind-desc">{ind.description}</p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* 5. Explainable Risk Factors Breakdown */}
          <div className="result-card risk-factors-card">
            <div className="card-header">
              <AlertCircle size={20} className="card-icon" />
              <div>
                <h3>Weighted Risk Indicators Breakdown</h3>
                <p className="card-subtitle">Transparent justification of the composite risk calculation</p>
              </div>
            </div>
            <div className="reasons-breakdown-list">
              {result.risk.reasons.length > 0 ? (
                result.risk.reasons.map((reason, idx) => (
                  <div key={idx} className="reason-item">
                    <div className="reason-text">
                      <AlertTriangle size={18} className="text-warning" />
                      <span>{reason.description}</span>
                    </div>
                    <span className="reason-points">+{reason.points} PTS</span>
                  </div>
                ))
              ) : (
                <div className="no-risk-item">
                  <CheckCircle2 size={20} className="text-success" />
                  <span>No elevated risk indicators were triggered. All checks are within nominal tolerances.</span>
                </div>
              )}
            </div>
          </div>

          {/* 6. Officer Decision Center */}
          <div className="result-card officer-decision-panel">
            <div className="card-header">
              <FileCheck size={22} className="card-icon text-accent" />
              <div>
                <h3>Immigration Officer Decision & Audit Record</h3>
                <p className="card-subtitle">Mandatory officer action required to finalize case disposition</p>
              </div>
              {result.officer_decision && (
                <span
                  className={`decision-status-badge badge-${result.officer_decision.decision.toLowerCase()}`}
                >
                  DECISION: {result.officer_decision.decision}
                </span>
              )}
            </div>

            {decisionMessage && <div className="decision-feedback-alert">{decisionMessage}</div>}

            {result.officer_decision ? (
              <div className="decision-summary-box">
                <div className="decision-header-info">
                  <UserCheck size={20} className="text-accent" />
                  <span>
                    Decision Recorded by <b>{result.officer_decision.officer_id}</b> on{' '}
                    {new Date(result.officer_decision.timestamp).toLocaleString()}
                  </span>
                </div>
                {result.officer_decision.notes && (
                  <p className="decision-notes-view">
                    <b>Officer Notes:</b> {result.officer_decision.notes}
                  </p>
                )}
                <div className="decision-modify-note">
                  To modify this decision, enter updated notes below and select an action.
                </div>
              </div>
            ) : null}

            <div className="decision-form-area">
              <label htmlFor="officer-notes-input" className="form-label">
                Officer Review Notes / Case Observations:
              </label>
              <textarea
                id="officer-notes-input"
                className="notes-textarea"
                rows={3}
                placeholder="Enter justification, verified stamps, physical inspection remarks, or secondary referral notes…"
                value={officerNotes}
                onChange={(e) => setOfficerNotes(e.target.value)}
              />

              <div className="decision-btn-group">
                <button
                  type="button"
                  className="decision-btn btn-approve"
                  disabled={decisionSaving}
                  onClick={() => void handleOfficerDecision('APPROVE')}
                >
                  <CheckCircle2 size={18} /> Approve & Clear Traveler
                </button>

                <button
                  type="button"
                  className="decision-btn btn-review"
                  disabled={decisionSaving}
                  onClick={() => void handleOfficerDecision('MANUAL_VERIFICATION')}
                >
                  <AlertTriangle size={18} /> Request Secondary / Manual Inspection
                </button>

                <button
                  type="button"
                  className="decision-btn btn-reject"
                  disabled={decisionSaving}
                  onClick={() => void handleOfficerDecision('REJECT')}
                >
                  <XCircle size={18} /> Reject & Flag Fraud Alert
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function FileTextIcon(props: { size?: number; className?: string }) {
  return (
    <svg
      width={props.size || 24}
      height={props.size || 24}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={props.className}
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  )
}

