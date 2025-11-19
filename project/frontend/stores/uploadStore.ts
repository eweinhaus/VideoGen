import { create } from "zustand"
import { uploadAudio } from "@/lib/api"
import type { PipelineStage } from "@/components/StepSelector"
import type { VideoModel } from "@/components/ModelSelector"
import type { Template } from "@/components/TemplateSelector"

interface ErrorDetails {
  category?: string
  error_type?: string
  error_message?: string
  user_message?: string
  suggestions?: string[]
  job_id?: string
  timestamp?: string
}

interface UploadState {
  audioFile: File | null
  userPrompt: string
  stopAtStage: PipelineStage | null
  videoModel: VideoModel
  aspectRatio: string
  template: Template
  isSubmitting: boolean
  errors: { audio?: string; prompt?: string }
  errorDetails: ErrorDetails | null
  setAudioFile: (file: File | null) => void
  setUserPrompt: (prompt: string) => void
  setStopAtStage: (stage: PipelineStage | null) => void
  setVideoModel: (model: VideoModel) => void
  setAspectRatio: (aspectRatio: string) => void
  setTemplate: (template: Template) => void
  validate: () => boolean
  submit: () => Promise<string>
  reset: () => void
}

const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10MB
const VALID_AUDIO_TYPES = [
  "audio/mpeg",
  "audio/mp3",
  "audio/wav",
  "audio/x-wav",
  "audio/flac",
  "audio/x-flac",
]

// Check if we're in production environment
const isProduction = (): boolean => {
  if (process.env.NODE_ENV === "production") {
    return true
  }
  if (process.env.NEXT_PUBLIC_ENVIRONMENT === "production") {
    return true
  }
  if (process.env.NEXT_PUBLIC_DISABLE_STOP_AT_STAGE === "true") {
    return true
  }
  if (typeof window !== "undefined") {
    const hostname = window.location.hostname
    const isLocalhost = hostname === "localhost" || hostname.includes("127.0.0.1")
    const isPreviewDeployment = hostname.includes(".vercel.app") && 
                                 (hostname.match(/-/g) || []).length >= 2
    if (!isLocalhost && !isPreviewDeployment) {
      return true
    }
  }
  return false
}

// Default to composer (full pipeline) for all environments
const getDefaultStopAtStage = (): PipelineStage | null => {
  return "composer"
}

export const uploadStore = create<UploadState>((set, get) => ({
  audioFile: null,
  userPrompt: "",
  stopAtStage: getDefaultStopAtStage(),
  videoModel: "veo_31", // Default model
  aspectRatio: "16:9", // Default aspect ratio
  template: "standard", // Default template
  isSubmitting: false,
  errors: {},
  errorDetails: null,

  setAudioFile: (file: File | null) => {
    if (!file) {
      set({ audioFile: null, errors: { ...get().errors, audio: undefined } })
      return
    }

    // Validate MIME type
    const isValidType = VALID_AUDIO_TYPES.includes(file.type)
    if (!isValidType) {
      set({
        audioFile: null,
        errors: {
          ...get().errors,
          audio: "Invalid file format. Please upload MP3, WAV, or FLAC",
        },
      })
      return
    }

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      set({
        audioFile: null,
        errors: {
          ...get().errors,
          audio: "File size must be less than 10MB",
        },
      })
      return
    }

    set({
      audioFile: file,
      errors: { ...get().errors, audio: undefined },
    })
  },

  setUserPrompt: (prompt: string) => {
    set({ userPrompt: prompt })
    const { errors } = get()
    if (prompt.length >= 50 && prompt.length <= 500) {
      set({ errors: { ...errors, prompt: undefined } })
    }
  },

  setStopAtStage: (stage: PipelineStage | null) => {
    set({ stopAtStage: stage })
  },

  setVideoModel: (model: VideoModel) => {
    set({ videoModel: model })
  },

  setAspectRatio: (aspectRatio: string) => {
    set({ aspectRatio })
  },

  setTemplate: (template: Template) => {
    set({ template })
  },

  validate: () => {
    const { audioFile, userPrompt } = get()
    const errors: { audio?: string; prompt?: string } = {}

    // Validate audio file
    if (!audioFile) {
      errors.audio = "Please select an audio file"
    } else {
      const isValidType = VALID_AUDIO_TYPES.includes(audioFile.type)
      if (!isValidType) {
        errors.audio = "Invalid file format. Please upload MP3, WAV, or FLAC"
      } else if (audioFile.size > MAX_FILE_SIZE) {
        errors.audio = "File size must be less than 10MB"
      }
    }

    // Validate prompt
    if (userPrompt.length < 50) {
      errors.prompt = "Prompt must be at least 50 characters"
    } else if (userPrompt.length > 500) {
      errors.prompt = "Prompt must be at most 500 characters"
    }

    set({ errors })
    return Object.keys(errors).length === 0
  },

  submit: async () => {
    const { audioFile, userPrompt, videoModel, validate } = get()

    if (!validate()) {
      throw new Error("Validation failed")
    }

    if (!audioFile) {
      throw new Error("Audio file is required")
    }

    set({ isSubmitting: true, errors: {} })

    try {
      // In production, always use composer (full pipeline)
      // In development, use the selected stage or default to composer
      const stopAtStage = isProduction()
        ? "composer" 
        : get().stopAtStage || "composer"
      
      const { aspectRatio, template } = get()
      const response = await uploadAudio(audioFile, userPrompt, stopAtStage, videoModel, aspectRatio, template)
      // Don't reset isSubmitting here - keep it true so popup stays visible during navigation
      // The job page will reset it once we're on /jobs/[jobId]
      return response.job_id
    } catch (error: any) {
      let errorMessage = error.message || "Upload failed"
      let errorDetails: ErrorDetails | null = null
      
      // Extract error details if available
      if (error.errorDetails) {
        errorDetails = error.errorDetails
        // Use user_message if available, otherwise fall back to error message
        if (errorDetails.user_message) {
          errorMessage = errorDetails.user_message
        }
      }
      
      // Handle authentication errors specifically
      if (error.statusCode === 401 || error.message?.includes("Unauthorized") || error.message?.includes("Not authenticated")) {
        errorMessage = "Please log in to upload files"
        // The API client will handle redirect, but we should still show a clear message
      }
      
      set({
        isSubmitting: false,
        errors: {
          ...get().errors,
          audio: errorMessage,
        },
        errorDetails: errorDetails,
      })
      throw error
    }
  },

  reset: () => {
    set({
      audioFile: null,
      userPrompt: "",
      stopAtStage: getDefaultStopAtStage(), // Reset to default (composer)
      videoModel: "veo_31", // Reset to default model
      aspectRatio: "16:9", // Reset to default aspect ratio
      template: "standard", // Reset to default template
      errors: {},
      errorDetails: null,
      isSubmitting: false,
    })
  },
}))

