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
  const [elapsed, setElapsed] = useState<number>(0)
  const [timerOn, setTimerOn] = useState<boolean>(false)

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, authLoading, router])

  useEffect(() => {
    if (jobId) {
      console.log("🔄 JobProgressPage: Fetching job", jobId)
      // Reset uploadStore's isSubmitting state when job progress page loads
      // This ensures the loading modal on the upload page is hidden once we're here
      import("@/stores/uploadStore").then(({ uploadStore }) => {
        uploadStore.getState().reset()
      })
      // Only fetch once on mount - don't refetch on every job update
      // SSE will handle real-time updates, and updateJob won't trigger refetches
      fetchJob(jobId).catch((error) => {
        console.error("❌ JobProgressPage: Failed to fetch job", error)
        // Error handled by jobStore, but log it here too
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]) // Only depend on jobId, not fetchJob to prevent unnecessary refetches

  // Track stages for StageIndicator
  useSSE(jobId, {
    onStageUpdate: (data: StageUpdateEvent) => {
      const normalize = (name: string) => {
        const n = name.toLowerCase()
        if (n === "audio_analysis") return "audio_parser"
        if (n === "scene_planning") return "scene_planner"
        if (n === "reference_generation") return "reference_generator"
        if (n === "prompt_generator") return "prompt_generation"
        if (n === "video_generator") return "video_generation"
        return n
      }
      const stage = normalize(data.stage)
      const statusMap: Record<string, "pending" | "processing" | "completed" | "failed"> = {
        started: "processing",
        processing: "processing",
        completed: "completed",
        failed: "failed",
        pending: "pending",
      }
      const status = statusMap[(data.status || "").toLowerCase()] || "processing"
      setCurrentStage(stage)
      if (!timerOn) setTimerOn(true)
      setStages((prev) => {
        const existing = prev.find((s) => s.name === stage)

        // Define stage order for marking previous stages as completed
        const stageOrder = [
          "audio_parser",
          "scene_planner",
          "reference_generator",
          "prompt_generation",
          "video_generation",
          "composition",
        ]
        const currentStageIndex = stageOrder.indexOf(stage)

        if (existing) {
          // Don't downgrade from completed to processing
          if (existing.status === "completed" && status === "processing") {
            return prev
          }
          return prev.map((s) => {
            const stageIndex = stageOrder.indexOf(s.name)
            // Mark all previous stages as completed when a new stage starts
            if (stageIndex !== -1 && stageIndex < currentStageIndex && s.status !== "completed" && s.status !== "failed") {
              return { ...s, status: "completed" }
            }
            return s.name === stage ? { ...s, status } : s
          })
        }

        // Add new stage and mark all previous stages as completed
        const updatedStages = prev.map((s) => {
          const stageIndex = stageOrder.indexOf(s.name)
          if (stageIndex !== -1 && stageIndex < currentStageIndex && s.status !== "completed" && s.status !== "failed") {
            return { ...s, status: "completed" }
          }
          return s
        })

        return [...updatedStages, { name: stage, status }]
      })
    },
  })

  // Timer lifecycle: start on first stage update; stop on completion/failure
  useEffect(() => {
    if (!timerOn) return
    if (job?.status === "completed" || job?.status === "failed") {
      setTimerOn(false)
      return
    }
    const id = setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => clearInterval(id)
  }, [timerOn, job?.status])

  // Start/stop the header timer based on job status immediately on load
  useEffect(() => {
    if (!job) return
    if (job.status === "queued" || job.status === "processing") {
      setTimerOn(true)
    } else if (job.status === "completed" || job.status === "failed") {
      setTimerOn(false)
    }
  }, [job])

  const formatElapsed = (s: number) => {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    return h > 0
      ? `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
      : `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
  }

  const handleComplete = (videoUrl: string) => {
    // Job is already updated by ProgressTracker
    // VideoPlayer will be shown automatically
  }

  const handleError = (error: string) => {
    setSseError(error)
  }

  // Debug logging
  useEffect(() => {
    console.log("🔍 JobProgressPage state:", {
      jobId,
      authLoading,
      jobLoading,
      hasJob: !!job,
      error,
      jobStatus: job?.status,
      jobProgress: job?.progress
    })
  }, [jobId, authLoading, jobLoading, job, error])

  // Early returns after all hooks
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
          <AlertDescription>
            <div className="space-y-2">
              <div>Error: {error}</div>
              <div className="text-sm text-muted-foreground">
                Job ID: {jobId}
              </div>
            </div>
          </AlertDescription>
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
        <div className="text-center space-y-4">
          <LoadingSpinner size="lg" text="Loading job..." />
          <div className="text-sm text-muted-foreground">
            Job ID: {jobId}
          </div>
          <div className="text-sm text-muted-foreground">
            If this persists, the job may not exist or you may not have access to it.
          </div>
        </div>
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
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Job Progress</CardTitle>
                <CardDescription>Job ID: {jobId}</CardDescription>
              </div>
              {/* Timer aligned to the right of the title */}
              {(isProcessing || timerOn) && (
                <div className="text-sm font-mono text-muted-foreground self-center inline-flex items-center gap-3">
                  <span className="inline-flex items-center gap-2">
                    <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                    Live
                  </span>
                  <span className="tabular-nums">{formatElapsed(elapsed)}</span>
                </div>
              )}
            </div>
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
            {isProcessing && job.progress === 0 && !job.currentStage && (
              <Alert className="mb-4">
                <AlertDescription>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-yellow-500 animate-pulse" />
                    <span>Job is starting... Processing will begin shortly.</span>
                  </div>
                </AlertDescription>
              </Alert>
            )}
            {isFailed ? (
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
              <div className="space-y-6">
                {isCompleted && job.videoUrl && (
                  <div className="space-y-4">
                    <Alert>
                      <AlertDescription>
                        Video generation completed successfully!
                      </AlertDescription>
                    </Alert>
                    <VideoPlayer videoUrl={job.videoUrl} jobId={jobId} />
                  </div>
                )}
                <ProgressTracker
                  jobId={jobId}
                  onComplete={handleComplete}
                  onError={handleError}
                />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

