import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, API_URL } from '../services/api'
import type { ConnectionStatus, HealthResponse } from '../types'
import '../App.css'

export function DashboardPage() {
  const [status, setStatus] = useState<ConnectionStatus>('checking')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const checkBackend = async () => {
    setStatus('checking')
    setError(null)

    try {
      const data = await api.getHealth()
      setHealth(data)
      setStatus('connected')
    } catch (err) {
      setHealth(null)
      setStatus('disconnected')
      setError(err instanceof Error ? err.message : 'Unable to reach backend')
    }
  }

  useEffect(() => {
    void checkBackend()
  }, [])

  return (
    <main className="app-main">
      <section className="status-card">
        <h2>Platform Status</h2>
        <p className="status-description">
          Verifying connectivity between the React frontend and FastAPI backend.
        </p>

        <div className="status-grid">
          <div className="status-item">
            <span className="status-label">Frontend</span>
            <span className="status-value online">Running</span>
            <span className="status-meta">Vite + React + TypeScript</span>
          </div>

          <div className="status-item">
            <span className="status-label">Backend API</span>
            <span className={`status-value ${status === 'connected' ? 'online' : status === 'checking' ? 'checking' : 'offline'}`}>
              {status === 'connected' ? 'Connected' : status === 'checking' ? 'Checking…' : 'Disconnected'}
            </span>
            <span className="status-meta">{API_URL}</span>
          </div>
        </div>

        {health && (
          <div className="health-details">
            <div><strong>Service:</strong> {health.service}</div>
            <div><strong>Version:</strong> {health.version}</div>
            <div><strong>Status:</strong> {health.status}</div>
            <div><strong>Timestamp:</strong> {new Date(health.timestamp).toLocaleString()}</div>
          </div>
        )}

        {error && <p className="error-message">{error}</p>}

        <div className="actions">
          <button type="button" onClick={() => void checkBackend()}>
            Recheck Connection
          </button>
          <a href={`${API_URL}/docs`} target="_blank" rel="noreferrer">
            Open API Docs
          </a>
          <Link to="/screening" className="nav-link-btn">
            New Screening
          </Link>
        </div>
      </section>

      <section className="info-card">
        <h3>Phase 1 Complete</h3>
        <ul>
          <li>Backend responds at <code>{API_URL}</code></li>
          <li>Swagger UI available at <code>{API_URL}/docs</code></li>
          <li>Frontend loads at <code>http://localhost:5173</code></li>
          <li>Health check returns <code>healthy</code></li>
        </ul>
        <p className="demo-note">
          Phase 2 adds document upload and quality analysis via the New Screening workflow.
        </p>
      </section>
    </main>
  )
}
