import { authStore } from "@/stores/authStore"
import { APIError, UploadResponse, JobResponse } from "@/types/api"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const token = authStore.getState().token
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  // Don't set Content-Type for FormData (browser will set it with boundary)
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json"
  }

  try {
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers,
    })

    if (!response.ok) {
      let errorMessage = "An error occurred"
      let retryable = false

      if (response.status === 401) {
        // Clear auth state and redirect to login
        authStore.getState().logout()
        if (typeof window !== "undefined") {
          window.location.href = "/login"
        }
        throw new APIError("Unauthorized", 401, false)
      }

      if (response.status === 429) {
        const retryAfter = response.headers.get("retry-after")
        errorMessage = `Too many requests. Please try again${retryAfter ? ` after ${retryAfter} seconds` : ""}`
        retryable = true
      } else if (response.status === 400) {
        const data = await response.json().catch(() => ({}))
        errorMessage = data.message || "Validation error"
        retryable = false
      } else if (response.status >= 500) {
        errorMessage = "Server error. Please try again later"
        retryable = true
      }

      throw new APIError(errorMessage, response.status, retryable)
    }

    // Handle empty responses
    const contentType = response.headers.get("content-type")
    if (contentType?.includes("application/json")) {
      return await response.json()
    }

    return response as unknown as T
  } catch (error) {
    if (error instanceof APIError) {
      throw error
    }
    throw new APIError("Connection error", 0, true)
  }
}

export async function uploadAudio(
  audioFile: File,
  userPrompt: string
): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("audio_file", audioFile)
  formData.append("user_prompt", userPrompt)

  return request<UploadResponse>("/api/v1/upload-audio", {
    method: "POST",
    body: formData,
  })
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/api/v1/jobs/${jobId}`)
}

export async function downloadVideo(jobId: string): Promise<Blob> {
  const token = authStore.getState().token
  const headers: Record<string, string> = {}

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}/api/v1/jobs/${jobId}/download`, {
    headers,
  })

  if (!response.ok) {
    if (response.status === 401) {
      authStore.getState().logout()
      if (typeof window !== "undefined") {
        window.location.href = "/login"
      }
      throw new APIError("Unauthorized", 401, false)
    }
    if (response.status === 404) {
      throw new APIError("Video not ready", 404, false)
    }
    throw new APIError("Download failed", response.status, true)
  }

  return await response.blob()
}

