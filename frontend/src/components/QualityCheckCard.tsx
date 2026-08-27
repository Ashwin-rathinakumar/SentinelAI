import { CheckCircle2 } from 'lucide-react'
import type { DocumentQuality } from '../types'
import './QualityCheckCard.css'

interface QualityCheckCardProps {
  quality: DocumentQuality
}

function metricStatusClass(label: string, metric: 'resolution' | 'brightness' | 'blur'): string {
  if (metric === 'blur') {
    if (label === 'Low') return 'good'
    if (label === 'Medium') return 'warn'
    return 'bad'
  }
  if (label === 'Excellent') return 'good'
  if (label === 'Good') return 'warn'
  return 'bad'
}

export function QualityCheckCard({ quality }: QualityCheckCardProps) {
  const metrics = [
    {
      name: 'Resolution',
      value: quality.resolution.label,
      status: metricStatusClass(quality.resolution.label, 'resolution'),
    },
    {
      name: 'Brightness',
      value: quality.brightness.label,
      status: metricStatusClass(quality.brightness.label, 'brightness'),
    },
    {
      name: 'Blur Detection',
      value: quality.blur.label,
      status: metricStatusClass(quality.blur.label, 'blur'),
    },
  ]

  return (
    <section className="quality-card">
      <div className="section-heading">
        <h2>Document Quality Check</h2>
        <p>Automated analysis results from the uploaded document.</p>
      </div>

      <div className="quality-metrics">
        {metrics.map((metric) => (
          <div key={metric.name} className="quality-metric-row">
            <span className="quality-metric-name">{metric.name}</span>
            <span className={`quality-metric-value ${metric.status}`}>{metric.value}</span>
            <CheckCircle2 className={`quality-metric-icon ${metric.status}`} size={18} />
          </div>
        ))}

        <div className="quality-metric-row ocr-row">
          <span className="quality-metric-name">OCR Readiness</span>
          <span className="quality-metric-value good">{quality.ocr_readiness}%</span>
          <CheckCircle2 className="quality-metric-icon good" size={18} />
        </div>
      </div>

      <div className="ocr-progress">
        <div className="ocr-progress-header">
          <span>OCR Readiness Score</span>
          <strong>{quality.ocr_readiness}%</strong>
        </div>
        <div className="ocr-progress-track">
          <div
            className="ocr-progress-fill"
            style={{ width: `${quality.ocr_readiness}%` }}
          />
        </div>
      </div>

      <div className="quality-complete">
        <CheckCircle2 size={16} />
        <span>Quality check complete</span>
      </div>
    </section>
  )
}
