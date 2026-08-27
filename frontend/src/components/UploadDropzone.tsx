import { FileUp, Loader2, Upload, X } from 'lucide-react'
import { useCallback, useRef, useState } from 'react'
import type { UploadPhase } from '../types'
import './UploadDropzone.css'

const ACCEPTED_TYPES = ['.jpg', '.jpeg', '.png', '.pdf']
const ACCEPTED_MIME = ['image/jpeg', 'image/png', 'application/pdf']
const MAX_SIZE_BYTES = 10 * 1024 * 1024

interface UploadDropzoneProps {
  disabled: boolean
  uploadPhase: UploadPhase
  selectedFile: File | null
  onFileSelect: (file: File | null) => void
  onUpload: () => void
  error: string | null
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
}

function validateFile(file: File): string | null {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`
  if (!ACCEPTED_TYPES.includes(extension)) {
    return 'Unsupported file type. Please upload JPG, JPEG, PNG, or PDF.'
  }
  if (file.type && !ACCEPTED_MIME.includes(file.type)) {
    return 'Invalid file format. Please upload a valid image or PDF.'
  }
  if (file.size > MAX_SIZE_BYTES) {
    return 'File exceeds the 10 MB size limit.'
  }
  if (file.size === 0) {
    return 'The selected file is empty.'
  }
  return null
}

export function UploadDropzone({
  disabled,
  uploadPhase,
  selectedFile,
  onFileSelect,
  onUpload,
  error,
}: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragActive, setDragActive] = useState(false)
  const [localError, setLocalError] = useState<string | null>(null)

  const isBusy = uploadPhase === 'uploading' || uploadPhase === 'analyzing'

  const handleFile = useCallback(
    (file: File | null) => {
      setLocalError(null)
      if (!file) {
        onFileSelect(null)
        return
      }
      const validationError = validateFile(file)
      if (validationError) {
        setLocalError(validationError)
        onFileSelect(null)
        return
      }
      onFileSelect(file)
    },
    [onFileSelect],
  )

  const onInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null
    handleFile(file)
    event.target.value = ''
  }

  const onDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setDragActive(false)
    if (disabled || isBusy) return
    const file = event.dataTransfer.files?.[0] ?? null
    handleFile(file)
  }

  const previewUrl =
    selectedFile && selectedFile.type.startsWith('image/')
      ? URL.createObjectURL(selectedFile)
      : null

  const displayError = error ?? localError

  return (
    <section className="upload-section">
      <div className="section-heading">
        <h2>Upload Document</h2>
        <p>Submit a clear scan or photo of the selected identity document.</p>
      </div>

      <div
        className={`upload-dropzone ${dragActive ? 'drag-active' : ''} ${disabled ? 'disabled' : ''}`}
        onDragEnter={(e) => {
          e.preventDefault()
          if (!disabled && !isBusy) setDragActive(true)
        }}
        onDragOver={(e) => e.preventDefault()}
        onDragLeave={(e) => {
          e.preventDefault()
          setDragActive(false)
        }}
        onDrop={onDrop}
        onClick={() => {
          if (!disabled && !isBusy) inputRef.current?.click()
        }}
        role="button"
        tabIndex={disabled || isBusy ? -1 : 0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            if (!disabled && !isBusy) inputRef.current?.click()
          }
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          onChange={onInputChange}
          hidden
          disabled={disabled || isBusy}
        />

        <div className="upload-dropzone-icon" aria-hidden="true">
          <Upload size={28} strokeWidth={1.75} />
        </div>

        <p className="upload-title">Upload Document</p>
        <p className="upload-subtitle">Drag &amp; drop your file here</p>
        <p className="upload-subtitle">or click to browse</p>
        <p className="upload-meta">Supports JPG, JPEG, PNG, PDF · Maximum size: 10 MB</p>
      </div>

      {selectedFile && (
        <div className="file-preview">
          {previewUrl ? (
            <img src={previewUrl} alt="Document preview" className="file-preview-image" />
          ) : (
            <div className="file-preview-placeholder">
              <FileUp size={24} />
              <span>PDF Document</span>
            </div>
          )}

          <div className="file-preview-details">
            <strong>{selectedFile.name}</strong>
            <span>{formatFileSize(selectedFile.size)}</span>
          </div>

          {!isBusy && uploadPhase !== 'complete' && (
            <button
              type="button"
              className="file-remove-btn"
              onClick={(e) => {
                e.stopPropagation()
                handleFile(null)
              }}
              aria-label="Remove file"
            >
              <X size={16} />
            </button>
          )}
        </div>
      )}

      {displayError && <p className="upload-error">{displayError}</p>}

      {isBusy && (
        <div className="upload-status">
          <Loader2 className="spin" size={18} />
          <span>
            {uploadPhase === 'uploading'
              ? 'Uploading document...'
              : 'Analyzing document quality...'}
          </span>
        </div>
      )}

      {selectedFile && uploadPhase === 'idle' && (
        <button
          type="button"
          className="upload-submit-btn"
          disabled={disabled}
          onClick={onUpload}
        >
          Upload &amp; Analyze
        </button>
      )}
    </section>
  )
}
