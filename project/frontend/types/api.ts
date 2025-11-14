export interface UploadResponse {
  job_id: string
  audio_url: string
  status: string
  estimated_time: number
}

export interface JobResponse {
  id: string
  status: "queued" | "processing" | "completed" | "failed"
  current_stage: string | null
  progress: number
  video_url: string | null
  error_message: string | null
  created_at: string
  updated_at: string
  estimated_remaining?: number
  total_cost?: number
  stages?: Record<string, {
    status: string
    duration?: number
    progress?: string
  }>
}

export class APIError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public retryable: boolean = false
  ) {
    super(message)
    this.name = "APIError"
  }
}

