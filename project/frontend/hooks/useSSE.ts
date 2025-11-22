"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import type { SSEHandlers } from "@/types/sse"
import { authStore } from "@/stores/authStore"

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
const MAX_RECONNECT_ATTEMPTS = 5

export function useSSE(
  jobId: string | null,
  handlers: SSEHandlers
): {
  isConnected: boolean
  error: string | null
  reconnect: () => void
  close: () => void
} {
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const lastErrorTimeRef = useRef<number | null>(null) // Track when errors occur to detect 503-like issues
  // Store handlers in ref to prevent re-connections when handlers change
  const handlersRef = useRef<SSEHandlers>(handlers)
  
  // Update handlers ref when they change (but don't trigger re-connection)
  useEffect(() => {
    handlersRef.current = handlers
  }, [handlers])

  const close = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    setIsConnected(false)
  }, [])

  const connect = useCallback(() => {
    if (!jobId) return

    close()

    // EventSource doesn't support custom headers, so we pass token as query parameter
    const authState = authStore.getState()
    const token = authState.token
    
    if (!token) {
      // Try to get session from Supabase directly (use static import to avoid multiple instances)
      import("@/lib/supabase").then((module) => {
        // Use the same supabase instance from the module
        module.supabase.auth.getSession().then(({ data: { session } }) => {
          if (session?.access_token) {
            authStore.setState({ token: session.access_token })
            // Retry connection with new token
            setTimeout(() => connect(), 100)
          }
        })
      })
      return // Don't connect without token
    }
    
    const url = `${API_BASE_URL}/api/v1/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`
    
    const eventSource = new EventSource(url, { withCredentials: true })

    eventSource.onopen = () => {
      setIsConnected(true)
      setError(null)
      reconnectAttemptsRef.current = 0
    }

    eventSource.onerror = (error) => {
      console.error("❌ SSE connection error:", error, "for job:", jobId)
      setIsConnected(false)
      eventSource.close()

      const now = Date.now()
      const lastErrorTime = lastErrorTimeRef.current
      // If errors occur very quickly (within 2 seconds), likely a 503 (connection limit)
      // Use longer delays for suspected 503 errors
      const isLikely503 = lastErrorTime && (now - lastErrorTime) < 2000
      lastErrorTimeRef.current = now

      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        // Use longer delays for suspected 503 errors (connection limit issues)
        // Base delay: 2s, 4s, 8s, 16s, 32s
        // For 503-like errors: 5s, 10s, 20s, 40s, 80s
        const baseDelay = Math.pow(2, reconnectAttemptsRef.current) * 1000
        const delay = isLikely503 ? baseDelay * 2.5 : baseDelay
        reconnectAttemptsRef.current++
        
        console.log(
          `⏳ SSE reconnecting in ${(delay / 1000).toFixed(1)}s (attempt ${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})${isLikely503 ? ' [suspected 503 - using longer delay]' : ''}`
        )
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect()
        }, delay)
      } else {
        console.error("❌ SSE connection failed after maximum attempts - falling back to polling")
        setError("Connection failed after multiple attempts - using polling fallback")
      }
    }

    // Register event listeners - use handlersRef to get latest handlers without re-creating connection
    eventSource.addEventListener("stage_update", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onStageUpdate?.(data)
      } catch (err) {
        console.error("❌ Failed to parse stage_update event:", err, "Raw data:", e.data)
      }
    })

    eventSource.addEventListener("progress", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onProgress?.(data)
      } catch (err) {
        console.error("Failed to parse progress event:", err)
      }
    })

    eventSource.addEventListener("message", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onMessage?.(data)
      } catch (err) {
        console.error("Failed to parse message event:", err)
      }
    })

    eventSource.addEventListener("cost_update", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onCostUpdate?.(data)
      } catch (err) {
        console.error("Failed to parse cost_update event:", err)
      }
    })

    eventSource.addEventListener("completed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onCompleted?.(data)
        // Don't close immediately - wait a bit to ensure all events are received
        setTimeout(() => close(), 2000)
      } catch (err) {
        console.error("Failed to parse completed event:", err)
      }
    })

    eventSource.addEventListener("error", (e: MessageEvent) => {
      try {
        // Only parse if data exists and is not empty
        if (e.data && typeof e.data === 'string' && e.data.trim() !== '') {
          const data = JSON.parse(e.data)
          handlersRef.current.onError?.(data)
        } else {
          // No data in error event - this is likely a connection error (handled by onerror)
          // Don't try to parse undefined/empty data
          console.debug("Error event received without data (likely connection error)")
        }
      } catch (err) {
        // If parsing fails, it might be a connection error
        console.error("Failed to parse error event:", err, "Data:", e.data)
      }
    })

    eventSource.addEventListener("audio_parser_results", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onAudioParserResults?.(data)
      } catch (err) {
        console.error("Failed to parse audio_parser_results event:", err)
      }
    })

    eventSource.addEventListener("scene_planner_results", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onScenePlannerResults?.(data)
      } catch (err) {
        console.error("Failed to parse scene_planner_results event:", err)
      }
    })

    eventSource.addEventListener("prompt_generator_results", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onPromptGeneratorResults?.(data)
      } catch (err) {
        console.error("Failed to parse prompt_generator_results event:", err)
      }
    })
    eventSource.addEventListener("video_generation_start", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onVideoGenerationStart?.(data)
      } catch (err) {
        console.error("Failed to parse video_generation_start event:", err)
      }
    })
    eventSource.addEventListener("video_generation_complete", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onVideoGenerationComplete?.(data)
      } catch (err) {
        console.error("Failed to parse video_generation_complete event:", err)
      }
    })
    eventSource.addEventListener("video_generation_failed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onVideoGenerationFailed?.(data)
      } catch (err) {
        console.error("Failed to parse video_generation_failed event:", err)
      }
    })
    eventSource.addEventListener("video_generation_retry", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onVideoGenerationRetry?.(data)
      } catch (err) {
        console.error("Failed to parse video_generation_retry event:", err)
      }
    })

    eventSource.addEventListener("reference_generation_start", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onReferenceGenerationStart?.(data)
      } catch (err) {
        console.error("Failed to parse reference_generation_start event:", err)
      }
    })

    eventSource.addEventListener("reference_generation_complete", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onReferenceGenerationComplete?.(data)
      } catch (err) {
        console.error("Failed to parse reference_generation_complete event:", err)
      }
    })

    eventSource.addEventListener("reference_generation_failed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onReferenceGenerationFailed?.(data)
      } catch (err) {
        console.error("Failed to parse reference_generation_failed event:", err)
      }
    })

    eventSource.addEventListener("reference_generation_retry", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onReferenceGenerationRetry?.(data)
      } catch (err) {
        console.error("Failed to parse reference_generation_retry event:", err)
      }
    })

    eventSource.addEventListener("regeneration_started", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onRegenerationStarted?.(data)
      } catch (err) {
        console.error("Failed to parse regeneration_started event:", err)
      }
    })

    eventSource.addEventListener("template_matched", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onTemplateMatched?.(data)
      } catch (err) {
        console.error("Failed to parse template_matched event:", err)
      }
    })

    eventSource.addEventListener("prompt_modified", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onPromptModified?.(data)
      } catch (err) {
        console.error("Failed to parse prompt_modified event:", err)
      }
    })

    eventSource.addEventListener("video_generating", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onVideoGenerating?.(data)
      } catch (err) {
        console.error("Failed to parse video_generating event:", err)
      }
    })

    eventSource.addEventListener("regeneration_complete", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onRegenerationComplete?.(data)
      } catch (err) {
        console.error("Failed to parse regeneration_complete event:", err)
      }
    })

    eventSource.addEventListener("regeneration_failed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onRegenerationFailed?.(data)
      } catch (err) {
        console.error("Failed to parse regeneration_failed event:", err)
      }
    })

    eventSource.addEventListener("recomposition_started", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onRecompositionStarted?.(data)
      } catch (err) {
        console.error("Failed to parse recomposition_started event:", err)
      }
    })

    eventSource.addEventListener("recomposition_complete", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onRecompositionComplete?.(data)
      } catch (err) {
        console.error("Failed to parse recomposition_complete event:", err)
      }
    })

    eventSource.addEventListener("recomposition_failed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlersRef.current.onRecompositionFailed?.(data)
      } catch (err) {
        console.error("Failed to parse recomposition_failed event:", err)
      }
    })

    eventSourceRef.current = eventSource
  }, [jobId, close])

  useEffect(() => {
    if (jobId && !eventSourceRef.current) {
      connect()
    }

    return () => {
      close()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]) // Only depend on jobId, connect/close are stable callbacks

  const reconnect = useCallback(() => {
    reconnectAttemptsRef.current = 0
    connect()
  }, [connect])

  return {
    isConnected,
    error,
    reconnect,
    close,
  }
}

