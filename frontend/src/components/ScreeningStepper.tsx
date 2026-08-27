import { Brain, FileSearch, ScanFace, UploadCloud } from 'lucide-react'
import type { ScreeningStep } from '../types'
import './ScreeningStepper.css'

interface StepConfig {
  id: ScreeningStep
  label: string
  icon: typeof UploadCloud
}

const STEPS: StepConfig[] = [
  { id: 1, label: 'Document Type', icon: FileSearch },
  { id: 2, label: 'Upload & Quality', icon: UploadCloud },
  { id: 3, label: 'Face Verification', icon: ScanFace },
  { id: 4, label: 'AI Analysis', icon: Brain },
]

interface ScreeningStepperProps {
  currentStep: ScreeningStep
  documentTypeSelected: boolean
  uploadComplete: boolean
}

function getStepState(
  stepId: ScreeningStep,
  currentStep: ScreeningStep,
  documentTypeSelected: boolean,
  uploadComplete: boolean,
): 'complete' | 'active' | 'upcoming' {
  if (stepId === 1) {
    return documentTypeSelected ? 'complete' : 'active'
  }
  if (stepId === 2) {
    if (uploadComplete) return 'complete'
    if (documentTypeSelected) return 'active'
    return 'upcoming'
  }
  if (stepId <= currentStep && uploadComplete) {
    return stepId === currentStep ? 'active' : 'complete'
  }
  return 'upcoming'
}

export function ScreeningStepper({
  currentStep,
  documentTypeSelected,
  uploadComplete,
}: ScreeningStepperProps) {
  return (
    <nav className="screening-stepper" aria-label="Screening progress">
      {STEPS.map((step, index) => {
        const state = getStepState(
          step.id,
          currentStep,
          documentTypeSelected,
          uploadComplete,
        )
        const Icon = step.icon

        return (
          <div key={step.id} className="stepper-item-wrap">
            <div className={`stepper-item ${state}`}>
              <div className="stepper-marker">
                {state === 'complete' ? (
                  <span className="stepper-check">✓</span>
                ) : (
                  <Icon size={16} strokeWidth={1.75} />
                )}
              </div>
              <div className="stepper-text">
                <span className="stepper-number">{step.id}</span>
                <span className="stepper-label">{step.label}</span>
              </div>
            </div>
            {index < STEPS.length - 1 && (
              <div className={`stepper-connector ${state === 'complete' ? 'complete' : ''}`} />
            )}
          </div>
        )
      })}
    </nav>
  )
}
