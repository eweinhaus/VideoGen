import { authStore } from "@/stores/authStore"
import {
  APIError,
  UploadResponse,
  JobResponse,
  RegenerationRequest,
  RegenerationResponse,
  StyleTransferOptions,
  SuggestionsResponse,
  MultiClipInstructionResponse,
} from "@/types/api"

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

      let errorData: any = {}
      try {
        const contentType = response.headers.get("content-type")
        if (contentType?.includes("application/json")) {
          errorData = await response.json().catch(() => ({}))
        }
      } catch (e) {
        // If JSON parsing fails, use empty object
      }

      if (response.status === 429) {
        const retryAfter = response.headers.get("retry-after")
        errorMessage = `Too many requests. Please try again${retryAfter ? ` after ${retryAfter} seconds` : ""}`
        retryable = true
      } else if (response.status === 400) {
        errorMessage = errorData.error || errorData.message || errorData.detail || "Validation error"
        retryable = false
      } else if (response.status >= 500) {
        errorMessage = errorData.detail || errorData.error || errorData.message || "Server error. Please try again later"
        retryable = true
      }

      // Extract detailed error information if available (for publicRequest)
      const errorDetails = errorData?.error_details
      throw new APIError(errorMessage, response.status, retryable, errorDetails)
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
      
      // Extract detailed error information if available
      const errorDetails = errorData.error_details

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

      throw new APIError(errorMessage, response.status, retryable, errorDetails)
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

export async function getJob(jobId: string, timeoutMs: number = 300000): Promise<JobResponse> {
  // Default to longer timeout for job status requests (5 minutes) to handle long uploads
  // The composer stage can take several minutes for large video uploads
  // But allow caller to override with shorter timeout for initial fetches
  return request<JobResponse>(`/api/v1/jobs/${jobId}`, {}, timeoutMs)
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

export async function transferStyle(
  jobId: string,
  sourceClipIndex: number,
  targetClipIndex: number,
  transferOptions: StyleTransferOptions,
  additionalInstruction?: string
): Promise<RegenerationResponse> {
  return request<RegenerationResponse>(
    `/api/v1/jobs/${jobId}/clips/style-transfer`,
    {
      method: "POST",
      body: JSON.stringify({
        source_clip_index: sourceClipIndex,
        target_clip_index: targetClipIndex,
        transfer_options: transferOptions,
        additional_instruction: additionalInstruction,
      }),
    },
    30000
  )
}

export async function getSuggestions(
  jobId: string,
  clipIndex: number
): Promise<SuggestionsResponse> {
  return request<SuggestionsResponse>(
    `/api/v1/jobs/${jobId}/clips/${clipIndex}/suggestions`,
    {
      method: "GET",
    },
    10000
  )
}

export async function applySuggestion(
  jobId: string,
  clipIndex: number,
  suggestionId: string
): Promise<RegenerationResponse> {
  return request<RegenerationResponse>(
    `/api/v1/jobs/${jobId}/clips/${clipIndex}/suggestions/${suggestionId}/apply`,
    {
      method: "POST",
    },
    30000
  )
}

export async function parseMultiClipInstruction(
  jobId: string,
  instruction: string
): Promise<MultiClipInstructionResponse> {
  return request<MultiClipInstructionResponse>(
    `/api/v1/jobs/${jobId}/clips/multi-clip-instruction`,
    {
      method: "POST",
      body: JSON.stringify({ instruction }),
    },
    10000
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

export interface ClipComparisonResponse {
  original: {
    video_url: string | null
    thumbnail_url: string | null
    prompt: string
    version_number: number
    duration: number
    user_instruction?: string | null
    cost?: number | null
  }
  regenerated: {
    video_url: string | null
    thumbnail_url: string | null
    prompt: string
    version_number: number
    duration: number
    user_instruction?: string | null
    cost?: number | null
  }
  duration_mismatch: boolean
  duration_diff: number
}

export async function getClipComparison(
  jobId: string,
  clipIndex: number,
  originalVersion?: number,
  regeneratedVersion?: number
): Promise<ClipComparisonResponse> {
  const params = new URLSearchParams()
  if (originalVersion !== undefined) {
    params.append("original_version", originalVersion.toString())
  }
  if (regeneratedVersion !== undefined) {
    params.append("regenerated_version", regeneratedVersion.toString())
  }
  
  const queryString = params.toString()
  const url = `/api/v1/jobs/${jobId}/clips/${clipIndex}/versions/compare${queryString ? `?${queryString}` : ""}`
  
  return request<ClipComparisonResponse>(url, { method: "GET" }, 10000)
}

export interface JobAnalyticsResponse {
  job_id: string
  total_regenerations: number
  success_rate: number
  average_cost: number
  most_common_modifications: Array<{
    instruction: string
    count: number
  }>
  average_time_seconds: number | null
}

export async function getJobAnalytics(jobId: string): Promise<JobAnalyticsResponse> {
  return request<JobAnalyticsResponse>(
    `/api/v1/jobs/${jobId}/analytics`,
    { method: "GET" },
    5000
  )
}

export interface UserAnalyticsResponse {
  user_id: string
  total_regenerations: number
  most_used_templates: Array<{
    template_id: string
    count: number
  }>
  success_rate: number
  total_cost: number
  average_cost_per_regeneration: number
  average_iterations_per_clip: number
}

export async function getUserAnalytics(userId: string): Promise<UserAnalyticsResponse> {
  return request<UserAnalyticsResponse>(
    `/api/v1/users/${userId}/analytics`,
    { method: "GET" },
    5000
  )
}

export async function exportJobAnalytics(jobId: string): Promise<Blob> {
  const token = authStore.getState().token
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
  
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  
  const fullUrl = `${API_BASE_URL}/api/v1/jobs/${jobId}/analytics/export`
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), 10000)
  
  try {
    const response = await fetch(fullUrl, {
      method: "GET",
      headers,
      signal: controller.signal,
    })
    
    clearTimeout(timeoutId)
    
    if (!response.ok) {
      throw new APIError("Failed to export analytics", response.status, false)
    }
    
    return await response.blob()
  } catch (error) {
    clearTimeout(timeoutId)
    if (error instanceof APIError) {
      throw error
    }
    throw new APIError("Failed to export analytics", 500, false)
  }
}

