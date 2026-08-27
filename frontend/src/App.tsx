import { Link, NavLink, Route, Routes } from 'react-router-dom'
import './App.css'
import { NewScreeningPage } from './pages/NewScreeningPage'
import { DashboardPage } from './pages/DashboardPage'

function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <Link to="/" className="brand-link">
            <div className="brand-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <path
                  d="M12 2L4 6v6c0 5.5 3.4 10.4 8 12 4.6-1.6 8-6.5 8-12V6l-8-4z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  fill="currentColor"
                  fillOpacity="0.15"
                />
                <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <div>
              <h1>SentinelAI</h1>
              <p className="subtitle">AI Security Intelligence</p>
            </div>
          </Link>
        </div>

        <nav className="app-nav">
          <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            Dashboard
          </NavLink>
          <NavLink to="/screening" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
            New Screening
          </NavLink>
        </nav>

        <span className="phase-badge">Phase 2 — Document Screening</span>
      </header>

      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/screening" element={<NewScreeningPage />} />
      </Routes>
    </div>
  )
}

export default App
