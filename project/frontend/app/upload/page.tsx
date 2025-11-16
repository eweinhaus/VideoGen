"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { AudioUploader } from "@/components/AudioUploader"
import { PromptInput } from "@/components/PromptInput"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { StepSelector, type PipelineStage } from "@/components/StepSelector"
import { useAuth } from "@/hooks/useAuth"
import { uploadStore } from "@/stores/uploadStore"
import { jobStore } from "@/stores/jobStore"

export default function UploadPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading: authLoading, user, token } = useAuth()
  const {
    audioFile,
    userPrompt,
    stopAtStage,
    isSubmitting,
    errors,
    setAudioFile,
    setUserPrompt,
    setStopAtStage,
    submit,
    reset,
  } = uploadStore()

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      console.log("Not authenticated, redirecting to login")
      router.push("/login")
    } else if (!authLoading && isAuthenticated) {
      console.log("✅ Authenticated on upload page, user:", user?.email)
      console.log("✅ Token available:", !!token)
    }
  }, [isAuthenticated, authLoading, router, user, token])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    console.log("📤 Submit button clicked")
    console.log("Auth state:", {
      isAuthenticated,
      hasToken: !!token,
      userEmail: user?.email
    })

    try {
      const jobId = await submit()
      console.log("✅ Upload successful, jobId:", jobId)
      
      // Ensure isSubmitting is reset before navigation
      // Use window.location for more reliable navigation
      if (jobId) {
        // Pre-fetch the job to ensure it's in the store before navigation
        try {
          await jobStore.getState().fetchJob(jobId)
        } catch (err) {
          console.warn("⚠️ Failed to pre-fetch job, but continuing with navigation:", err)
        }
        // Use window.location for more reliable navigation
        window.location.href = `/jobs/${jobId}`
      } else {
        console.error("❌ No jobId returned from submit")
        // Reset submitting state manually
        uploadStore.getState().reset()
      }
    } catch (error: any) {
      console.error("❌ Upload failed:", error)
      // Error is handled by uploadStore, but ensure isSubmitting is reset
      // The uploadStore should handle this, but we'll add a safety check
      setTimeout(() => {
        if (uploadStore.getState().isSubmitting) {
          console.warn("⚠️ isSubmitting still true after error, resetting...")
          uploadStore.getState().reset()
        }
      }, 1000)
    }
  }

  const isFormValid =
    audioFile !== null &&
    userPrompt.length >= 50 &&
    userPrompt.length <= 500 &&
    !errors.audio &&
    !errors.prompt

  if (authLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingSpinner size="lg" text="Loading..." />
      </div>
    )
  }

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Create Music Video</CardTitle>
          <CardDescription>
            Upload your audio file and describe your vision for the video
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label className="text-sm font-medium">Audio File</label>
              <AudioUploader
                value={audioFile}
                onChange={setAudioFile}
                error={errors.audio}
                disabled={isSubmitting}
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Creative Prompt</label>
              <PromptInput
                value={userPrompt}
                onChange={setUserPrompt}
                error={errors.prompt}
                disabled={isSubmitting}
              />
            </div>

            <StepSelector
              value={stopAtStage}
              onChange={setStopAtStage}
              disabled={isSubmitting}
            />

            {errors.audio || errors.prompt ? (
              <Alert variant="destructive">
                <AlertDescription>
                  Please fix the errors above before submitting
                </AlertDescription>
              </Alert>
            ) : null}

            <div className="flex gap-4">
              <Button
                type="submit"
                disabled={!isFormValid || isSubmitting}
                className="flex-1"
              >
                {isSubmitting ? "Submitting..." : "Generate Video"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={reset}
                disabled={isSubmitting}
              >
                Reset
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}

