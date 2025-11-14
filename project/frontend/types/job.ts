export interface Job {
  id: string
  status: "queued" | "processing" | "completed" | "failed"
  currentStage: string | null
  progress: number
  videoUrl: string | null
  errorMessage: string | null
  createdAt: string
  updatedAt: string
  estimatedRemaining?: number
  totalCost?: number
  stages?: Record<string, {
    status: string
    duration?: number
    progress?: string
  }>
}

export interface JobStage {
  name: string
  status: "pending" | "processing" | "completed" | "failed"
}

