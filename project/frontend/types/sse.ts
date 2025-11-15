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
    energy_level?: string
    confidence?: number
  }
  lyrics_count: number
  clip_boundaries_count: number
}

export interface ScenePlannerResultsEvent {
  job_id: string
  video_summary: string
  characters: Array<{
    id: string
    description: string
    role: string
  }>
  scenes: Array<{
    id: string
    description: string
    time_of_day: string
  }>
  style: {
    color_palette: string[]
    visual_style: string
    mood: string
    lighting: string
    cinematography: string
  }
  clip_scripts: Array<{
    clip_index: number
    start: number
    end: number
    visual_description: string
    motion: string
    camera_angle: string
    characters: string[]
    scenes: string[]
    lyrics_context?: string | null
    beat_intensity: string
  }>
  transitions: Array<{
    from_clip: number
    to_clip: number
    type: string
    duration: number
    rationale: string
  }>
}

export interface SSEHandlers {
  onStageUpdate?: (data: StageUpdateEvent) => void
  onProgress?: (data: ProgressEvent) => void
  onMessage?: (data: MessageEvent) => void
  onCostUpdate?: (data: CostUpdateEvent) => void
  onCompleted?: (data: CompletedEvent) => void
  onError?: (data: ErrorEvent) => void
  onAudioParserResults?: (data: AudioParserResultsEvent) => void
  onScenePlannerResults?: (data: ScenePlannerResultsEvent) => void
}

