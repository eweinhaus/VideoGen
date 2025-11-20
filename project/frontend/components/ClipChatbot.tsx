"use client"

import { useState, useEffect, useRef, useCallback } from "react"
import Image from "next/image"
import { regenerateClip, getJobClips, getClipComparison } from "@/lib/api"
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
}

export function ClipChatbot({
  jobId,
  onRegenerationComplete,
}: ClipChatbotProps) {
  // Generate unique storage key for this job (unified chat)
  const storageKey = `clip_chat_${jobId}`
  const conversationHistoryKey = `clip_chat_history_${jobId}`
  const selectedClipKey = `clip_chat_selected_${jobId}`
  
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
  const [lastClipIndex, setLastClipIndex] = useState<number | null>(null)
  const [clips, setClips] = useState<ClipData[]>([])
  const [selectedClipIndex, setSelectedClipIndex] = useState<number | null>(null)
  const [loadingClips, setLoadingClips] = useState(true)
  const [showComparison, setShowComparison] = useState(false)
  const [comparisonData, setComparisonData] = useState<{
    original: any
    regenerated: any | null
  } | null>(null)
  const [loadingComparison, setLoadingComparison] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const conversationHistoryRef = useRef<Array<{ role: string; content: string }>>([])
  const isInitializedRef = useRef(false)

  // Save selected clip index to localStorage
  const saveSelectedClip = useCallback((clipIndex: number | null) => {
    if (!isInitializedRef.current) return
    try {
      if (clipIndex === null) {
        localStorage.removeItem(selectedClipKey)
      } else {
        localStorage.setItem(selectedClipKey, JSON.stringify(clipIndex))
      }
    } catch (err) {
      console.error("Failed to save selected clip:", err)
    }
  }, [selectedClipKey])

  // Restore selected clip index from localStorage
  const getPersistedSelectedClip = useCallback((): number | null => {
    try {
      const saved = localStorage.getItem(selectedClipKey)
      if (saved !== null) {
        return JSON.parse(saved)
      }
    } catch (err) {
      console.error("Failed to restore selected clip:", err)
    }
    return null
  }, [selectedClipKey])

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
          
          // Restore persisted selected clip index if it exists
          const persistedIndex = getPersistedSelectedClip()
          if (persistedIndex !== null) {
            // Validate that the selected clip still exists
            const clipExists = response.clips.some(c => c.clip_index === persistedIndex)
            if (clipExists) {
              setSelectedClipIndex(persistedIndex)
            } else {
              // Selected clip no longer exists, clear selection
              setSelectedClipIndex(null)
              saveSelectedClip(null)
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
  }, [jobId, getPersistedSelectedClip, saveSelectedClip])

  // Load messages and conversation history from localStorage on mount or when jobId changes
  useEffect(() => {
    // Reset initialization flag when jobId changes
    isInitializedRef.current = false
    
    try {
      // Load messages
      const savedMessages = localStorage.getItem(storageKey)
      if (savedMessages) {
        const parsed = JSON.parse(savedMessages)
        // Convert timestamp strings back to Date objects
        const restoredMessages: Message[] = parsed.map((msg: any) => ({
          ...msg,
          timestamp: new Date(msg.timestamp),
        }))
        setMessages(restoredMessages)
      } else {
        // Clear messages if no saved data for this job
        setMessages([])
      }

      // Load conversation history
      const savedHistory = localStorage.getItem(conversationHistoryKey)
      if (savedHistory) {
        conversationHistoryRef.current = JSON.parse(savedHistory)
      } else {
        // Clear conversation history if no saved data
        conversationHistoryRef.current = []
      }
    } catch (err) {
      console.error("Failed to load chat history from localStorage:", err)
      // Silently fail - start with empty chat
      setMessages([])
      conversationHistoryRef.current = []
    }
    
    isInitializedRef.current = true
  }, [jobId, storageKey, conversationHistoryKey])

  // Restore selected clip index on mount (if not already set by clip fetch)
  // This is handled in the clip fetch useEffect, but this is a fallback
  useEffect(() => {
    if (selectedClipIndex === null && clips.length > 0 && isInitializedRef.current) {
      const persistedIndex = getPersistedSelectedClip()
      if (persistedIndex !== null) {
        const clipExists = clips.some(c => c.clip_index === persistedIndex)
        if (clipExists) {
          setSelectedClipIndex(persistedIndex)
        }
      }
    }
  }, [clips, selectedClipIndex, getPersistedSelectedClip])

  // Save selected clip index when it changes
  useEffect(() => {
    if (isInitializedRef.current) {
      saveSelectedClip(selectedClipIndex)
    }
  }, [selectedClipIndex, saveSelectedClip])

  // Save messages to localStorage whenever they change
  useEffect(() => {
    if (!isInitializedRef.current) return
    
    try {
      // Convert Date objects to ISO strings for storage
      const messagesToSave = messages.map((msg) => ({
        ...msg,
        timestamp: msg.timestamp.toISOString(),
      }))
      localStorage.setItem(storageKey, JSON.stringify(messagesToSave))
    } catch (err) {
      console.error("Failed to save messages to localStorage:", err)
      // Silently fail - chat will continue to work, just won't persist
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

    if (!input.trim() || isProcessing || selectedClipIndex === null) {
      return
    }

    const userMessage = input.trim()
    const clipIndex = selectedClipIndex
    setInput("")
    setError(null)
    setLastError(null)
    setIsRetryable(false)
    setIsProcessing(true)
    setProgress(0)
    setCostEstimate(null)
    setTemplateMatched(null)
    setLastInstruction(userMessage) // Store for retry
    setLastClipIndex(clipIndex) // Store for retry

    // Find the selected clip for thumbnail
    const selectedClip = clips.find((c) => c.clip_index === clipIndex)

    // Add user message to conversation
    const newUserMessage: Message = {
      role: "user",
      content: userMessage,
      timestamp: new Date(),
    }
    
    // Add clip attachment message right after user message
    const clipAttachmentMessage: Message = {
      role: "user",
      content: `Clip ${clipIndex + 1} attached`,
      timestamp: new Date(),
      attachedClipIndex: clipIndex,
      thumbnailUrl: selectedClip?.thumbnail_url || null,
    }
    
    setMessages((prev) => [...prev, newUserMessage, clipAttachmentMessage])

    // Add to conversation history
    conversationHistoryRef.current.push({
      role: "user",
      content: userMessage,
    })
    saveConversationHistory()

    try {
      // Call regeneration API
      const response = await regenerateClip(jobId, clipIndex, {
        instruction: userMessage,
        conversation_history: conversationHistoryRef.current.slice(-3), // Last 3 messages
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
            ? `I'll apply the "${response.template_matched}" transformation to this clip. Estimated cost: ${costText}`
            : `I'll apply the "${response.template_matched}" transformation to this clip.`
          : costText
            ? `I'll modify this clip based on your instruction. Estimated cost: ${costText}`
            : `I'll modify this clip based on your instruction.`,
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
    if (!lastInstruction || !lastClipIndex || isProcessing) {
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
      // Call regeneration API directly with last instruction
      const response = await regenerateClip(jobId, lastClipIndex, {
        instruction: lastInstruction,
        conversation_history: conversationHistoryRef.current.slice(-3), // Last 3 messages
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

  return (
    <>
      {showComparison && comparisonData && selectedClipIndex !== null && (
        <ClipComparison
          originalClip={comparisonData.original}
          regeneratedClip={comparisonData.regenerated}
          onClose={() => {
            setShowComparison(false)
            setComparisonData(null)
          }}
          clipIndex={selectedClipIndex}
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

        {/* Clip Thumbnails Row */}
        {!loadingClips && clips.length > 0 && (
          <div className="border-t px-3 py-3">
            <div className="flex gap-2 overflow-x-auto overflow-y-hidden pb-1 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent" style={{ minHeight: "100px" }}>
              {clips.map((clip) => {
                const timestampRange = `${formatTimestamp(clip.timestamp_start)} - ${formatTimestamp(clip.timestamp_end)}`
                return (
                  <div
                    key={clip.clip_index}
                    className="relative flex-shrink-0"
                    style={{ width: "120px" }}
                  >
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedClipIndex(clip.clip_index)
                        saveSelectedClip(clip.clip_index)
                      }}
                      disabled={isProcessing}
                      className={cn(
                        "relative w-full rounded overflow-hidden border-2 transition-all",
                        "flex flex-col h-full",
                        selectedClipIndex === clip.clip_index
                          ? "border-primary ring-2 ring-primary/20"
                          : "border-muted hover:border-primary/50",
                        isProcessing && "opacity-50 cursor-not-allowed"
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
                       {selectedClipIndex === clip.clip_index && (
                         <div className="absolute inset-0 bg-primary/20" />
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
           <p className="text-xs text-muted-foreground mt-2 font-medium">
              {selectedClipIndex !== null ? (
                <>
                  Clip {selectedClipIndex + 1} selected
                </>
              ) : (
                "Select a clip to modify"
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

        {/* Compare Button - Prominent placement */}
        {selectedClipIndex !== null && (
          <div className="border-t px-3 py-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => handleCompareClip(selectedClipIndex)}
              disabled={loadingComparison || isProcessing}
              className="w-full"
            >
              <GitCompare className="h-4 w-4 mr-2" />
              {loadingComparison ? "Loading..." : "Compare Versions"}
            </Button>
          </div>
        )}

        {/* Input Area */}
        <div className="border-t p-2">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Enter instruction..."
              disabled={isProcessing || selectedClipIndex === null}
              rows={2}
              className="resize-none text-sm font-medium min-h-[60px] max-h-[120px]"
            />
            <Button
              type="submit"
              disabled={!input.trim() || isProcessing || selectedClipIndex === null}
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

