export interface Job {
  id: string
  status: "queued" | "processing" | "completed" | "failed"
  currentStage: string | null
  progress: number
  videoUrl: string | null
  audioUrl?: string | null
  errorMessage: string | null
  createdAt: string
  updatedAt: string
  estimatedRemaining?: number
  totalCost?: number
  stages?: Record<string, {
    status: string
    duration?: number
    progress?: string
    metadata?: Record<string, any>
  }>
  audioData?: {
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

export interface JobStage {
  name: string
  status: "pending" | "processing" | "completed" | "failed"
}

