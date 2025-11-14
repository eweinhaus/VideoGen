import { create } from "zustand"
import { uploadAudio } from "@/lib/api"

interface UploadState {
  audioFile: File | null
  userPrompt: string
  isSubmitting: boolean
  errors: { audio?: string; prompt?: string }
  setAudioFile: (file: File | null) => void
  setUserPrompt: (prompt: string) => void
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

export const uploadStore = create<UploadState>((set, get) => ({
  audioFile: null,
  userPrompt: "",
  isSubmitting: false,
  errors: {},

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
    const { audioFile, userPrompt, validate } = get()

    if (!validate()) {
      throw new Error("Validation failed")
    }

    if (!audioFile) {
      throw new Error("Audio file is required")
    }

    set({ isSubmitting: true, errors: {} })

    try {
      const response = await uploadAudio(audioFile, userPrompt)
      set({ isSubmitting: false })
      return response.job_id
    } catch (error: any) {
      set({
        isSubmitting: false,
        errors: {
          ...get().errors,
          audio: error.message || "Upload failed",
        },
      })
      throw error
    }
  },

  reset: () => {
    set({
      audioFile: null,
      userPrompt: "",
      errors: {},
      isSubmitting: false,
    })
  },
}))

