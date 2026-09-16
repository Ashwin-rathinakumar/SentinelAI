import {
  BookOpen,
  Car,
  CreditCard,
  FileCheck2,
  Globe,
} from 'lucide-react'
import type { DocumentType } from '../types'
import './DocumentTypeSelector.css'

export interface DocumentTypeOption {
  id: DocumentType
  title: string
  description: string
  icon: typeof BookOpen
}

const DOCUMENT_TYPES: DocumentTypeOption[] = [
  { id: 'unknown', title: 'Auto detect', description: 'Identify the document from its contents.', icon: FileCheck2 },
  { id: 'aadhaar', title: 'Aadhaar', description: 'Indian identity card; no passport MRZ or expiry.', icon: CreditCard },
  {
    id: 'passport',
    title: 'Passport',
    description: 'International travel document with biometric data page.',
    icon: BookOpen,
  },
  {
    id: 'visa',
    title: 'Visa',
    description: 'Entry authorization sticker or visa document.',
    icon: Globe,
  },
  {
    id: 'national_id',
    title: 'National ID',
    description: 'Government-issued national identity card.',
    icon: CreditCard,
  },
  {
    id: 'driving_license',
    title: 'Driving Licence',
    description: 'Official driver licence with photo identification.',
    icon: Car,
  },
  {
    id: 'permit',
    title: 'Permit / Authorization',
    description: 'Work, residence, or special authorization permit.',
    icon: FileCheck2,
  },
]

interface DocumentTypeSelectorProps {
  selected: DocumentType | null
  onSelect: (type: DocumentType) => void
}

export function DocumentTypeSelector({ selected, onSelect }: DocumentTypeSelectorProps) {
  return (
    <section className="doc-type-section">
      <div className="section-heading">
        <h2>Select Document Type</h2>
        <p>Choose a document hint. Screening determines the type from the uploaded contents.</p>
      </div>

      <div className="doc-type-grid">
        {DOCUMENT_TYPES.map(({ id, title, description, icon: Icon }) => {
          const isSelected = selected === id
          return (
            <button
              key={id}
              type="button"
              className={`doc-type-card ${isSelected ? 'selected' : ''}`}
              onClick={() => onSelect(id)}
              aria-pressed={isSelected}
            >
              <div className="doc-type-icon" aria-hidden="true">
                <Icon size={22} strokeWidth={1.75} />
              </div>
              <div className="doc-type-content">
                <h3>{title}</h3>
                <p>{description}</p>
              </div>
              {isSelected && <span className="doc-type-check" aria-hidden="true">✓</span>}
            </button>
          )
        })}
      </div>
    </section>
  )
}
