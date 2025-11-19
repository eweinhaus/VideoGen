import { authStore } from "@/stores/authStore"
import { APIError, UploadResponse, JobResponse, RegenerationRequest, RegenerationResponse } from "@/types/api"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

/**
 * Make a public request without authentication (for public endpoints)
 */
async function publicRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  timeoutMs: number = 10000
): Promise<T> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }

  // Don't set Content-Type for FormData (browser will set it with boundary)
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json"
  }

  try {
    const fullUrl = `${API_BASE_URL}${endpoint}`
    
    // Add timeout to prevent hanging
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
    
    const response = await fetch(fullUrl, {
      ...options,
      headers,
      signal: controller.signal,
    })
    
    clearTimeout(timeoutId)

    if (!response.ok) {
      let errorMessage = "An error occurred"
      let retryable = false

      if (response.status === 429) {
        const retryAfter = response.headers.get("retry-after")
        errorMessage = `Too many requests. Please try again${retryAfter ? ` after ${retryAfter} seconds` : ""}`
        retryable = true
      } else if (response.status === 400) {
        const data = await response.json().catch(() => ({}))
        errorMessage = data.error || data.message || "Validation error"
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
    // Handle abort (timeout)
    if (error instanceof Error && error.name === "AbortError") {
      console.error("❌ Request timeout:", endpoint)
      throw new APIError("Request timeout - server took too long to respond", 0, true)
    }
    console.error("❌ Request error:", endpoint, error)
    throw new APIError("Connection error", 0, true)
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {},
  timeoutMs: number = 30000
): Promise<T> {
  const token = authStore.getState().token
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  }

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  } else {
    // Try to get token from Supabase session as fallback (similar to SSE)
    try {
      const { supabase } = await import("@/lib/supabase")
      const { data: { session } } = await supabase.auth.getSession()
      if (session?.access_token) {
        const fallbackToken = session.access_token
        headers["Authorization"] = `Bearer ${fallbackToken}`
        // Update authStore with the token
        authStore.setState({ token: fallbackToken })
      }
    } catch (err) {
      console.error("❌ Failed to get token from Supabase session:", err)
    }
  }

  // Don't set Content-Type for FormData (browser will set it with boundary)
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json"
  }

  try {
    const fullUrl = `${API_BASE_URL}${endpoint}`
    
    // Add timeout to prevent hanging (configurable, default 30 seconds)
    // Use longer timeout for job status requests during long operations
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs)
    
    const response = await fetch(fullUrl, {
      ...options,
      headers,
      signal: controller.signal,
    })
    
    clearTimeout(timeoutId)

    if (!response.ok) {
      let errorMessage = "An error occurred"
      let retryable = false

      // Try to extract detailed error message from response
      let errorData: any = {}
      try {
        const contentType = response.headers.get("content-type")
        if (contentType?.includes("application/json")) {
          errorData = await response.json()
        }
      } catch (e) {
        // If JSON parsing fails, use empty object
        console.warn("Failed to parse error response as JSON:", e)
      }

      // FastAPI returns errors in 'detail' field, but also check 'error' and 'message' for compatibility
      errorMessage = errorData.detail || errorData.error || errorData.message || errorMessage

      if (response.status === 401) {
        console.error("❌ 401 Unauthorized error:", endpoint)
        
        // Clear auth state and redirect to login
        authStore.getState().logout()
        if (typeof window !== "undefined") {
          window.location.href = "/login"
        }
        throw new APIError(errorMessage || "Unauthorized", 401, false)
      }

      if (response.status === 429) {
        const retryAfter = response.headers.get("retry-after")
        errorMessage = errorMessage || `Too many requests. Please try again${retryAfter ? ` after ${retryAfter} seconds` : ""}`
        retryable = true
      } else if (response.status === 400) {
        errorMessage = errorMessage || "Invalid request. Please check your input."
        retryable = false
      } else if (response.status === 404) {
        errorMessage = errorMessage || "Resource not found."
        retryable = false
      } else if (response.status === 403) {
        errorMessage = errorMessage || "You don't have permission to perform this action."
        retryable = false
      } else if (response.status === 409) {
        errorMessage = errorMessage || "A conflicting operation is already in progress."
        retryable = true
      } else if (response.status === 402) {
        errorMessage = errorMessage || "Payment or budget limit exceeded."
        retryable = false
      } else if (response.status >= 500) {
        errorMessage = errorMessage || "Server error. Please try again later."
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
    // Handle abort (timeout)
    if (error instanceof Error && error.name === "AbortError") {
      console.error("❌ Request timeout:", endpoint)
      throw new APIError("Request timeout - server took too long to respond", 0, true)
    }
    console.error("❌ Request error:", endpoint, error)
    throw new APIError("Connection error", 0, true)
  }
}

export async function getModelAspectRatios(
  modelKey: string
): Promise<import("@/types/api").ModelAspectRatiosResponse> {
  // This is a public endpoint, use publicRequest without auth
  // Use 10 second timeout for metadata requests
  return publicRequest<import("@/types/api").ModelAspectRatiosResponse>(
    `/api/v1/models/${modelKey}/aspect-ratios`,
    { method: "GET" },
    10000 // 10 second timeout
  )
}

export async function uploadAudio(
  audioFile: File,
  userPrompt: string,
  stopAtStage: string | null = null,
  videoModel: string = "kling_v21",
  aspectRatio: string = "16:9"
): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("audio_file", audioFile)
  formData.append("user_prompt", userPrompt)
  if (stopAtStage) {
    formData.append("stop_at_stage", stopAtStage)
  }
  formData.append("video_model", videoModel)
  formData.append("aspect_ratio", aspectRatio)

  // Use longer timeout for upload (180 seconds = 3 minutes)
  // Backend has 150s timeout for storage upload, plus buffer for validation, DB ops, etc.
  return request<UploadResponse>(
    "/api/v1/upload-audio",
    {
      method: "POST",
      body: formData,
    },
    180000 // 3 minutes timeout
  )
}

export async function getJob(jobId: string): Promise<JobResponse> {
  // Use longer timeout for job status requests (5 minutes) to handle long uploads
  // The composer stage can take several minutes for large video uploads
  return request<JobResponse>(`/api/v1/jobs/${jobId}`, {}, 300000) // 5 minutes
}

export async function getJobClips(jobId: string): Promise<import("@/types/api").ClipListResponse> {
  // Use 10 second timeout for clips requests
  return request<import("@/types/api").ClipListResponse>(
    `/api/v1/jobs/${jobId}/clips`,
    { method: "GET" },
    10000 // 10 second timeout
  )
}

export async function regenerateClip(
  jobId: string,
  clipIndex: number,
  regenerationRequest: RegenerationRequest
): Promise<RegenerationResponse> {
  // Use 30 second timeout for regeneration requests (initial response)
  // Actual regeneration happens async with SSE events
  return request<RegenerationResponse>(
    `/api/v1/jobs/${jobId}/clips/${clipIndex}/regenerate`,
    {
      method: "POST",
      body: JSON.stringify(regenerationRequest),
    },
    30000 // 30 second timeout
  )
}

export async function downloadVideo(jobId: string): Promise<Blob> {
  const token = authStore.getState().token
  const headers: Record<string, string> = {}

  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }

  // First, get the signed download URL from the API
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

  // Parse the JSON response to get the download_url
  const data = await response.json()
  const downloadUrl = data.download_url

  if (!downloadUrl) {
    throw new APIError("Download URL not found in response", 500, false)
  }

  // Fetch the actual video file from the signed URL
  const videoResponse = await fetch(downloadUrl)

  if (!videoResponse.ok) {
    throw new APIError("Failed to download video file", videoResponse.status, true)
  }

  // Return the video blob
  return await videoResponse.blob()
}

