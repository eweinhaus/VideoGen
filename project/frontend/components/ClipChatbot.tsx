"use client"

import { useState, useEffect, useRef } from "react"
import Image from "next/image"
import { regenerateClip, getJobClips } from "@/lib/api"
import { useSSE } from "@/hooks/useSSE"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Progress } from "@/components/ui/progress"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { APIError } from "@/types/api"
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

interface Message {
  role: "user" | "assistant" | "system"
  content: string
  timestamp: Date
  type?: "info" | "warning" | "error" | "success"
  attachedClipIndex?: number
  thumbnailUrl?: string | null
}

interface ClipChatbotProps {
  jobId: string
  clipIndex: number
  onRegenerationComplete?: (newVideoUrl: string) => void
}

export function ClipChatbot({
  jobId,
  clipIndex,
  onRegenerationComplete,
}: ClipChatbotProps) {
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
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const conversationHistoryRef = useRef<Array<{ role: string; content: string }>>([])

  // Fetch clip thumbnail when clipIndex changes
  useEffect(() => {
    let mounted = true

    async function fetchThumbnail() {
      try {
        const response = await getJobClips(jobId)
        const clip = response.clips.find((c) => c.clip_index === clipIndex)
        if (mounted && clip) {
          setThumbnailUrl(clip.thumbnail_url)
        }
      } catch (err) {
        console.error("Failed to fetch clip thumbnail:", err)
        // Silently fail - thumbnail is optional
      }
    }

    fetchThumbnail()

    return () => {
      mounted = false
    }
  }, [jobId, clipIndex])

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

    if (!input.trim() || isProcessing) {
      return
    }

    const userMessage = input.trim()
    setInput("")
    setError(null)
    setLastError(null)
    setIsRetryable(false)
    setIsProcessing(true)
    setProgress(0)
    setCostEstimate(null)
    setTemplateMatched(null)
    setLastInstruction(userMessage) // Store for retry

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
      thumbnailUrl: thumbnailUrl,
    }
    
    setMessages((prev) => [...prev, newUserMessage, clipAttachmentMessage])

    // Add to conversation history
    conversationHistoryRef.current.push({
      role: "user",
      content: userMessage,
    })

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
      const costText = response.estimated_cost != null ? `$${response.estimated_cost.toFixed(2)}` : "calculating..."
      const assistantMessage: Message = {
        role: "assistant",
        content: response.template_matched
          ? `I'll apply the "${response.template_matched}" transformation to this clip. Estimated cost: ${costText}`
          : `I'll modify this clip based on your instruction. Estimated cost: ${costText}`,
        timestamp: new Date(),
      }
      setMessages((prev) => [...prev, assistantMessage])

      // Add to conversation history
      conversationHistoryRef.current.push({
        role: "assistant",
        content: assistantMessage.content,
      })

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

  const handleRetry = async () => {
    if (!lastInstruction || isProcessing) {
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
      const response = await regenerateClip(jobId, clipIndex, {
        instruction: lastInstruction,
        conversation_history: conversationHistoryRef.current.slice(-3), // Last 3 messages
      })

      // Update cost estimate
      setCostEstimate(response.estimated_cost)
      setTemplateMatched(response.template_matched || null)

      // Add assistant response
      const costText = response.estimated_cost != null ? `$${response.estimated_cost.toFixed(2)}` : "calculating..."
      const assistantMessage: Message = {
        role: "assistant",
        content: response.template_matched
          ? `Retrying with "${response.template_matched}" transformation. Estimated cost: ${costText}`
          : `Retrying regeneration. Estimated cost: ${costText}`,
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
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Modify Clip</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Messages */}
        <div className="h-64 overflow-y-auto border rounded-md p-4 space-y-3 bg-muted/30">
          {messages.length === 0 ? (
            <div className="text-center text-muted-foreground py-8">
              <p>Start a conversation to modify this clip.</p>
              <p className="text-sm mt-2">Try: &quot;make it nighttime&quot; or &quot;add more motion&quot;</p>
            </div>
          ) : (
            messages.map((message, index) => (
              <div
                key={index}
                className={cn(
                  "flex",
                  message.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                <div
                  className={cn(
                    "max-w-[80%] rounded-lg px-4 py-2",
                    message.attachedClipIndex !== undefined
                      ? "bg-primary/60 text-primary-foreground text-xs"
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
                  {message.attachedClipIndex !== undefined ? (
                    <div className="flex items-center gap-2">
                      {message.thumbnailUrl && (
                        <div className="relative w-12 h-8 rounded overflow-hidden flex-shrink-0">
                          <Image
                            src={message.thumbnailUrl}
                            alt={`Clip ${message.attachedClipIndex + 1} thumbnail`}
                            fill
                            className="object-cover"
                            sizes="48px"
                          />
                        </div>
                      )}
                      <p className="text-xs">{message.content}</p>
                    </div>
                  ) : (
                    <>
                      <p className="text-sm">{message.content}</p>
                      <p className="text-xs opacity-70 mt-1">
                        {message.timestamp.toLocaleTimeString()}
                      </p>
                    </>
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Error Alert with Retry */}
        {error && (
          <Alert variant="destructive">
            <AlertDescription className="flex items-center justify-between">
              <span>{error}</span>
              {isRetryable && lastInstruction && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleRetry}
                  className="ml-4"
                >
                  Retry
                </Button>
              )}
            </AlertDescription>
          </Alert>
        )}

        {/* Cost Estimate */}
        {costEstimate != null && typeof costEstimate === "number" && (
          <div className="text-sm text-muted-foreground">
            Estimated cost: <span className="font-semibold">${costEstimate.toFixed(2)}</span>
            {templateMatched && (
              <span className="ml-2 text-xs">(Template: {templateMatched})</span>
            )}
          </div>
        )}

        {/* Progress Bar */}
        {progress !== null && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm">
              <span>
                {progress < 60
                  ? "Regenerating clip..."
                  : progress < 100
                  ? "Recomposing video..."
                  : "Complete!"}
              </span>
              <span>{Math.round(progress)}%</span>
            </div>
            <Progress value={progress} />
          </div>
        )}

        {/* Input Form */}
        <form onSubmit={handleSubmit} className="space-y-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter your modification instruction..."
            disabled={isProcessing}
            rows={2}
            className="resize-none"
          />
          <div className="flex gap-2">
            <Button
              type="submit"
              disabled={!input.trim() || isProcessing}
              className="flex-1"
            >
              {isProcessing ? (
                <>
                  <LoadingSpinner className="mr-2 h-4 w-4" />
                  Processing...
                </>
              ) : (
                "Send"
              )}
            </Button>
            {isProcessing && (
              <Button
                type="button"
                variant="outline"
                onClick={handleCancel}
              >
                Cancel
              </Button>
            )}
          </div>
        </form>

        {/* SSE Connection Status */}
        {!isConnected && (
          <Alert>
            <AlertDescription className="text-xs">
              Connecting to server...
            </AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  )
}

