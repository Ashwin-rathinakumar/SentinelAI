import { useState } from 'react'
import { ArrowRight } from 'lucide-react'
import { DocumentTypeSelector } from '../components/DocumentTypeSelector'
import { QualityCheckCard } from '../components/QualityCheckCard'
import { ScreeningStepper } from '../components/ScreeningStepper'
import { UploadDropzone } from '../components/UploadDropzone'
import { api } from '../services/api'
import type { DocumentType, ScreeningStep, UploadPhase, UploadResponse } from '../types'
import './NewScreeningPage.css'

export function NewScreeningPage() {
  const [documentType, setDocumentType] = useState<DocumentType | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle')
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [showPhase3Placeholder, setShowPhase3Placeholder] = useState(false)

  const documentTypeSelected = documentType !== null
  const uploadComplete = uploadPhase === 'complete' && uploadResult !== null
  const currentStep: ScreeningStep = uploadComplete ? 2 : documentTypeSelected ? 2 : 1

  const handleUpload = async () => {
    if (!selectedFile || !documentType) return

    setUploadError(null)
    setUploadResult(null)
    setUploadPhase('uploading')

    try {
      const result = await api.uploadDocument(selectedFile, documentType, (phase) => {
        setUploadPhase(phase)
      })
      setUploadResult(result)
      setUploadPhase('complete')
    } catch (err) {
      setUploadPhase('error')
      setUploadError(err instanceof Error ? err.message : 'Upload failed. Please try again.')
    }
  }

  return (
    <div className="screening-page">
      <ScreeningStepper
        currentStep={currentStep}
        documentTypeSelected={documentTypeSelected}
        uploadComplete={uploadComplete}
      />

      <DocumentTypeSelector
        selected={documentType}
        onSelect={(type) => {
          setDocumentType(type)
          setShowPhase3Placeholder(false)
        }}
      />

      <UploadDropzone
        disabled={!documentTypeSelected}
        uploadPhase={uploadPhase}
        selectedFile={selectedFile}
        onFileSelect={(file) => {
          setSelectedFile(file)
          setUploadError(null)
          setUploadResult(null)
          setUploadPhase('idle')
          setShowPhase3Placeholder(false)
        }}
        onUpload={() => void handleUpload()}
        error={uploadError}
      />

      {uploadResult && uploadPhase === 'complete' && (
        <QualityCheckCard quality={uploadResult.quality} />
      )}

      {showPhase3Placeholder ? (
        <section className="phase-placeholder">
          <h3>Phase 3 — OCR Extraction</h3>
          <p>Coming next</p>
        </section>
      ) : (
        <div className="screening-actions">
          <button
            type="button"
            className="next-step-btn"
            disabled={!uploadComplete}
            onClick={() => setShowPhase3Placeholder(true)}
          >
            Next Step
            <ArrowRight size={18} />
          </button>
        </div>
      )}
    </div>
  )
}
