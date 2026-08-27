import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Database,
  FileCheck,
  FileSearch,
  Fingerprint,
  RefreshCw,
  Shield,
  ShieldCheck,
  UserCheck,
} from 'lucide-react'
import { api, API_URL } from '../services/api'
import type { CaseSummary, ConnectionStatus, HealthResponse } from '../types'
import '../App.css'

export function DashboardPage() {
  const [status, setStatus] = useState<ConnectionStatus>('checking')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [loadingCases, setLoadingCases] = useState(false)

  const loadData = async () => {
    setStatus('checking')
    setError(null)
    setLoadingCases(true)

    try {
      const data = await api.getHealth()
      setHealth(data)
      setStatus('connected')
    } catch (err) {
      setHealth(null)
      setStatus('disconnected')
      setError(err instanceof Error ? err.message : 'Unable to reach backend')
    }

    try {
      const casesData = await api.getCases()
      setCases(casesData.cases || [])
    } catch (err) {
      console.error('Failed to load cases:', err)
    } finally {
      setLoadingCases(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  return (
    <main className="app-main">
      {/* Top Banner */}
      <section className="hero-banner">
        <div className="hero-content">
          <div className="hero-badge">
            <ShieldCheck size={16} /> SIH26188 Intelligent Border Security Solution
          </div>
          <h1>SentinelAI Screening Platform</h1>
          <p className="hero-subtitle">
            Next-Generation AI Fake Identity & Travel Document Verification System featuring OCR extraction,
            ICAO 9303 MRZ mathematical validation, 1:1 facial biometric matching, forensic tamper heuristics,
            and explainable risk scoring.
          </p>
          <div className="hero-actions">
            <Link to="/screening" className="hero-primary-btn">
              Launch Screening Workflow <ArrowRight size={18} />
            </Link>
            <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer" className="hero-secondary-btn">
              API Documentation & Swagger
            </a>
          </div>
        </div>
      </section>

      {/* System Status & Key Capabilities */}
      <div className="dashboard-top-grid">
        <section className="status-card">
          <div className="card-top-title">
            <h3>System Status</h3>
            <button type="button" className="refresh-mini-btn" onClick={() => void loadData()}>
              <RefreshCw size={14} /> Refresh
            </button>
          </div>

          <div className="status-grid">
            <div className="status-item">
              <span className="status-label">Frontend Web UI</span>
              <span className="status-value online">Running</span>
              <span className="status-meta">Vite + React + TypeScript</span>
            </div>

            <div className="status-item">
              <span className="status-label">Backend Screening API</span>
              <span
                className={`status-value ${
                  status === 'connected' ? 'online' : status === 'checking' ? 'checking' : 'offline'
                }`}
              >
                {status === 'connected' ? 'Connected' : status === 'checking' ? 'Checking…' : 'Disconnected'}
              </span>
              <span className="status-meta">{API_URL}</span>
            </div>

            <div className="status-item">
              <span className="status-label">OCR & MRZ Engine</span>
              <span className="status-value online">RapidOCR ONNX (PaddleOCR)</span>
              <span className="status-meta">ICAO 9303 TD1/TD2/TD3 Ready</span>
            </div>

            <div className="status-item">
              <span className="status-label">Biometric Verification</span>
              <span className="status-value online">OpenCV 1:1 Biometrics</span>
              <span className="status-meta">Facial Haar + Feature Embeddings</span>
            </div>
          </div>

          {health && (
            <div className="health-details">
              <div>
                <strong>Service:</strong> {health.service}
              </div>
              <div>
                <strong>Version:</strong> {health.version}
              </div>
              <div>
                <strong>Status:</strong> {health.status}
              </div>
              <div>
                <strong>Timestamp:</strong> {new Date(health.timestamp).toLocaleString()}
              </div>
            </div>
          )}

          {error && <p className="error-message">{error}</p>}
        </section>

        <section className="capabilities-card">
          <h3>Core Security Modules</h3>
          <ul className="capabilities-list">
            <li>
              <FileSearch size={18} className="text-accent" />
              <div>
                <strong>ICAO 9303 MRZ Engine:</strong> Mathematical check-digit validation, character confusion
                sanitization, and composite check calculations.
              </div>
            </li>
            <li>
              <Fingerprint size={18} className="text-accent" />
              <div>
                <strong>1:1 Biometric Verification:</strong> Automated face extraction from document and cross-matching
                against live webcam/selfie captures.
              </div>
            </li>
            <li>
              <Shield size={18} className="text-accent" />
              <div>
                <strong>Forensic Tamper Detection:</strong> Error Level Analysis (ELA), edge density gradients, and
                container metadata inspection.
              </div>
            </li>
            <li>
              <Database size={18} className="text-accent" />
              <div>
                <strong>Immigration Registry Lookup:</strong> Watchlist and synthetic border control database checks.
              </div>
            </li>
            <li>
              <UserCheck size={18} className="text-accent" />
              <div>
                <strong>Officer Decision Center:</strong> Explicit audit trails, review notes, and tamper-resistant
                case persistence.
              </div>
            </li>
          </ul>
        </section>
      </div>

      {/* Case Management Audit Log Table */}
      <section className="cases-table-card">
        <div className="table-header">
          <div>
            <h3>Recent Screening Cases & Audit Log</h3>
            <p className="table-subtitle">Live repository of processed documents, risk scores, and officer decisions</p>
          </div>
          <Link to="/screening" className="nav-link-btn">
            + New Screening
          </Link>
        </div>

        {loadingCases ? (
          <div className="loading-state">
            <RefreshCw size={24} className="spin-icon" /> Loading case records…
          </div>
        ) : cases.length === 0 ? (
          <div className="empty-state">
            <FileCheck size={36} className="text-muted" />
            <p>No screening cases recorded yet. Run a screening to see audit logs here.</p>
            <Link to="/screening" className="hero-primary-btn">
              Screen First Document
            </Link>
          </div>
        ) : (
          <div className="table-responsive">
            <table className="cases-table">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Date & Time</th>
                  <th>Doc Type</th>
                  <th>Document No</th>
                  <th>Holder Name</th>
                  <th>Risk Level</th>
                  <th>Validation</th>
                  <th>Officer Decision</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c) => {
                  const riskLevel = c.risk?.risk_level || 'UNKNOWN'
                  const score = c.risk?.risk_score ?? 0
                  const isHigh = riskLevel.includes('HIGH')
                  const isMedium = riskLevel.includes('MEDIUM')
                  const decision = c.officer_decision?.decision

                  return (
                    <tr key={c.case_id}>
                      <td>
                        <span className="table-case-id">{c.case_id}</span>
                      </td>
                      <td className="table-time">
                        {c.timestamp ? new Date(c.timestamp).toLocaleString() : '—'}
                      </td>
                      <td>
                        <span className="doc-type-pill">{c.document_type.toUpperCase()}</span>
                      </td>
                      <td className="table-docnum">{c.document_number}</td>
                      <td>{c.holder_name || 'Unknown'}</td>
                      <td>
                        <span
                          className={`table-risk-badge ${
                            isHigh ? 'risk-high' : isMedium ? 'risk-medium' : 'risk-low'
                          }`}
                        >
                          {score}/100 · {riskLevel}
                        </span>
                      </td>
                      <td>
                        <span
                          className={`table-status-badge ${
                            c.validation === 'VALID'
                              ? 'status-valid'
                              : c.validation === 'INVALID'
                              ? 'status-invalid'
                              : 'status-review'
                          }`}
                        >
                          {c.validation || 'REVIEW'}
                        </span>
                      </td>
                      <td>
                        {decision ? (
                          <span
                            className={`table-decision-badge badge-${decision.toLowerCase()}`}
                          >
                            {decision}
                          </span>
                        ) : (
                          <span className="table-decision-pending">PENDING</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  )
}

