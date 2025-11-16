import { authStore } from "@/stores/authStore"
import { APIError, UploadResponse, JobResponse } from "@/types/api"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

// Debug: Log API base URL (only in browser)
if (typeof window !== "undefined") {
  console.log("🔧 API_BASE_URL:", API_BASE_URL)
  console.log("🔧 NEXT_PUBLIC_API_URL env:", process.env.NEXT_PUBLIC_API_URL)
}

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
    console.log("Sending request with token:", endpoint, "Token:", token.substring(0, 20) + "...")
  } else {
    // Try to get token from Supabase session as fallback (similar to SSE)
    try {
      const { supabase } = await import("@/lib/supabase")
      const { data: { session } } = await supabase.auth.getSession()
      if (session?.access_token) {
        const fallbackToken = session.access_token
        console.log("✅ Found token in Supabase session, using for request")
        headers["Authorization"] = `Bearer ${fallbackToken}`
        // Update authStore with the token
        authStore.setState({ token: fallbackToken })
      } else {
        // Debug: Log when token is missing
        console.error("❌ No auth token found for request to:", endpoint)
        console.error("Auth store state:", {
          user: authStore.getState().user?.email,
          hasToken: !!authStore.getState().token,
          isLoading: authStore.getState().isLoading
        })
        // Don't throw error here - let the API handle 401
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
    // Debug: Log full URL being requested
    if (typeof window !== "undefined") {
      console.log("🌐 Making request to:", fullUrl)
    }
    
    // Add timeout to prevent hanging (30 seconds)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 30000)
    
    const response = await fetch(fullUrl, {
      ...options,
      headers,
      signal: controller.signal,
    })
    
    clearTimeout(timeoutId)

    if (!response.ok) {
      let errorMessage = "An error occurred"
      let retryable = false

      if (response.status === 401) {
        // Log the error response for debugging
        const errorData = await response.json().catch(() => ({}))
        console.error("❌ 401 Unauthorized error:", errorData)
        console.error("Request endpoint:", endpoint)
        console.error("Token was:", token ? `${token.substring(0, 20)}...` : "missing")
        
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
        errorMessage = data.error || data.message || "Validation error"
        // Log validation errors for debugging
        console.error("❌ Validation error:", {
          error: data.error,
          code: data.code,
          message: data.message,
          fullResponse: data
        })
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

export async function uploadAudio(
  audioFile: File,
  userPrompt: string,
  stopAtStage: string | null = null
): Promise<UploadResponse> {
  const formData = new FormData()
  formData.append("audio_file", audioFile)
  formData.append("user_prompt", userPrompt)
  if (stopAtStage) {
    formData.append("stop_at_stage", stopAtStage)
  }

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

