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

export interface StyleTransferOptions {
  color_palette?: boolean
  lighting?: boolean
  mood?: boolean
  camera_angle?: boolean
  motion?: boolean
  preserve_characters?: boolean
}

export interface Suggestion {
  type: "quality" | "consistency" | "creative"
  description: string
  example_instruction: string
  confidence: number
}

export interface SuggestionsResponse {
  suggestions: Suggestion[]
  cached: boolean
}

export interface ClipInstruction {
  clip_index: number
  instruction: string
}

export interface MultiClipInstructionResponse {
  target_clips: number[]
  per_clip_instructions: ClipInstruction[]
  estimated_cost: number
  per_clip_costs: Array<{
    clip_index: number
    cost: number
  }>
  batch_discount_applied: boolean
}

export interface ErrorDetails {
  total_clips?: number
  successful?: number
  failed?: number
  min_required?: number
  rate_limit_failures?: number
  failed_clips?: Array<{
    clip_index: number
    error: string
    error_type: string
    is_rate_limit: boolean
    prompt_preview?: string
  }>
}

export class APIError extends Error {
  public errorDetails?: ErrorDetails
  
  constructor(
    message: string,
    public statusCode: number,
    public retryable: boolean = false,
    errorDetails?: ErrorDetails
  ) {
    super(message)
    this.name = "APIError"
    this.errorDetails = errorDetails
  }
}

