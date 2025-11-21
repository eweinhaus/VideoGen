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
import { ClipSelector } from "@/components/ClipSelector"
import { ClipChatbot } from "@/components/ClipChatbot"
import { ClipComparison } from "@/components/ClipComparison"
import { useAuth } from "@/hooks/useAuth"
import { useJob } from "@/hooks/useJob"
import { useSSE } from "@/hooks/useSSE"
import { ArrowLeft, GitCompare } from "lucide-react"
import { getClipComparison, revertClipToVersion } from "@/lib/api"
import { jobStore } from "@/stores/jobStore"
import type { StageUpdateEvent, RegenerationCompleteEvent } from "@/types/sse"

export default function JobProgressPage() {
  const params = useParams()
  const router = useRouter()
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const jobId = params.jobId as string
  const { job, isLoading: jobLoading, error, fetchJob } = useJob(jobId)
  const [sseError, setSseError] = useState<string | null>(null)
  const [selectedClipIndex, setSelectedClipIndex] = useState<number | undefined>(undefined)
  const [selectedClipTimestamp, setSelectedClipTimestamp] = useState<number | undefined>(undefined)
  const comparisonStateKey = `job_page_comparison_${jobId}`
  const [showComparison, setShowComparison] = useState(false)
  const [comparisonData, setComparisonData] = useState<any>(null)
  const [loadingComparison, setLoadingComparison] = useState(false)
  const [clipRefreshTrigger, setClipRefreshTrigger] = useState(0) // Add refresh trigger
  
  // SSE connection for regeneration events (separate from main job progress)
  useSSE(jobId, {
    onRegenerationComplete: (data: RegenerationCompleteEvent) => {
      console.log("🎯 JobProgressPage: Regeneration complete SSE event received for clip", data.clip_index)
      
      // Immediately trigger ClipSelector refresh with NO delay
      setClipRefreshTrigger(prev => prev + 1)
      console.log("✅ ClipSelector refresh triggered immediately (no delay)")
      
      // Refresh job to get updated video URL
      fetchJob(jobId).catch((err) => {
        console.error("Failed to refresh job after regeneration:", err)
      })
      
      // If comparison view is open for the regenerated clip, refresh it
      if (showComparison && selectedClipIndex === data.clip_index) {
        handleCompare(data.clip_index).catch((err) => {
          console.warn("Failed to refresh comparison after regeneration:", err)
        })
      }
    },
  })
  
  // Restore comparison state from localStorage on mount or when selectedClipIndex changes
  useEffect(() => {
    if (selectedClipIndex === undefined) return
    
    try {
      const saved = localStorage.getItem(comparisonStateKey)
      if (saved) {
        const parsed = JSON.parse(saved)
        // Only restore if the saved clipIndex matches the current selectedClipIndex
        if (parsed.show && parsed.data && parsed.clipIndex === selectedClipIndex) {
          setComparisonData(parsed.data)
          setShowComparison(true)
        } else if (parsed.clipIndex !== selectedClipIndex) {
          // Clear comparison state if clip doesn't match
          setShowComparison(false)
          setComparisonData(null)
          localStorage.removeItem(comparisonStateKey)
        }
      }
    } catch (err) {
      console.error("Failed to restore comparison state:", err)
    }
  }, [comparisonStateKey, selectedClipIndex])

  // Save comparison state to localStorage
  useEffect(() => {
    try {
      if (!showComparison || !comparisonData || selectedClipIndex === undefined) {
        localStorage.removeItem(comparisonStateKey)
      } else {
        localStorage.setItem(comparisonStateKey, JSON.stringify({
          show: showComparison,
          data: comparisonData,
          clipIndex: selectedClipIndex
        }))
      }
    } catch (err) {
      console.error("Failed to save comparison state:", err)
    }
  }, [showComparison, comparisonData, selectedClipIndex, comparisonStateKey])

  // Clear comparison state when jobId changes
  useEffect(() => {
    localStorage.removeItem(comparisonStateKey)
    setShowComparison(false)
    setComparisonData(null)
  }, [jobId, comparisonStateKey])
  
  const handleCompare = async (forceClipIndex?: number) => {
    const clipIndex = forceClipIndex !== undefined ? forceClipIndex : selectedClipIndex
    if (clipIndex === undefined) return
    
    setLoadingComparison(true)
    
    try {
      const data = await getClipComparison(jobId, clipIndex)
      console.log("🎯 Received comparison data:", {
        active_version_number: data.active_version_number,
        originalVersion: data.original.version_number,
        regeneratedVersion: data.regenerated?.version_number
      })
      setComparisonData(data)
      setShowComparison(true)
    } catch (err) {
      console.error("Failed to load comparison:", err)
      // Error is logged, user can retry
    } finally {
      setLoadingComparison(false)
    }
  }

  const handleRevert = async (clipIndex: number, versionNumber: number) => {
    try {
      await revertClipToVersion(jobId, clipIndex, versionNumber)
      // Refresh job to get updated video URL
      await fetchJob(jobId)
      
      // Wait for backend thumbnail generation to complete (2 seconds)
      // Backend generates thumbnails asynchronously after recomposition
      // We need to wait longer since it's a background task
      setTimeout(() => {
        setClipRefreshTrigger(prev => prev + 1)
        console.log("✅ ClipSelector refresh triggered after revert (with 2s for async thumbnail generation)")
      }, 2000)  // Increased from 500ms to 2000ms
      
      // Show success message (you could add a toast notification here)
      console.log(`✅ Successfully reverted clip ${clipIndex} to version ${versionNumber}`)
    } catch (error) {
      console.error("Failed to revert clip:", error)
      throw error // Re-throw to let ClipComparison handle the error
    }
  }

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, authLoading, router])

  useEffect(() => {
    if (jobId) {
      console.log("🔄 JobProgressPage: Fetching job", jobId)
      // Only fetch once on mount - don't refetch on every job update
      // SSE will handle real-time updates, and updateJob won't trigger refetches
      fetchJob(jobId).catch((error) => {
        console.error("❌ JobProgressPage: Failed to fetch job", error)
        // Error handled by jobStore, but log it here too
      })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]) // Only depend on jobId, not fetchJob to prevent unnecessary refetches

  // Scroll to top when video loads
  useEffect(() => {
    const isCompleted = job?.status === "completed" && job?.videoUrl
    if (isCompleted && job?.videoUrl) {
      // Small delay to ensure DOM is updated
      setTimeout(() => {
        window.scrollTo({ top: 0, behavior: 'smooth' })
      }, 100)
    }
  }, [job?.status, job?.videoUrl])

  // Hide loading modal immediately once we're on the job page
  useEffect(() => {
    // Once the job page is loaded and we have the jobId, hide the modal immediately
    if (jobId) {
      import("@/stores/uploadStore").then(({ uploadStore }) => {
        if (uploadStore.getState().isSubmitting) {
          console.log("✅ On job page, hiding loading modal immediately")
          uploadStore.getState().reset()
        }
      })
    }
  }, [jobId])

  // Format remaining time for display in header
  const formatRemaining = (seconds: number | null | undefined): string => {
    if (seconds === null || seconds === undefined) return ""
    if (seconds < 60) return "Less than a minute remaining"
    const minutes = Math.ceil(seconds / 60)
    return `About ${minutes} minute${minutes !== 1 ? 's' : ''} remaining`
  }

  const handleComplete = (videoUrl: string) => {
    // Job is already updated by ProgressTracker
    // VideoPlayer will be shown automatically
  }

  const handleError = (error: string) => {
    setSseError(error)
  }

  // Removed debug logging to prevent excessive re-renders

  // Check if cross-page loading modal should be shown
  const [isSubmitting, setIsSubmitting] = useState(false)
  
  useEffect(() => {
    // Check uploadStore for isSubmitting state (for cross-page modal)
    // The modal persists until audio_parser stage starts, then uploadStore.reset() is called
    import("@/stores/uploadStore").then(({ uploadStore }) => {
      setIsSubmitting(uploadStore.getState().isSubmitting)
      
      // Poll uploadStore periodically until it's reset (when audio_parser starts)
      const interval = setInterval(() => {
        const current = uploadStore.getState().isSubmitting
        setIsSubmitting(current)
        if (!current) {
          clearInterval(interval)
        }
      }, 100) // Check every 100ms
      
      return () => clearInterval(interval)
    })
  }, [])
  
  // Status flags - define before early returns
  const isCompleted = job?.status === "completed" && job?.videoUrl
  const isRegenerating = job?.status === "regenerating"
  const isFailed = job?.status === "failed"
  const isQueued = job?.status === "queued" && !job?.currentStage
  const isProcessing = job?.status === "processing"
  const showVideoUI = (isCompleted || isRegenerating) && job?.videoUrl
  
  // Early returns after all hooks
  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" text="Loading..." />
      </div>
    )
  }
  
  // If job is loading AND we don't have any cached job data, show loading
  // But if we have cached data (even if stale), render the page with it
  const hasCachedJob = job?.id === jobId
  
  if (jobLoading && !hasCachedJob) {
    if (isSubmitting) {
      // Show cross-page loading modal (matches upload page modal)
      return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="w-[400px] rounded-lg bg-card p-6 shadow-lg border">
            <div className="flex flex-col items-center justify-center space-y-4">
              <LoadingSpinner size="lg" />
              <div className="text-center">
                <p className="text-lg font-semibold">Creating your video...</p>
                <p className="text-sm text-muted-foreground mt-2">
                  This may take a moment. Please wait while we process your request.
                </p>
              </div>
            </div>
          </div>
        </div>
      )
    }
    // Fallback: show spinner if modal isn't active
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" text="Loading job..." />
      </div>
    )
  }
  
  // If we're loading but have cached data, show a subtle loading indicator
  // but still render the page with cached data
  const showBackgroundLoading = jobLoading && hasCachedJob

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

  // If we don't have job data at all (not even cached), show error/loading
  // But give it a bit more time if we're still loading
  if (!job) {
    // If we're still loading, wait a bit more (maybe API is just slow)
    if (jobLoading) {
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
    
    // If we're not loading anymore and still no job, show error
    return (
      <div className="container mx-auto max-w-3xl px-4 py-8">
        <Alert variant="destructive">
          <AlertDescription>
            <div className="space-y-2">
              <div>Job not found or you don&apos;t have access to it</div>
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

  return (
    <>
      {/* Cross-page loading modal - persists until audio_parser starts */}
      {isSubmitting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 backdrop-blur-sm">
          <div className="w-[400px] rounded-lg bg-card p-6 shadow-lg border">
            <div className="flex flex-col items-center justify-center space-y-4">
              <LoadingSpinner size="lg" />
              <div className="text-center">
                <p className="text-lg font-semibold">Creating your video...</p>
                <p className="text-sm text-muted-foreground mt-2">
                  This may take a moment. Please wait while we process your request.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
      
      {/* Subtle background loading indicator when using cached data */}
      {showBackgroundLoading && (
        <div className="fixed top-4 right-4 z-40 rounded-lg bg-background/90 backdrop-blur-sm border px-3 py-2 shadow-lg">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span>Updating job status...</span>
          </div>
        </div>
      )}
      
      <div className="container mx-auto px-4 py-8 md:pl-[440px] md:max-w-none">
      <div className="mb-6">
        <Button
          variant="ghost"
          onClick={() => router.push("/upload")}
          className="mb-4"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to Upload
        </Button>
        
        {/* Sticky header with progress and video - pinned to top when video loaded */}
        {showVideoUI && (
          <div className="sticky top-0 z-30 bg-background/95 backdrop-blur-sm border-b pb-4 mb-6 -mx-4 px-4 -mt-4 pt-4 space-y-4">
            {isRegenerating && (
              <Alert>
                <AlertDescription className="flex items-center gap-2">
                  <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
                  <span>Regenerating clip... Your video will update when complete.</span>
                </AlertDescription>
              </Alert>
            )}
            {isCompleted && (
              <Alert>
                <AlertDescription>
                  Video generation completed successfully!
                </AlertDescription>
              </Alert>
            )}
            <VideoPlayer 
              videoUrl={job.videoUrl!} 
              jobId={jobId} 
              seekTo={selectedClipTimestamp}
            />
            {/* Clip Selector - right below video player */}
            <div className="w-full">
              <ClipSelector
                jobId={jobId}
                onClipSelect={(clipIndex, timestampStart) => {
                  setSelectedClipIndex(clipIndex)
                  setSelectedClipTimestamp(timestampStart)
                }}
                selectedClipIndex={selectedClipIndex}
                totalClips={undefined}
                refreshTrigger={clipRefreshTrigger}
              />
            </div>
            <ProgressTracker
              jobId={jobId}
              onComplete={handleComplete}
              onError={handleError}
            />
          </div>
        )}
        
        <Card className="w-full">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Job Progress</CardTitle>
                <CardDescription>Job ID: {jobId}</CardDescription>
              </div>
              {/* Timer aligned to the right of the title - get from job store */}
              {job?.estimatedRemaining != null && (isProcessing || isQueued || isRegenerating) && (
                <div className="text-sm font-mono text-muted-foreground self-center">
                  <span className="tabular-nums">{formatRemaining(job.estimatedRemaining)}</span>
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
                    <div className="space-y-3">
                      <div className="font-semibold">
                        {job.errorMessage || "Video generation failed"}
                      </div>
                      {/* Display detailed error information if available in error message */}
                      {job.errorMessage && (
                        <div className="mt-3 pt-3 border-t border-destructive/20">
                          <div className="text-sm space-y-2">
                            {/* Check if error message contains detailed clip failure information */}
                            {job.errorMessage.includes("Failed clips:") && (
                              <>
                                {job.errorMessage.split("\n\n").map((section, idx) => {
                                  if (section.includes("Failed clips:") || section.includes("Clip ")) {
                                    const lines = section.split("\n")
                                    const failedClipsLines = lines.filter(line => 
                                      line.trim().startsWith("Clip ") || line.trim().startsWith("Failed clips:")
                                    )
                                    if (failedClipsLines.length > 0) {
                                      return (
                                        <div key={idx} className="space-y-1">
                                          <div className="font-medium mb-2">Failed Clips Details:</div>
                                          {failedClipsLines.map((clipError, clipIdx) => {
                                            // Skip the "Failed clips:" header line
                                            if (clipError.trim() === "Failed clips:") return null
                                            return (
                                              <div key={clipIdx} className="pl-4 border-l-2 border-destructive/30 text-xs font-mono break-words">
                                                {clipError.trim()}
                                              </div>
                                            )
                                          })}
                                        </div>
                                      )
                                    }
                                  }
                                  return null
                                })}
                              </>
                            )}
                            {/* If error message is long, show it in a scrollable area */}
                            {job.errorMessage.length > 200 && (
                              <details className="mt-2">
                                <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
                                  Show full error message
                                </summary>
                                <pre className="mt-2 text-xs p-2 bg-destructive/10 rounded overflow-auto max-h-60 font-mono whitespace-pre-wrap break-words">
                                  {job.errorMessage}
                                </pre>
                              </details>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
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
                {showVideoUI ? (
                  <>
                    {/* Floating ClipChatbot - positioned fixed at bottom-left */}
                    <ClipChatbot
                      jobId={jobId}
                      audioUrl={job?.audioUrl ?? undefined}
                      selectedClipIndex={selectedClipIndex}
                      onClipSelect={(clipIndex, timestamp) => {
                        // Allow undefined to clear selection
                        setSelectedClipIndex(clipIndex === undefined ? undefined : clipIndex)
                        setSelectedClipTimestamp(timestamp)
                      }}
                      onRegenerationComplete={async (newVideoUrl) => {
                        // Refresh job to get updated video URL and trigger re-render
                        try {
                          await fetchJob(jobId)
                          console.log("✅ Regeneration complete! New video URL:", newVideoUrl)
                          
                          // Trigger ClipSelector refresh to show new thumbnails
                          setClipRefreshTrigger(prev => prev + 1)
                          console.log("✅ ClipSelector refresh triggered")
                          
                          // CRITICAL FIX: If comparison view is open for the regenerated clip,
                          // refresh it to show old vs. new (not new vs. new)
                          if (showComparison && selectedClipIndex !== undefined) {
                            // Give backend a moment to save the new version
                            setTimeout(async () => {
                              try {
                                await handleCompare(selectedClipIndex)
                                console.log("✅ Comparison refreshed after regeneration")
                              } catch (error) {
                                console.error("Failed to refresh comparison after regeneration:", error)
                              }
                            }, 500)
                          }
                        } catch (error) {
                          console.error("Failed to refresh job after regeneration:", error)
                        }
                      }}
                    />
                    
                    {/* Comparison Modal */}
                    {showComparison && comparisonData && selectedClipIndex !== undefined && (
                      <ClipComparison
                        originalClip={comparisonData.original}
                        regeneratedClip={comparisonData.regenerated ?? null}
                        mode="side-by-side"
                        syncPlayback={true}
                        audioUrl={job?.audioUrl ?? undefined}
                        clipStartTime={comparisonData.clip_start_time ?? null}
                        clipEndTime={comparisonData.clip_end_time ?? null}
                        activeVersionNumber={comparisonData.active_version_number}
                        onClose={() => {
                          setShowComparison(false)
                          setComparisonData(null)
                          localStorage.removeItem(comparisonStateKey)
                        }}
                        onRevert={handleRevert}
                        clipIndex={selectedClipIndex}
                      />
                    )}
                  </>
                ) : (
                  /* Show progress when video not loaded yet */
                  <ProgressTracker
                    jobId={jobId}
                    onComplete={handleComplete}
                    onError={handleError}
                  />
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
    </>
  )
}

