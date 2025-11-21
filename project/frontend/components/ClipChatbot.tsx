"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import Image from "next/image"
import { regenerateClip, getJobClips, getClipComparison, revertClipToVersion } from "@/lib/api"
import { useSSE } from "@/hooks/useSSE"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { FloatingChat } from "@/components/ui/floating-chat"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Progress } from "@/components/ui/progress"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { ClipComparison } from "@/components/ClipComparison"
import { APIError } from "@/types/api"
import { GitCompare } from "lucide-react"
import type {
  RegenerationStartedEvent,
  TemplateMatchedEvent,
  PromptModifiedEvent,
  VideoGeneratingEvent,
  RecompositionStartedEvent,
  RecompositionCompleteEvent,
  RecompositionFailedEvent,
  RegenerationCompleteEvent,
  RegenerationFailedEvent,
} from "@/types/sse"
import { cn } from "@/lib/utils"

// Format timestamp in seconds to "M:SS" format
function formatTimestamp(seconds: number): string {
  const roundedSeconds = Math.round(seconds)
  const mins = Math.floor(roundedSeconds / 60)
  const secs = roundedSeconds % 60
  return `${mins}:${secs.toString().padStart(2, "0")}`
}

interface Message {
  role: "user" | "assistant" | "system"
  content: string
  timestamp: Date
  type?: "info" | "warning" | "error" | "success"
  attachedClipIndex?: number
  thumbnailUrl?: string | null
}

interface ClipData {
  clip_index: number
  thumbnail_url: string | null
  timestamp_start: number
  timestamp_end: number
  duration: number
}

interface ClipChatbotProps {
  jobId: string
  onRegenerationComplete?: (newVideoUrl: string) => void
  audioUrl?: string | null
  // NEW: Shared clip selection state (synchronized with main ClipSelector)
  selectedClipIndex?: number
  onClipSelect?: (clipIndex: number, timestamp?: number) => void
}

export function ClipChatbot({
  jobId,
  onRegenerationComplete,
  audioUrl,
  selectedClipIndex: externalSelectedClipIndex,
  onClipSelect,
}: ClipChatbotProps) {
  // Generate unique storage key for this job (unified chat)
  const storageKey = `clip_chat_${jobId}`
  const conversationHistoryKey = `clip_chat_history_${jobId}`
  const selectedClipsKey = `clip_chat_selected_clips_${jobId}`
  const comparisonStateKey = `clip_chat_comparison_${jobId}`
  
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState("")
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [lastError, setLastError] = useState<string | null>(null)
  const [isRetryable, setIsRetryable] = useState(false)
  const [costEstimate, setCostEstimate] = useState<number | null>(null)
  const [progress, setProgress] = useState<number | null>(null)
  const [templateMatched, setTemplateMatched] = useState<string | null>(null)
  const [lastInstruction, setLastInstruction] = useState<string | null>(null)
  const [lastClipIndices, setLastClipIndices] = useState<number[]>([])
  const [clips, setClips] = useState<ClipData[]>([])
  const [selectedClipIndices, setSelectedClipIndices] = useState<number[]>([])
  const [loadingClips, setLoadingClips] = useState(true)
  
  // Sync external selection with internal selection
  // When parent changes selection (e.g., from main ClipSelector), update internal state
  useEffect(() => {
    if (externalSelectedClipIndex !== undefined) {
      // Check if this clip is already selected in our array
      if (!selectedClipIndices.includes(externalSelectedClipIndex)) {
        // Replace selection with just this clip (single selection from parent)
        setSelectedClipIndices([externalSelectedClipIndex])
        saveSelectedClips([externalSelectedClipIndex])
      }
    }
  }, [externalSelectedClipIndex])
  
  // Sync internal selection with parent
  // When internal selection changes, notify parent of the first selected clip
  useEffect(() => {
    if (onClipSelect && selectedClipIndices.length > 0) {
      const firstSelectedClip = clips.find(c => c.clip_index === selectedClipIndices[0])
      if (firstSelectedClip) {
        // Notify parent of selection change with timestamp for video seeking
        onClipSelect(firstSelectedClip.clip_index, firstSelectedClip.timestamp_start)
      }
    }
  }, [selectedClipIndices, clips, onClipSelect])
  const [showComparison, setShowComparison] = useState(false)
  const [comparisonData, setComparisonData] = useState<{
    original: any
    regenerated: any | null
    clip_start_time?: number | null
    clip_end_time?: number | null
  } | null>(null)
  const [loadingComparison, setLoadingComparison] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const conversationHistoryRef = useRef<Array<{ role: string; content: string }>>([])
  const isInitializedRef = useRef(false)
  const isRestoringRef = useRef(false)
  const hasRestoredMessagesRef = useRef(false)

  // Save selected clip indices to localStorage
  const saveSelectedClips = useCallback((clipIndices: number[]) => {
    if (!isInitializedRef.current) return
    try {
      if (clipIndices.length === 0) {
        localStorage.removeItem(selectedClipsKey)
      } else {
        localStorage.setItem(selectedClipsKey, JSON.stringify(clipIndices))
      }
    } catch (err) {
      console.error("Failed to save selected clips:", err)
    }
  }, [selectedClipsKey])

  // Restore selected clip indices from localStorage
  const getPersistedSelectedClips = useCallback((): number[] => {
    try {
      const saved = localStorage.getItem(selectedClipsKey)
      if (saved !== null) {
        return JSON.parse(saved)
      }
    } catch (err) {
      console.error("Failed to restore selected clips:", err)
    }
    return []
  }, [selectedClipsKey])

  // Save comparison state to localStorage
  const saveComparisonState = useCallback((show: boolean, data: { original: any; regenerated: any | null } | null) => {
    if (!isInitializedRef.current) return
    try {
      if (!show || !data) {
        localStorage.removeItem(comparisonStateKey)
      } else {
        localStorage.setItem(comparisonStateKey, JSON.stringify({
          show,
          data,
          clipIndex: selectedClipIndices[0] // Use first selected clip for comparison
        }))
      }
    } catch (err) {
      console.error("Failed to save comparison state:", err)
    }
  }, [comparisonStateKey, selectedClipIndices])

  // Restore comparison state from localStorage
  const getPersistedComparisonState = useCallback((): { show: boolean; data: { original: any; regenerated: any | null } | null; clipIndex: number | null } | null => {
    try {
      const saved = localStorage.getItem(comparisonStateKey)
      if (saved !== null) {
        return JSON.parse(saved)
      }
    } catch (err) {
      console.error("Failed to restore comparison state:", err)
    }
    return null
  }, [comparisonStateKey])

  // Load clips on mount - always refetch (never cache thumbnails)
  useEffect(() => {
    let mounted = true

    async function fetchClips() {
      try {
        setLoadingClips(true)
        const response = await getJobClips(jobId)
        if (mounted) {
          setClips(response.clips)
          setLoadingClips(false)
          
          // Restore persisted selected clip indices if they exist
          const persistedIndices = getPersistedSelectedClips()
          if (persistedIndices.length > 0) {
            // Validate that all selected clips still exist
            const validIndices = persistedIndices.filter(index =>
              response.clips.some(c => c.clip_index === index)
            )
            if (validIndices.length > 0) {
              setSelectedClipIndices(validIndices)
            } else {
              // No valid clips, clear selection
              setSelectedClipIndices([])
              saveSelectedClips([])
            }
          }
        }
      } catch (err) {
        console.error("Failed to fetch clips:", err)
        if (mounted) {
          setLoadingClips(false)
        }
      }
    }

    fetchClips()

    return () => {
      mounted = false
    }
  }, [jobId, getPersistedSelectedClips, saveSelectedClips])

  // Load messages and conversation history from localStorage on mount or when jobId changes
  useEffect(() => {
    // Reset initialization flag when jobId changes
    isInitializedRef.current = false
    hasRestoredMessagesRef.current = false
    
    console.log(`[ClipChatbot] Loading messages for jobId: ${jobId}, storageKey: ${storageKey}`)
    
    try {
      // Load messages - verify the data exists and is valid
      const savedMessages = localStorage.getItem(storageKey)
      console.log(`[ClipChatbot] Found saved messages in localStorage:`, savedMessages ? `${savedMessages.length} chars` : 'none')
      
      if (savedMessages) {
        try {
          const parsed = JSON.parse(savedMessages)
          console.log(`[ClipChatbot] Parsed messages:`, Array.isArray(parsed) ? `${parsed.length} messages` : 'not an array')
          
          // Verify it's an array
          if (Array.isArray(parsed) && parsed.length > 0) {
            // Convert timestamp strings back to Date objects
            const restoredMessages: Message[] = parsed.map((msg: any) => {
              // Handle both Date objects (if somehow still serialized) and ISO strings
              let timestamp: Date
              if (msg.timestamp instanceof Date) {
                timestamp = msg.timestamp
              } else if (typeof msg.timestamp === "string") {
                timestamp = new Date(msg.timestamp)
              } else {
                // Fallback to current date if timestamp is invalid
                console.warn("[ClipChatbot] Invalid timestamp in message, using current date:", msg)
                timestamp = new Date()
              }
              
              return {
                ...msg,
                timestamp,
              }
            })
            
            // Only set messages if we successfully parsed them
            if (restoredMessages.length > 0) {
              console.log(`[ClipChatbot] Restoring ${restoredMessages.length} messages from localStorage`)
              hasRestoredMessagesRef.current = true
              setMessages(restoredMessages)
              console.log(`[ClipChatbot] Successfully restored ${restoredMessages.length} messages`)
            } else {
              console.warn("[ClipChatbot] Parsed messages array was empty, starting fresh")
              hasRestoredMessagesRef.current = false
              setMessages([])
            }
          } else {
            console.warn(`[ClipChatbot] Saved messages is not a valid array (type: ${typeof parsed}, length: ${Array.isArray(parsed) ? parsed.length : 'N/A'}), starting fresh`)
            setMessages([])
          }
        } catch (parseErr) {
          console.error("[ClipChatbot] Failed to parse saved messages:", parseErr)
          // Try to recover by checking if it's corrupted JSON
          setMessages([])
        }
      } else {
        // No saved messages - start fresh
        console.log(`[ClipChatbot] No saved messages found for jobId: ${jobId}, starting fresh`)
        setMessages([])
      }

      // Load conversation history
      const savedHistory = localStorage.getItem(conversationHistoryKey)
      if (savedHistory) {
        try {
          const parsed = JSON.parse(savedHistory)
          if (Array.isArray(parsed)) {
            conversationHistoryRef.current = parsed
            console.log(`Restored ${parsed.length} conversation history entries`)
          } else {
            console.warn("Saved conversation history is not a valid array, starting fresh")
            conversationHistoryRef.current = []
          }
        } catch (parseErr) {
          console.error("Failed to parse conversation history:", parseErr)
          conversationHistoryRef.current = []
        }
      } else {
        // No saved history - start fresh
        conversationHistoryRef.current = []
      }

      // Clear comparison state when jobId changes (new job = new state)
      localStorage.removeItem(comparisonStateKey)
      setShowComparison(false)
      setComparisonData(null)
    } catch (err) {
      console.error("Failed to load chat history from localStorage:", err)
      // Silently fail - start with empty chat
      setMessages([])
      conversationHistoryRef.current = []
    }
    
    // Set initialization flag to true AFTER all restoration is complete
    // Use requestAnimationFrame to ensure DOM updates are processed first
    requestAnimationFrame(() => {
      isInitializedRef.current = true
      console.log(`[ClipChatbot] Initialization complete for jobId: ${jobId}`)
    })
  }, [jobId, storageKey, conversationHistoryKey, comparisonStateKey])

  // Restore selected clip indices on mount (if not already set by clip fetch)
  // This is handled in the clip fetch useEffect, but this is a fallback
  useEffect(() => {
    if (selectedClipIndices.length === 0 && clips.length > 0 && isInitializedRef.current) {
      const persistedIndices = getPersistedSelectedClips()
      if (persistedIndices.length > 0) {
        const validIndices = persistedIndices.filter(index =>
          clips.some(c => c.clip_index === index)
        )
        if (validIndices.length > 0) {
          setSelectedClipIndices(validIndices)
        }
      }
    }
  }, [clips, selectedClipIndices, getPersistedSelectedClips])

  // Save selected clip indices when they change
  useEffect(() => {
    if (isInitializedRef.current) {
      saveSelectedClips(selectedClipIndices)
    }
  }, [selectedClipIndices, saveSelectedClips])

  // Restore comparison state on mount (after clips are loaded) or when selected clips change
  useEffect(() => {
    if (!isInitializedRef.current || clips.length === 0 || loadingClips) return
    
    isRestoringRef.current = true
    
    try {
      const persisted = getPersistedComparisonState()
      if (persisted && persisted.clipIndex !== null) {
        // Verify the clip still exists
        const clipExists = clips.some(c => c.clip_index === persisted.clipIndex)
        if (clipExists && selectedClipIndices.includes(persisted.clipIndex) && persisted.show && persisted.data) {
          // Restore comparison state if the selected clip matches
          setComparisonData(persisted.data)
          setShowComparison(true)
        } else if (!selectedClipIndices.includes(persisted.clipIndex)) {
          // Clear comparison state if clip doesn't match
          setShowComparison(false)
          setComparisonData(null)
          // Manually clear localStorage to avoid triggering save effect
          localStorage.removeItem(comparisonStateKey)
        }
      }
    } catch (err) {
      console.error("Failed to restore comparison state:", err)
    } finally {
      // Reset restoring flag after state updates complete
      // Use requestAnimationFrame to ensure state updates are processed first
      requestAnimationFrame(() => {
        isRestoringRef.current = false
      })
    }
  }, [clips, loadingClips, selectedClipIndices, getPersistedComparisonState, comparisonStateKey])

  // Save comparison state when it changes (but skip if we're in the middle of restoring)
  useEffect(() => {
    if (!isInitializedRef.current || isRestoringRef.current) return
    saveComparisonState(showComparison, comparisonData)
  }, [showComparison, comparisonData, saveComparisonState])

  // Save messages to localStorage whenever they change
  useEffect(() => {
    // Skip saving if not initialized (prevents saving during initial restore)
    if (!isInitializedRef.current) {
      console.log(`[ClipChatbot] Skipping save - not initialized yet. Messages count: ${messages.length}`)
      return
    }
    
    // Don't save empty messages array (but allow saving if messages exist)
    // UNLESS we just restored messages and they're now empty (which means they were cleared after restore)
    if (messages.length === 0) {
      // If we had restored messages but now they're empty, log a warning
      if (hasRestoredMessagesRef.current) {
        console.warn(`[ClipChatbot] Messages were restored but are now empty - this might indicate a problem`)
      }
      console.log(`[ClipChatbot] Skipping save - messages array is empty`)
      return
    }
    
    // If we successfully restored messages and they still exist, mark that we've saved them
    if (hasRestoredMessagesRef.current && messages.length > 0) {
      console.log(`[ClipChatbot] Saving restored messages (${messages.length} messages)`)
      hasRestoredMessagesRef.current = false // Reset flag after first save after restore
    }
    
    try {
      console.log(`[ClipChatbot] Saving ${messages.length} messages to localStorage`)
      
      // Convert Date objects to ISO strings for storage
      const messagesToSave = messages.map((msg) => ({
        ...msg,
        timestamp: msg.timestamp.toISOString(),
      }))
      const serialized = JSON.stringify(messagesToSave)
      
      // Check if we're about to exceed localStorage quota (typical limit is ~5-10MB)
      // If serialized data is too large, try to keep only the most recent messages
      if (serialized.length > 4 * 1024 * 1024) { // 4MB threshold (leave room for other data)
        console.warn("[ClipChatbot] Chat history is large, keeping only the most recent messages")
        // Keep the last 100 messages to prevent quota issues
        const recentMessages = messagesToSave.slice(-100)
        const truncatedSerialized = JSON.stringify(recentMessages)
        localStorage.setItem(storageKey, truncatedSerialized)
        console.log(`[ClipChatbot] Truncated chat history from ${messagesToSave.length} to ${recentMessages.length} messages`)
      } else {
        localStorage.setItem(storageKey, serialized)
        console.log(`[ClipChatbot] Successfully saved ${messages.length} messages to localStorage (${serialized.length} bytes)`)
      }
    } catch (err: any) {
      // Handle quota exceeded error specifically
      if (err?.name === "QuotaExceededError" || err?.code === 22) {
        console.warn("localStorage quota exceeded, attempting to keep only recent messages")
        try {
          // Try saving only the most recent 50 messages
          const recentMessages = messages.slice(-50).map((msg) => ({
            ...msg,
            timestamp: msg.timestamp.toISOString(),
          }))
          localStorage.setItem(storageKey, JSON.stringify(recentMessages))
          console.log(`Successfully saved ${recentMessages.length} recent messages after quota error`)
        } catch (retryErr) {
          console.error("Failed to save messages even after truncation:", retryErr)
        }
      } else {
        console.error("Failed to save messages to localStorage:", err)
      }
    }
  }, [messages, storageKey])

  // Helper function to save conversation history
  const saveConversationHistory = () => {
    if (!isInitializedRef.current) return
    
    try {
      localStorage.setItem(conversationHistoryKey, JSON.stringify(conversationHistoryRef.current))
    } catch (err) {
      console.error("Failed to save conversation history to localStorage:", err)
      // Silently fail - chat will continue to work, just won't persist
    }
  }


  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // SSE handlers for regeneration events
  const { isConnected } = useSSE(jobId, {
    onRegenerationStarted: (data: RegenerationStartedEvent) => {
      setProgress(5)
      addSystemMessage("Regeneration started...", "info")
    },
    onTemplateMatched: (data: TemplateMatchedEvent) => {
      setTemplateMatched(data.template_id)
      setProgress(10)
      addSystemMessage(`Template matched: ${data.template_id}`, "info")
    },
    onPromptModified: (data: PromptModifiedEvent) => {
      setProgress(15)
      if (data.template_used) {
        addSystemMessage("Template transformation applied", "info")
      } else {
        addSystemMessage("Prompt modified using AI", "info")
      }
    },
    onVideoGenerating: (data: VideoGeneratingEvent) => {
      // Progress range: 10-60% for video generation
      const videoProgress = 10 + (data.progress / 100) * 50
      setProgress(videoProgress)
    },
    onRecompositionStarted: (data: RecompositionStartedEvent) => {
      setProgress(data.progress) // Start at 60%
      addSystemMessage("Recomposing video with updated clip...", "info")
    },
    onRecompositionComplete: (data: RecompositionCompleteEvent) => {
      setProgress(100)
      const durationText = data.duration != null ? `${data.duration.toFixed(1)}s` : "complete"
      addSystemMessage(`Video recomposition complete! Duration: ${durationText}`, "success")
      // Final completion will be handled by regeneration_complete
    },
    onRecompositionFailed: (data: RecompositionFailedEvent) => {
      setIsProcessing(false)
      setProgress(null)
      setError(data.error)
      setLastError(data.error)
      setIsRetryable(data.retryable ?? false)
      addSystemMessage(`Recomposition failed: ${data.error}`, "error")
    },
    onRegenerationComplete: (data: RegenerationCompleteEvent) => {
      setProgress(100)
      setIsProcessing(false)
      setError(null)
      setLastError(null)
      setIsRetryable(false)
      
      // Build completion message with temperature and seed info
      let completionMessage = "Regeneration and recomposition complete!"
      const infoParts: string[] = []
      
      if (data.temperature != null) {
        infoParts.push(`Temperature: ${data.temperature.toFixed(2)}`)
      }
      if (data.seed != null) {
        infoParts.push(`Seed: ${data.seed}`)
      }
      
      if (infoParts.length > 0) {
        completionMessage += ` (${infoParts.join(", ")})`
      }
      
      addSystemMessage(completionMessage, "success")
      
      // Use video_url from recomposition if available, otherwise use new_clip_url
      const finalVideoUrl = data.video_url || data.new_clip_url
      if (onRegenerationComplete && finalVideoUrl) {
        onRegenerationComplete(finalVideoUrl)
      }
      
      // CRITICAL FIX: Refresh clips to update thumbnails after regeneration
      // Thumbnails are generated during regeneration, but UI needs to refetch them
      if (data.clip_index !== undefined && data.clip_index !== null) {
        // Delay slightly to ensure backend has saved the new thumbnail
        setTimeout(async () => {
          try {
            const response = await getJobClips(jobId)
            setClips(response.clips)
            console.log("✅ Clips refreshed after regeneration, thumbnails updated")
            
            // Automatically refresh comparison for this clip if it's shown
            if (showComparison && selectedClipIndices.includes(data.clip_index)) {
              handleCompareClip(data.clip_index).catch((err) => {
                console.warn("Failed to auto-refresh comparison after regeneration:", err)
              })
            }
          } catch (err) {
            console.warn("Failed to refresh clips after regeneration:", err)
          }
        }, 1000) // Wait 1 second for thumbnail generation
      }
      
      // Reset state after a delay
      setTimeout(() => {
        setProgress(null)
        setTemplateMatched(null)
        setCostEstimate(null)
      }, 3000)
    },
    onRegenerationFailed: (data: RegenerationFailedEvent) => {
      setIsProcessing(false)
      setProgress(null)
      setError(data.error)
      setLastError(data.error)
      setIsRetryable(data.retryable ?? false)
      addSystemMessage(`Regeneration failed: ${data.error}`, "error")
    },
  })

  const addSystemMessage = (content: string, type: Message["type"] = "info") => {
    setMessages((prev) => [
      ...prev,
      {
        role: "system",
        content,
        timestamp: new Date(),
        type,
      },
    ])
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!input.trim() || isProcessing || selectedClipIndices.length === 0) {
      return
    }

    const userMessage = input.trim()
    const clipIndices = selectedClipIndices
    setInput("")
    setError(null)
    setLastError(null)
    setIsRetryable(false)
    setIsProcessing(true)
    setProgress(0)
    setCostEstimate(null)
    setTemplateMatched(null)
    setLastInstruction(userMessage) // Store for retry
    setLastClipIndices(clipIndices) // Store all clip indices for retry

    // Add user message to conversation
    const newUserMessage: Message = {
      role: "user",
      content: userMessage,
      timestamp: new Date(),
    }
    
    setMessages((prev) => [...prev, newUserMessage])

    // Add clip attachment messages for all selected clips
    const clipAttachmentMessages: Message[] = clipIndices.map((clipIndex) => {
      const selectedClip = clips.find((c) => c.clip_index === clipIndex)
      return {
        role: "user" as const,
        content: `Clip ${clipIndex + 1} attached`,
        timestamp: new Date(),
        attachedClipIndex: clipIndex,
        thumbnailUrl: selectedClip?.thumbnail_url || null,
      }
    })
    
    setMessages((prev) => [...prev, ...clipAttachmentMessages])

    // Add to conversation history
    conversationHistoryRef.current.push({
      role: "user",
      content: userMessage,
    })
    saveConversationHistory()

    try {
      // Call regeneration API with all selected clip indices
      const response = await regenerateClip(jobId, {
        instruction: userMessage,
        conversation_history: conversationHistoryRef.current.slice(-3), // Last 3 messages
        clip_indices: clipIndices, // Send all selected clips
      })

      // Update cost estimate
      setCostEstimate(response.estimated_cost)
      setTemplateMatched(response.template_matched || null)

      // Add assistant response
      const clipText = clipIndices.length > 1 
        ? `${clipIndices.length} clips` 
        : "this clip"
      const costText = response.estimated_cost != null ? `$${response.estimated_cost.toFixed(2)}` : null
      const assistantMessage: Message = {
        role: "assistant",
        content: response.template_matched
          ? costText
            ? `I'll apply the "${response.template_matched}" transformation to ${clipText}. Estimated cost: ${costText}`
            : `I'll apply the "${response.template_matched}" transformation to ${clipText}.`
          : costText
            ? `I'll modify ${clipText} based on your instruction. Estimated cost: ${costText}`
            : `I'll modify ${clipText} based on your instruction.`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, assistantMessage])

      // Add to conversation history
      conversationHistoryRef.current.push({
        role: "assistant",
        content: assistantMessage.content,
      })
      saveConversationHistory()

      // Progress will be updated via SSE events
    } catch (err) {
      setIsProcessing(false)
      setProgress(null)
      
      let errorMessage = "Failed to regenerate clip"
      let isRetryable = false
      
      if (err instanceof APIError) {
        // Use the detailed error message from the API
        errorMessage = err.message || "Failed to regenerate clip"
        isRetryable = err.retryable
        
        // Add context based on status code if message is generic
        if (err.statusCode === 409) {
          if (!err.message || err.message === "Failed to regenerate clip") {
            errorMessage = "A regeneration is already in progress. Please wait for it to complete."
          }
        } else if (err.statusCode === 400) {
          if (!err.message || err.message === "Failed to regenerate clip") {
            errorMessage = "Invalid request. Please check your instruction."
          }
        } else if (err.statusCode === 403) {
          if (!err.message || err.message === "Failed to regenerate clip") {
            errorMessage = "You don't have permission to regenerate this clip."
          }
        } else if (err.statusCode === 404) {
          if (!err.message || err.message === "Failed to regenerate clip") {
            errorMessage = "Clip not found. The job may not be completed yet, or the clip data is incomplete."
          }
        } else if (err.statusCode === 402) {
          if (!err.message || err.message === "Failed to regenerate clip") {
            errorMessage = "Budget limit exceeded. Please check your account limits."
          }
        } else if (err.statusCode >= 500) {
          // For 500 errors, show the detailed error message from the API
          errorMessage = err.message || "Server error occurred. Please try again later."
          // If the error mentions database or AttributeError, provide helpful context
          if (errorMessage.includes("AttributeError") || errorMessage.includes("database")) {
            errorMessage += " (This may require a server restart. Please contact support if the issue persists.)"
          }
        }
      } else if (err instanceof Error) {
        // For non-API errors, use the error message
        errorMessage = err.message || "An unexpected error occurred."
      }
      
      setError(errorMessage)
      setIsRetryable(isRetryable)
      addSystemMessage(errorMessage, "error")
    }
  }

  const handleCancel = () => {
    // Note: Backend doesn't support cancellation yet, but we can reset UI state
    setIsProcessing(false)
    setProgress(null)
    setError(null)
    setLastError(null)
    setIsRetryable(false)
    addSystemMessage("Regeneration cancelled (note: regeneration may continue in background)", "warning")
  }

  const handleCompareClip = async (clipIndex: number) => {
    if (loadingComparison) return
    
    try {
      setLoadingComparison(true)
      const data = await getClipComparison(jobId, clipIndex)
      setComparisonData({
        original: data.original,
        regenerated: data.regenerated,
      })
      setShowComparison(true)
    } catch (err) {
      console.error("Failed to load clip comparison:", err)
      let errorMessage = "Failed to load clip comparison"
      if (err instanceof APIError) {
        errorMessage = err.message || errorMessage
      }
      addSystemMessage(errorMessage, "error")
    } finally {
      setLoadingComparison(false)
    }
  }

  const handleRetry = async () => {
    if (!lastInstruction || !lastClipIndices || lastClipIndices.length === 0 || isProcessing) {
      return
    }

    // Clear previous error
    setError(null)
    setLastError(null)
    setIsRetryable(false)
    setIsProcessing(true)
    setProgress(0)
    setCostEstimate(null)
    setTemplateMatched(null)

    // Add retry message
    addSystemMessage("Retrying regeneration...", "info")

    try {
      // Call regeneration API directly with last instruction and clip indices
      const response = await regenerateClip(jobId, {
        instruction: lastInstruction,
        conversation_history: conversationHistoryRef.current.slice(-3), // Last 3 messages
        clip_indices: lastClipIndices, // Send all previously selected clips
      })

      // Update cost estimate
      setCostEstimate(response.estimated_cost)
      setTemplateMatched(response.template_matched || null)

      // Add assistant response
      const costText = response.estimated_cost != null ? `$${response.estimated_cost.toFixed(2)}` : null
      const assistantMessage: Message = {
        role: "assistant",
        content: response.template_matched
          ? costText
            ? `Retrying with "${response.template_matched}" transformation. Estimated cost: ${costText}`
            : `Retrying with "${response.template_matched}" transformation.`
          : costText
            ? `Retrying regeneration. Estimated cost: ${costText}`
            : `Retrying regeneration.`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, assistantMessage])

      // Progress will be updated via SSE events
    } catch (err) {
      setIsProcessing(false)
      setProgress(null)
      
      let errorMessage = "Failed to retry regeneration"
      if (err instanceof APIError) {
        if (err.statusCode === 409) {
          errorMessage = "A regeneration is already in progress. Please wait for it to complete."
        } else if (err.statusCode === 400) {
          errorMessage = err.message || "Invalid request. Please check your instruction."
        } else if (err.statusCode === 403) {
          errorMessage = "You don't have permission to regenerate this clip."
        } else if (err.statusCode === 404) {
          errorMessage = "Clip not found. The job may not be completed yet."
        } else {
          errorMessage = err.message || "An error occurred during regeneration."
        }
      }
      
      setError(errorMessage)
      setLastError(errorMessage)
      setIsRetryable(err instanceof APIError && err.retryable)
      addSystemMessage(errorMessage, "error")
    }
  }

  const handleRevert = async (clipIndex: number, versionNumber: number) => {
    try {
      await revertClipToVersion(jobId, clipIndex, versionNumber)
      
      // Show success message in chat
      addSystemMessage(
        `Successfully reverted clip ${clipIndex + 1} to version ${versionNumber}. The main video has been updated.`,
        "success"
      )
      
      // Refresh clips to update thumbnails after revert
      // Wait a bit for thumbnail to regenerate
      setTimeout(async () => {
        try {
          const response = await getJobClips(jobId)
          setClips(response.clips)
          console.log(`✅ Refreshed clips after revert - thumbnails updated`)
        } catch (err) {
          console.error("Failed to refresh clips after revert:", err)
        }
      }, 2000) // 2 second delay for thumbnail generation
      
      // Trigger regeneration complete callback if provided to update main video
      if (onRegenerationComplete) {
        // The backend will return the new video URL, but we need to refresh the job to get it
        // For now, just notify that a revert happened
        console.log(`✅ Reverted clip ${clipIndex} to version ${versionNumber}`)
      }
      
      // DON'T close comparison modal - let user toggle back and forth between versions
      // The button text will update automatically based on activeVersion state in ClipComparison
      // User can manually close modal when done comparing
    } catch (error) {
      console.error("Failed to revert clip:", error)
      
      let errorMessage = "Failed to revert clip"
      if (error instanceof APIError) {
        errorMessage = error.message || errorMessage
      }
      
      addSystemMessage(errorMessage, "error")
      throw error // Re-throw to let ClipComparison handle the error
    }
  }

  return (
    <>
      {showComparison && comparisonData && selectedClipIndices.length > 0 && (
        <ClipComparison
          originalClip={comparisonData.original}
          regeneratedClip={comparisonData.regenerated}
          audioUrl={audioUrl ?? undefined}
          clipStartTime={comparisonData.clip_start_time ?? null}
          clipEndTime={comparisonData.clip_end_time ?? null}
          activeVersionNumber={comparisonData.active_version_number}
          onClose={() => {
            setShowComparison(false)
            setComparisonData(null)
            saveComparisonState(false, null)
          }}
          onRevert={handleRevert}
          clipIndex={selectedClipIndices[0]}
        />
      )}
      <FloatingChat title="AI Assistant" jobId={jobId} defaultMinimized={true}>
        <div className="flex flex-col h-full" style={{ maxHeight: "calc(80vh - 60px)" }}>
        {/* Scrollable Messages Area */}
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {messages.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">
              <p className="text-base font-medium">Start a conversation to modify a clip.</p>
              <p className="text-sm mt-2">Select a clip below and try: &quot;make it nighttime&quot; or &quot;add more motion&quot;</p>
            </div>
          ) : (
            messages.map((message, index) => {
              const attachedClipIndex = message.attachedClipIndex
              return (
              <div
                key={index}
                className={cn(
                  "flex",
                  message.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                <div
                  className={cn(
                    "max-w-[85%] rounded-lg px-3 py-2",
                    attachedClipIndex !== undefined
                      ? "bg-primary/60 text-primary-foreground text-sm font-medium"
                      : message.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : message.role === "assistant"
                      ? "bg-muted"
                      : message.type === "error"
                      ? "bg-destructive/10 text-destructive"
                      : message.type === "success"
                      ? "bg-green-500/10 text-green-600"
                      : message.type === "warning"
                      ? "bg-yellow-500/10 text-yellow-600"
                      : "bg-muted/50"
                  )}
                >
                  {attachedClipIndex !== undefined ? (
                    <div className="flex items-center gap-2">
                      {message.thumbnailUrl && (
                        <div className="relative w-10 h-6 rounded overflow-hidden flex-shrink-0 bg-muted">
                          <Image
                            src={message.thumbnailUrl}
                            alt={`Clip ${attachedClipIndex + 1} thumbnail`}
                            fill
                            className="object-cover"
                            sizes="40px"
                            onError={(e) => {
                              console.warn(`Failed to load message thumbnail for clip ${attachedClipIndex + 1}`)
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        </div>
                      )}
                      <p className="text-sm font-medium">{message.content}</p>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm font-medium leading-relaxed whitespace-pre-wrap break-words">{message.content}</p>
                      <p className="text-xs opacity-70 mt-1">
                        {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    </>
                  )}
                </div>
              </div>
              )
            })
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Error Alert */}
        {error && (
          <div className="px-3 pb-2">
            <Alert variant="destructive" className="py-2">
              <AlertDescription className="flex items-center justify-between text-sm font-medium">
                <span className="flex-1">{error}</span>
                {isRetryable && lastInstruction && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleRetry}
                    className="ml-2 h-7 text-sm font-medium"
                  >
                    Retry
                  </Button>
                )}
              </AlertDescription>
            </Alert>
          </div>
        )}

        {/* Cost Estimate & Progress */}
        {(costEstimate != null || progress !== null) && (
          <div className="px-3 pb-2 space-y-1.5">
            {costEstimate != null && typeof costEstimate === "number" && (
              <div className="text-sm text-muted-foreground font-medium">
                Estimated cost: <span className="font-semibold">${costEstimate.toFixed(2)}</span>
                {templateMatched && (
                  <span className="ml-1 text-xs">(Template: {templateMatched})</span>
                )}
              </div>
            )}
            {progress !== null && (
              <div className="space-y-1">
                <div className="flex justify-between text-sm font-medium">
                  <span>
                    {progress < 60
                      ? "Regenerating clip..."
                      : progress < 100
                      ? "Recomposing video..."
                      : "Complete!"}
                  </span>
                  <span>{Math.round(progress)}%</span>
                </div>
                <Progress value={progress} className="h-1.5" />
              </div>
            )}
          </div>
        )}

        {/* Compare Button - Prominent placement (above thumbnails) */}
        {!loadingClips && clips.length > 0 && selectedClipIndices.length === 1 && (
          <div className="border-t px-3 py-2 min-h-[56px] flex items-center">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => handleCompareClip(selectedClipIndices[0])}
              disabled={loadingComparison}
              className="w-full"
            >
              <GitCompare className="h-4 w-4 mr-2" />
              {loadingComparison ? "Loading..." : "Compare Versions"}
            </Button>
          </div>
        )}
        
        {/* Multi-clip compare hint (above thumbnails) */}
        {!loadingClips && clips.length > 0 && selectedClipIndices.length > 1 && (
          <div className="border-t px-3 py-2 min-h-[56px] flex items-center justify-center">
            <p className="text-xs text-muted-foreground text-center">
              Select a single clip to compare versions
            </p>
          </div>
        )}

        {/* Clip Thumbnails Row */}
        {!loadingClips && clips.length > 0 && (
          <div className="border-t px-3 py-3">
            {/* Select All Checkbox */}
            <div className="flex items-center justify-between mb-2">
              <label className="flex items-center gap-2 text-sm font-medium text-muted-foreground cursor-pointer hover:text-foreground transition-colors">
                <input
                  type="checkbox"
                  checked={selectedClipIndices.length === clips.length && clips.length > 0}
                  onChange={(e) => {
                    if (selectedClipIndices.length === clips.length) {
                      // Deselect all
                      setSelectedClipIndices([])
                      saveSelectedClips([])
                    } else {
                      // Select all clips
                      const allIndices = clips.map(c => c.clip_index)
                      setSelectedClipIndices(allIndices)
                      saveSelectedClips(allIndices)
                    }
                  }}
                  className="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary"
                />
                <span>Select All Clips ({clips.length})</span>
              </label>
              <span className="text-sm font-medium text-primary min-w-[80px] text-right">
                {selectedClipIndices.length > 0 ? `${selectedClipIndices.length} selected` : '\u00A0'}
              </span>
            </div>
            
            <div className="flex gap-2 overflow-x-auto overflow-y-hidden pb-1 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent" style={{ minHeight: "106px" }}>
              {clips.map((clip) => {
                const timestampRange = `${formatTimestamp(clip.timestamp_start)} - ${formatTimestamp(clip.timestamp_end)}`
                const isSelected = selectedClipIndices.includes(clip.clip_index)
                return (
                  <div
                    key={clip.clip_index}
                    className="relative flex-shrink-0 p-1"
                    style={{ width: "128px" }}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        // Toggle selection
                        if (isSelected) {
                          const newSelection = selectedClipIndices.filter(i => i !== clip.clip_index)
                          setSelectedClipIndices(newSelection)
                          saveSelectedClips(newSelection)
                        } else {
                          const newSelection = [...selectedClipIndices, clip.clip_index].sort((a, b) => a - b)
                          setSelectedClipIndices(newSelection)
                          saveSelectedClips(newSelection)
                        }
                      }}
                      className={cn(
                        "relative w-full rounded overflow-hidden transition-all",
                        "flex flex-col h-full box-border",
                        isSelected
                          ? "border-4 border-blue-500 shadow-lg"
                          : "border-4 border-transparent hover:border-blue-400/50"
                      )}
                    >
                      {/* Thumbnail */}
                      <div className="relative w-full h-16 bg-muted">
                        {clip.thumbnail_url ? (
                          <Image
                            src={clip.thumbnail_url}
                            alt={`Clip ${clip.clip_index + 1}`}
                            fill
                            className="object-cover"
                            sizes="120px"
                            onError={(e) => {
                              console.warn(`Failed to load thumbnail for clip ${clip.clip_index + 1}`)
                              e.currentTarget.style.display = 'none'
                            }}
                          />
                        ) : (
                         <div className="flex items-center justify-center h-full bg-muted text-xs font-semibold text-muted-foreground">
                           {clip.clip_index + 1}
                         </div>
                       )}
                       {isSelected && (
                         <div className="absolute inset-0 bg-blue-500/30 border-2 border-blue-500" />
                       )}
                       {/* Clip number badge */}
                       <div className="absolute top-0.5 left-0.5 bg-black/70 text-white text-xs font-bold px-1.5 py-0.5 rounded">
                         {clip.clip_index + 1}
                       </div>
                     </div>
                     {/* Timestamp info - single line */}
                     <div className="bg-muted/50 px-1 py-1.5 text-xs text-muted-foreground leading-none text-center font-medium whitespace-nowrap">
                       {timestampRange}
                     </div>
                   </button>
                 </div>
               )
             })}
          </div>
          <p className="text-xs text-muted-foreground mt-2 font-medium min-h-[1.25rem]">
             {selectedClipIndices.length > 0 ? (
               <>
                 {selectedClipIndices.length} clip{selectedClipIndices.length !== 1 ? 's' : ''} selected
               </>
             ) : (
               "Click clips to select"
             )}
           </p>
         </div>
        )}

        {/* Loading Clips */}
        {loadingClips && (
          <div className="border-t px-3 py-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground font-medium">
              <LoadingSpinner className="h-4 w-4" />
              <span>Loading clips...</span>
            </div>
          </div>
        )}

        {/* No Clips Available */}
        {!loadingClips && clips.length === 0 && (
          <div className="border-t px-3 py-2">
            <Alert className="py-2">
              <AlertDescription className="text-sm font-medium">
                No clips available. The video may not have completed generation yet.
              </AlertDescription>
            </Alert>
          </div>
        )}

        {/* Input Area */}
        <div className="border-t p-2">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={selectedClipIndices.length > 0 ? "Enter instruction..." : "Select clips first..."}
              disabled={isProcessing || selectedClipIndices.length === 0}
              rows={2}
              className="resize-none text-sm font-medium min-h-[60px] max-h-[120px]"
            />
            <Button
              type="submit"
              disabled={!input.trim() || isProcessing || selectedClipIndices.length === 0}
              size="sm"
              className="h-[60px] px-4 self-end"
            >
              {isProcessing ? (
                <LoadingSpinner className="h-4 w-4" />
              ) : (
                "Send"
              )}
            </Button>
          </form>
        </div>

        {/* SSE Connection Status */}
        {!isConnected && (
          <div className="border-t px-3 py-1.5">
            <Alert className="py-1.5">
              <AlertDescription className="text-sm font-medium">
                Connecting to server...
              </AlertDescription>
            </Alert>
          </div>
        )}
      </div>
    </FloatingChat>
    </>
  )
}

