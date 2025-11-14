"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { ProgressTracker } from "@/components/ProgressTracker"
import { VideoPlayer } from "@/components/VideoPlayer"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { useAuth } from "@/hooks/useAuth"
import { useJob } from "@/hooks/useJob"
import { ArrowLeft } from "lucide-react"

export default function JobProgressPage() {
  const params = useParams()
  const router = useRouter()
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const jobId = params.jobId as string
  const { job, isLoading: jobLoading, error, fetchJob } = useJob(jobId)
  const [sseError, setSseError] = useState<string | null>(null)

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
  const isQueued = job.status === "queued"
  const isProcessing = job.status === "processing"

  return (
    <div className="container mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6">
        <Button
          variant="ghost"
          onClick={() => router.push("/upload")}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Upload
        </Button>
        <Card>
          <CardHeader>
            <CardTitle>Job Progress</CardTitle>
            <CardDescription>Job ID: {jobId}</CardDescription>
          </CardHeader>
          <CardContent>
            {isQueued && (
              <Alert className="mb-4">
                <AlertDescription>
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                    <span>Job is queued and waiting to be processed...</span>
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

