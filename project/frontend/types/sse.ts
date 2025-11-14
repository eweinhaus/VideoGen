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

export interface SSEHandlers {
  onStageUpdate?: (data: StageUpdateEvent) => void
  onProgress?: (data: ProgressEvent) => void
  onMessage?: (data: MessageEvent) => void
  onCostUpdate?: (data: CostUpdateEvent) => void
  onCompleted?: (data: CompletedEvent) => void
  onError?: (data: ErrorEvent) => void
}

