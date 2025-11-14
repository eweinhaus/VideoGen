"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { AudioUploader } from "@/components/AudioUploader"
import { PromptInput } from "@/components/PromptInput"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { useAuth } from "@/hooks/useAuth"
import { uploadStore } from "@/stores/uploadStore"

export default function UploadPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const {
    audioFile,
    userPrompt,
    isSubmitting,
    errors,
    setAudioFile,
    setUserPrompt,
    submit,
    reset,
  } = uploadStore()

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, authLoading, router])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    try {
      const jobId = await submit()
      router.push(`/jobs/${jobId}`)
    } catch (error: any) {
      // Error is handled by uploadStore
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

