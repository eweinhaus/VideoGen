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
    metadata?: Record<string, any>
  }>
  audio_data?: {
    bpm: number
    duration: number
    beat_timestamps: number[]
    song_structure: Array<{
      type: string
      start: number
      end: number
      energy: string
    }>
    mood: {
      primary: string
      secondary?: string
      energy_level?: string
      confidence?: number
    }
    lyrics: Array<{ text: string; timestamp: number }>
    clip_boundaries: Array<{ start: number; end: number; duration: number }>
    metadata?: Record<string, any>
  }
}

export interface ModelAspectRatiosResponse {
  model_key: string
  aspect_ratios: string[]
  default: string
}

export interface ClipData {
  clip_index: number
  thumbnail_url: string | null
  timestamp_start: number
  timestamp_end: number
  lyrics_preview: string | null
  duration: number
  is_regenerated: boolean
  original_prompt: string | null
}

export interface ClipListResponse {
  clips: ClipData[]
  total_clips: number
}

export interface RegenerationRequest {
  instruction: string
  conversation_history?: Array<{ role: string; content: string }>
}

export interface RegenerationResponse {
  regeneration_id: string
  estimated_cost: number
  estimated_time: number
  status: string
  template_matched?: string | null
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

