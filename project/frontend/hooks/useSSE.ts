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
    
    // Always log the auth state for debugging
    console.log("🔍 SSE Connection Debug:", {
      jobId,
      hasToken: !!token,
      tokenLength: token?.length || 0,
      userEmail: authState.user?.email,
      tokenPreview: token ? `${token.substring(0, 20)}...` : "null"
    })
    
    if (!token) {
      console.error("❌ No token found in authStore for SSE connection!")
      console.error("Full auth state:", authState)
      // Try to get session from Supabase directly
      import("@/lib/supabase").then(({ supabase }) => {
        supabase.auth.getSession().then(({ data: { session } }) => {
          if (session?.access_token) {
            console.log("✅ Found token in Supabase session, updating authStore")
            authStore.setState({ token: session.access_token })
            // Retry connection with new token
            setTimeout(() => connect(), 100)
          } else {
            console.error("❌ No session found in Supabase either")
          }
        })
      })
      return // Don't connect without token
    }
    
    const url = `${API_BASE_URL}/api/v1/jobs/${jobId}/stream?token=${encodeURIComponent(token)}`
    console.log("✅ SSE connecting with token:", url.substring(0, 120) + "...")
    
    const eventSource = new EventSource(url, { withCredentials: true })

    eventSource.onopen = () => {
      setIsConnected(true)
      setError(null)
      reconnectAttemptsRef.current = 0
    }

    eventSource.onerror = () => {
      setIsConnected(false)
      eventSource.close()

      if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = Math.pow(2, reconnectAttemptsRef.current) * 1000 // 2s, 4s, 8s, 16s, 32s
        reconnectAttemptsRef.current++

        reconnectTimeoutRef.current = setTimeout(() => {
          connect()
        }, delay)
      } else {
        setError("Connection failed after multiple attempts")
      }
    }

    // Register event listeners
    eventSource.addEventListener("stage_update", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlers.onStageUpdate?.(data)
      } catch (err) {
        console.error("Failed to parse stage_update event:", err)
      }
    })

    eventSource.addEventListener("progress", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlers.onProgress?.(data)
      } catch (err) {
        console.error("Failed to parse progress event:", err)
      }
    })

    eventSource.addEventListener("message", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlers.onMessage?.(data)
      } catch (err) {
        console.error("Failed to parse message event:", err)
      }
    })

    eventSource.addEventListener("cost_update", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlers.onCostUpdate?.(data)
      } catch (err) {
        console.error("Failed to parse cost_update event:", err)
      }
    })

    eventSource.addEventListener("completed", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlers.onCompleted?.(data)
        // Don't close immediately - wait a bit to ensure all events are received
        setTimeout(() => close(), 2000)
      } catch (err) {
        console.error("Failed to parse completed event:", err)
      }
    })

    eventSource.addEventListener("error", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlers.onError?.(data)
      } catch (err) {
        // If parsing fails, it might be a connection error
        console.error("Failed to parse error event:", err)
      }
    })

    eventSource.addEventListener("audio_parser_results", (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data)
        handlers.onAudioParserResults?.(data)
      } catch (err) {
        console.error("Failed to parse audio_parser_results event:", err)
      }
    })

    eventSourceRef.current = eventSource
  }, [jobId, handlers, close])

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

