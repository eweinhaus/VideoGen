export interface StageUpdateEvent {
  stage: string
  status: string
  duration?: number
}

export interface ProgressEvent {
  progress: number
  estimated_remaining?: number
}

export interface MessageEvent {
  text: string
  stage?: string
}

export interface CostUpdateEvent {
  stage: string
  cost: number
  total: number
}

export interface CompletedEvent {
  video_url: string
  total_cost?: number
}

export interface ErrorEvent {
  error: string
  code?: string
  retryable?: boolean
}

export interface AudioParserResultsEvent {
  bpm: number
  duration: number
  beat_timestamps: number[]
  beat_count: number
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
  lyrics_count: number
  clip_boundaries_count: number
  metadata?: {
    cache_hit?: boolean
    fallback_used?: string[]
    beat_detection_confidence?: number
    structure_confidence?: number
    mood_confidence?: number
    processing_time?: number
    [key: string]: any
  }
}

export interface SSEHandlers {
  onStageUpdate?: (data: StageUpdateEvent) => void
  onProgress?: (data: ProgressEvent) => void
  onMessage?: (data: MessageEvent) => void
  onCostUpdate?: (data: CostUpdateEvent) => void
  onCompleted?: (data: CompletedEvent) => void
  onError?: (data: ErrorEvent) => void
  onAudioParserResults?: (data: AudioParserResultsEvent) => void
}

