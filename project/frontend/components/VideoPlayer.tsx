"use client"

import { useState, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { Download } from "lucide-react"
import { downloadVideo } from "@/lib/api"
import { APIError } from "@/types/api"

interface VideoPlayerProps {
  videoUrl: string
  jobId: string
  autoPlay?: boolean
  seekTo?: number // Timestamp in seconds to seek to
}

export function VideoPlayer({
  videoUrl,
  jobId,
  autoPlay = false,
  seekTo,
}: VideoPlayerProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [isDownloading, setIsDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const videoRef = useRef<HTMLVideoElement>(null)

  // Reset loading state when video URL changes (e.g., after recomposition)
  useEffect(() => {
    if (videoUrl) {
      setIsLoading(true)
      setError(null)
    }
  }, [videoUrl])

  // Seek to specific timestamp when seekTo prop changes
  useEffect(() => {
    if (seekTo !== undefined && videoRef.current && !isLoading) {
      const video = videoRef.current
      // Add small offset to compensate for keyframe seeking
      // Browsers seek to nearest keyframe which is often slightly before requested time
      const adjustedSeekTime = seekTo + 0.04 // Add 40ms (1 frame at 24fps)
      
      // Wait for video to be ready before seeking
      if (video.readyState >= 2) {
        // readyState 2 = HAVE_CURRENT_DATA
        video.currentTime = adjustedSeekTime
        
        // Verify seek position after a short delay
        setTimeout(() => {
          if (video.currentTime < seekTo) {
            // Still too early, try again
            video.currentTime = adjustedSeekTime
          }
        }, 100)
      } else {
        // Wait for video to load metadata before seeking
        const handleLoadedMetadata = () => {
          video.currentTime = adjustedSeekTime
          
          // Verify seek position after a short delay
          setTimeout(() => {
            if (video.currentTime < seekTo) {
              video.currentTime = adjustedSeekTime
            }
          }, 100)
          
          video.removeEventListener("loadedmetadata", handleLoadedMetadata)
        }
        video.addEventListener("loadedmetadata", handleLoadedMetadata)
        return () => {
          video.removeEventListener("loadedmetadata", handleLoadedMetadata)
        }
      }
    }
  }, [seekTo, isLoading])

  const handleVideoLoad = () => {
    setIsLoading(false)
  }

  const handleVideoError = () => {
    setIsLoading(false)
    setError("Failed to load video")
  }

  const handleDownload = async () => {
    setIsDownloading(true)
    setError(null)

    try {
      const blob = await downloadVideo(jobId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `music_video_${jobId}.mp4`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError("Download failed")
      }
    } finally {
      setIsDownloading(false)
    }
  }

  return (
    <div className="w-full space-y-4">
      <div className="relative aspect-video w-full overflow-hidden rounded-lg bg-black">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center">
            <LoadingSpinner size="lg" text="Loading video..." />
          </div>
        )}
        <video
          ref={videoRef}
          key={videoUrl} // Force re-mount when URL changes
          src={videoUrl}
          controls
          preload="metadata"
          playsInline
          onLoadedData={handleVideoLoad}
          onError={handleVideoError}
          className="h-full w-full"
          autoPlay={autoPlay}
        />
      </div>

      <div className="flex justify-center">
        <Button
          onClick={handleDownload}
          disabled={isDownloading || !!error}
          className="gap-2"
        >
          <Download className="h-4 w-4" />
          {isDownloading ? "Downloading..." : "Download Video"}
        </Button>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

