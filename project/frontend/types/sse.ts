export interface StageUpdateEvent {
  stage: string
  status: string
  duration?: number
}

export interface ProgressEvent {
  progress: number
  estimated_remaining?: number
  total_cost?: number
  stage?: string  // Optional stage name (may be included in progress events)
  status?: string  // Optional status (may be included in progress events)
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
  clip_boundaries?: Array<{
    start: number
    end: number
    duration: number
  }>
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

export interface PromptGeneratorResultsEvent {
  total_clips: number
  generation_time: number
  llm_used: boolean
  llm_model?: string | null
  clip_prompts: Array<{
    clip_index: number
    prompt: string
    negative_prompt: string
    duration: number
    scene_reference_url?: string | null
    character_reference_urls: string[]
    metadata?: Record<string, any>
  }>
}

export interface VideoGenerationStartEvent {
  clip_index: number
  total_clips: number
}

export interface VideoGenerationCompleteEvent {
  clip_index: number
  video_url: string
  duration: number
  cost: number
}

export interface VideoGenerationFailedEvent {
  clip_index: number
  error: string
}

export interface VideoGenerationRetryEvent {
  clip_index: number
  attempt: number
  delay_seconds: number
  error: string
}

export interface ReferenceGenerationStartEvent {
  image_type: string
  image_id: string
  total_images: number
  current_image: number
}

export interface ReferenceGenerationCompleteEvent {
  image_type: string
  image_id: string
  image_url: string
  generation_time: number
  cost: number
  retry_count?: number
  total_images?: number
  completed_images?: number
}

export interface ReferenceGenerationFailedEvent {
  image_type: string
  image_id: string
  retry_count?: number
  reason?: string
  will_continue?: boolean
}

export interface ReferenceGenerationRetryEvent {
  image_type: string
  image_id: string
  retry_count: number
  max_retries?: number
  reason?: string
}

export interface RegenerationStartedEvent {
  sequence: number
  clip_index: number
  instruction: string
}

export interface TemplateMatchedEvent {
  sequence: number
  template_id: string
  transformation: string
}

export interface PromptModifiedEvent {
  sequence: number
  modified_prompt: string
  template_used?: string | null
}

export interface VideoGeneratingEvent {
  sequence: number
  progress: number
  clip_index: number
}

export interface RecompositionStartedEvent {
  sequence: number
  progress: number
  clip_index: number
}

export interface RecompositionCompleteEvent {
  sequence: number
  progress: number
  video_url: string
  duration: number
}

export interface RecompositionFailedEvent {
  sequence: number
  clip_index: number
  error: string
  retryable?: boolean
}

export interface RegenerationCompleteEvent {
  sequence: number
  clip_index: number
  new_clip_url: string
  cost: number
  video_url?: string  // Added for recomposition result
}

export interface RegenerationFailedEvent {
  sequence: number
  clip_index: number
  error: string
  retryable?: boolean
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
  onPromptGeneratorResults?: (data: PromptGeneratorResultsEvent) => void
  onReferenceGenerationStart?: (data: ReferenceGenerationStartEvent) => void
  onReferenceGenerationComplete?: (data: ReferenceGenerationCompleteEvent) => void
  onReferenceGenerationFailed?: (data: ReferenceGenerationFailedEvent) => void
  onReferenceGenerationRetry?: (data: ReferenceGenerationRetryEvent) => void
  onVideoGenerationStart?: (data: VideoGenerationStartEvent) => void
  onVideoGenerationComplete?: (data: VideoGenerationCompleteEvent) => void
  onVideoGenerationFailed?: (data: VideoGenerationFailedEvent) => void
  onVideoGenerationRetry?: (data: VideoGenerationRetryEvent) => void
  onRegenerationStarted?: (data: RegenerationStartedEvent) => void
  onTemplateMatched?: (data: TemplateMatchedEvent) => void
  onPromptModified?: (data: PromptModifiedEvent) => void
  onVideoGenerating?: (data: VideoGeneratingEvent) => void
  onRecompositionStarted?: (data: RecompositionStartedEvent) => void
  onRecompositionComplete?: (data: RecompositionCompleteEvent) => void
  onRecompositionFailed?: (data: RecompositionFailedEvent) => void
  onRegenerationComplete?: (data: RegenerationCompleteEvent) => void
  onRegenerationFailed?: (data: RegenerationFailedEvent) => void
}

