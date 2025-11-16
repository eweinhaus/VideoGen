"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { ProgressTracker } from "@/components/ProgressTracker"
import { StageIndicator } from "@/components/StageIndicator"
import { VideoPlayer } from "@/components/VideoPlayer"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { useAuth } from "@/hooks/useAuth"
import { useJob } from "@/hooks/useJob"
import { useSSE } from "@/hooks/useSSE"
import { ArrowLeft } from "lucide-react"
import type { StageUpdateEvent } from "@/types/sse"

export default function JobProgressPage() {
  const params = useParams()
  const router = useRouter()
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const jobId = params.jobId as string
  const { job, isLoading: jobLoading, error, fetchJob } = useJob(jobId)
  const [sseError, setSseError] = useState<string | null>(null)
  const [stages, setStages] = useState<
    Array<{ name: string; status: "pending" | "processing" | "completed" | "failed" }>
  >([])
  const [currentStage, setCurrentStage] = useState<string | null>(null)

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, authLoading, router])

  useEffect(() => {
    if (jobId) {
      fetchJob(jobId).catch(() => {
        // Error handled by jobStore
      })
    }
  }, [jobId, fetchJob])

  // Track stages for StageIndicator
  useSSE(jobId, {
    onStageUpdate: (data: StageUpdateEvent) => {
      setCurrentStage(data.stage)
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
  })

  const handleComplete = (videoUrl: string) => {
    // Job is already updated by ProgressTracker
    // VideoPlayer will be shown automatically
  }

  const handleError = (error: string) => {
    setSseError(error)
  }

  if (authLoading || jobLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" text="Loading job..." />
      </div>
    )
  }

  if (error) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-8">
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <Button
          className="mt-4"
          variant="outline"
          onClick={() => router.push("/upload")}
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Upload
        </Button>
      </div>
    )
  }

  if (!job) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" text="Loading job..." />
      </div>
    )
  }

  const isCompleted = job.status === "completed" && job.videoUrl
  const isFailed = job.status === "failed"
  // Only show "queued" message if status is queued AND no stage has started yet
  const isQueued = job.status === "queued" && !job.currentStage
  const isProcessing = job.status === "processing"

  return (
    <div className="container mx-auto max-w-7xl px-4 py-8">
      <div className="mb-6">
        <Button
          variant="ghost"
          onClick={() => router.push("/upload")}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Upload
        </Button>
        <Card className="w-full">
          <CardHeader>
            <CardTitle>Job Progress</CardTitle>
            <CardDescription>Job ID: {jobId}</CardDescription>
          </CardHeader>
          <CardContent className="w-full">
            {isQueued && (
              <Alert className="mb-4">
                <AlertDescription>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                    <span>
                      Job is queued and waiting to start{" "}
                      {job.currentStage === "audio_parser" && "audio analysis"}
                      {job.currentStage === "scene_planner" && "scene planning"}
                      {job.currentStage === "reference_generator" && "reference generation"}
                      {job.currentStage === "prompt_generation" && "prompt generation"}
                      {job.currentStage === "video_generation" && "video generation"}
                      {job.currentStage === "composition" && "composition"}
                      {!job.currentStage && "processing"}
                      ...
                    </span>
                  </div>
                </AlertDescription>
              </Alert>
            )}
            {isProcessing && job.progress === 0 && (
              <Alert className="mb-4">
                <AlertDescription>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-yellow-500 animate-pulse" />
                    <span>Job is starting... Processing will begin shortly.</span>
                  </div>
                </AlertDescription>
              </Alert>
            )}
            {isCompleted && job.videoUrl ? (
              <div className="space-y-6">
                <Alert>
                  <AlertDescription>
                    Video generation completed successfully!
                  </AlertDescription>
                </Alert>
                <VideoPlayer videoUrl={job.videoUrl} jobId={jobId} />
              </div>
            ) : isFailed ? (
              <div className="space-y-4">
                <Alert variant="destructive">
                  <AlertDescription>
                    {job.errorMessage || "Video generation failed"}
                  </AlertDescription>
                </Alert>
                {sseError && (
                  <Alert variant="destructive">
                    <AlertDescription>{sseError}</AlertDescription>
                  </Alert>
                )}
                <Button
                  variant="outline"
                  onClick={() => router.push("/upload")}
                >
                  Create New Video
                </Button>
              </div>
            ) : (
              <ProgressTracker
                jobId={jobId}
                onComplete={handleComplete}
                onError={handleError}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

