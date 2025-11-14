"use client"

import { useState, useEffect } from "react"
import { useSSE } from "@/hooks/useSSE"
import { Progress } from "@/components/ui/progress"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { StageIndicator } from "@/components/StageIndicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import type { StageUpdateEvent, ProgressEvent, MessageEvent, CostUpdateEvent, CompletedEvent, ErrorEvent } from "@/types/sse"
import { jobStore } from "@/stores/jobStore"
import { formatDuration } from "@/lib/utils"

interface ProgressTrackerProps {
  jobId: string
  onComplete?: (videoUrl: string) => void
  onError?: (error: string) => void
}

interface StatusMessage {
  text: string
  stage?: string
  timestamp: Date
}

export function ProgressTracker({
  jobId,
  onComplete,
  onError,
}: ProgressTrackerProps) {
  const [progress, setProgress] = useState(0)
  const [currentStage, setCurrentStage] = useState<string | null>(null)
  const [messages, setMessages] = useState<StatusMessage[]>([])
  const [estimatedRemaining, setEstimatedRemaining] = useState<number | null>(
    null
  )
  const [cost, setCost] = useState<number | null>(null)
  const [stages, setStages] = useState<
    Array<{ name: string; status: "pending" | "processing" | "completed" | "failed" }>
  >([])

  const { updateJob } = jobStore()

  const { isConnected, error: sseError } = useSSE(jobId, {
    onStageUpdate: (data: StageUpdateEvent) => {
      setCurrentStage(data.stage)
      updateJob(jobId, { currentStage: data.stage })
      
      setStages((prev) => {
        const existing = prev.find((s) => s.name === data.stage)
        const status = data.status as "pending" | "processing" | "completed" | "failed"
        if (existing) {
          return prev.map((s) =>
            s.name === data.stage
              ? { ...s, status }
              : s
          )
        }
        return [...prev, { name: data.stage, status }]
      })
    },
    onProgress: (data: ProgressEvent) => {
      setProgress(data.progress)
      updateJob(jobId, { progress: data.progress })
      if (data.estimated_remaining) {
        setEstimatedRemaining(data.estimated_remaining)
      }
    },
    onMessage: (data: MessageEvent) => {
      setMessages((prev) => [
        { text: data.text, stage: data.stage, timestamp: new Date() },
        ...prev.slice(0, 4), // Keep last 5 messages
      ])
    },
    onCostUpdate: (data: CostUpdateEvent) => {
      setCost(data.total)
      updateJob(jobId, { totalCost: data.total })
    },
    onCompleted: (data: CompletedEvent) => {
      updateJob(jobId, {
        status: "completed",
        videoUrl: data.video_url,
        progress: 100,
      })
      onComplete?.(data.video_url)
    },
    onError: (data: ErrorEvent) => {
      updateJob(jobId, {
        status: "failed",
        errorMessage: data.error,
      })
      onError?.(data.error)
    },
  })

  return (
    <div className="w-full space-y-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Progress</span>
          <span className="text-sm text-muted-foreground">{progress}%</span>
        </div>
        <Progress value={progress} />
      </div>

      {estimatedRemaining !== null && (
        <p className="text-sm text-muted-foreground">
          Estimated time remaining: {formatDuration(estimatedRemaining)}
        </p>
      )}

      {cost !== null && (
        <p className="text-sm text-muted-foreground">
          Total cost: ${cost.toFixed(2)}
        </p>
      )}

      <StageIndicator stages={stages} currentStage={currentStage} />

      {messages.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Status Messages</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {messages.map((msg, index) => (
                <div key={index} className="text-sm">
                  <p className="font-medium">{msg.text}</p>
                  {msg.stage && (
                    <p className="text-xs text-muted-foreground">
                      {msg.stage}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {sseError && (
        <Alert variant="destructive">
          <AlertDescription>{sseError}</AlertDescription>
        </Alert>
      )}

      {!isConnected && !sseError && (
        <Alert>
          <AlertDescription>Connecting to server...</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

