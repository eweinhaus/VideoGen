"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { X, RotateCcw, Play, Pause, Maximize, Minimize } from "lucide-react"
import { formatDuration } from "@/lib/utils"

interface ClipVersion {
  video_url: string | null
  thumbnail_url: string | null
  prompt: string
  version_number: number
  duration: number
  user_instruction?: string | null
  cost?: number | null
}

interface ClipComparisonProps {
  originalClip: ClipVersion
  regeneratedClip: ClipVersion
  mode?: "side-by-side"
  syncPlayback?: boolean
  onClose: () => void
}

export function ClipComparison({
  originalClip,
  regeneratedClip,
  mode = "side-by-side",
  syncPlayback = true,
  onClose,
}: ClipComparisonProps) {
  const [isLoading, setIsLoading] = useState(true)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isSynced, setIsSynced] = useState(syncPlayback)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  
  const originalVideoRef = useRef<HTMLVideoElement>(null)
  const regeneratedVideoRef = useRef<HTMLVideoElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  
  const [originalTime, setOriginalTime] = useState(0)
  const [regeneratedTime, setRegeneratedTime] = useState(0)
  
  // Calculate duration mismatch
  const originalDuration = originalClip.duration || 0
  const regeneratedDuration = regeneratedClip.duration || 0
  const durationMismatch = Math.abs(originalDuration - regeneratedDuration) > 0.1
  const shorterDuration = Math.min(originalDuration, regeneratedDuration)
  
  // Handle video load
  useEffect(() => {
    let loadedCount = 0
    const checkLoaded = () => {
      loadedCount++
      const totalVideos = (originalClip.video_url ? 1 : 0) + (regeneratedClip.video_url ? 1 : 0)
      if (loadedCount >= totalVideos || totalVideos === 0) {
        setIsLoading(false)
      }
    }
    
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedVideoRef.current
    
    const cleanup: (() => void)[] = []
    
    if (originalVideo && originalClip.video_url) {
      const handleLoaded = () => checkLoaded()
      const handleError = () => {
        setError("Failed to load original video")
        checkLoaded()
      }
      originalVideo.addEventListener("loadeddata", handleLoaded)
      originalVideo.addEventListener("error", handleError)
      cleanup.push(() => {
        originalVideo.removeEventListener("loadeddata", handleLoaded)
        originalVideo.removeEventListener("error", handleError)
      })
    } else {
      checkLoaded() // No video URL, count as loaded
    }
    
    if (regeneratedVideo && regeneratedClip.video_url) {
      const handleLoaded = () => checkLoaded()
      const handleError = () => {
        setError("Failed to load regenerated video")
        checkLoaded()
      }
      regeneratedVideo.addEventListener("loadeddata", handleLoaded)
      regeneratedVideo.addEventListener("error", handleError)
      cleanup.push(() => {
        regeneratedVideo.removeEventListener("loadeddata", handleLoaded)
        regeneratedVideo.removeEventListener("error", handleError)
      })
    } else {
      checkLoaded() // No video URL, count as loaded
    }
    
    return () => {
      cleanup.forEach(fn => fn())
    }
  }, [originalClip.video_url, regeneratedClip.video_url])
  
  // Synchronized playback
  const handlePlay = useCallback(async () => {
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedVideoRef.current
    
    if (isSynced) {
      // Sync both videos
      if (originalVideo && regeneratedVideo) {
        if (isPlaying) {
          originalVideo.pause()
          regeneratedVideo.pause()
        } else {
          // Sync to shorter duration if different
          if (durationMismatch) {
            const syncTime = Math.min(
              originalVideo.currentTime || 0,
              regeneratedVideo.currentTime || 0
            )
            originalVideo.currentTime = syncTime
            regeneratedVideo.currentTime = syncTime
          }
          await Promise.all([originalVideo.play(), regeneratedVideo.play()])
        }
      }
    } else {
      // Independent playback
      if (originalVideo) {
        if (isPlaying) {
          originalVideo.pause()
        } else {
          await originalVideo.play()
        }
      }
      if (regeneratedVideo) {
        if (isPlaying) {
          regeneratedVideo.pause()
        } else {
          await regeneratedVideo.play()
        }
      }
    }
    
    setIsPlaying(!isPlaying)
  }, [isSynced, isPlaying, durationMismatch])
  
  // Sync seek position (for synchronized mode)
  useEffect(() => {
    if (!isSynced) return
    
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedVideoRef.current
    
    if (!originalVideo || !regeneratedVideo) return
    
    const syncVideos = () => {
      if (durationMismatch) {
        // Sync to shorter duration
        const shorterTime = Math.min(
          originalVideo.currentTime || 0,
          regeneratedVideo.currentTime || 0
        )
        originalVideo.currentTime = shorterTime
        regeneratedVideo.currentTime = shorterTime
      } else {
        // Sync to same time
        const syncTime = originalVideo.currentTime || regeneratedVideo.currentTime || 0
        originalVideo.currentTime = syncTime
        regeneratedVideo.currentTime = syncTime
      }
    }
    
    originalVideo.addEventListener("seeked", syncVideos)
    regeneratedVideo.addEventListener("seeked", syncVideos)
    
    return () => {
      originalVideo.removeEventListener("seeked", syncVideos)
      regeneratedVideo.removeEventListener("seeked", syncVideos)
    }
  }, [isSynced, durationMismatch])
  
  // Update timestamps
  useEffect(() => {
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedVideoRef.current
    
    const updateTimestamps = () => {
      if (originalVideo) {
        setOriginalTime(originalVideo.currentTime)
      }
      if (regeneratedVideo) {
        setRegeneratedTime(regeneratedVideo.currentTime)
      }
    }
    
    const interval = setInterval(updateTimestamps, 100) // Update every 100ms
    
    if (originalVideo) {
      originalVideo.addEventListener("timeupdate", updateTimestamps)
    }
    if (regeneratedVideo) {
      regeneratedVideo.addEventListener("timeupdate", updateTimestamps)
    }
    
    return () => {
      clearInterval(interval)
      if (originalVideo) {
        originalVideo.removeEventListener("timeupdate", updateTimestamps)
      }
      if (regeneratedVideo) {
        regeneratedVideo.removeEventListener("timeupdate", updateTimestamps)
      }
    }
  }, [])
  
  // Fullscreen handling
  const enterFullscreen = useCallback(async () => {
    if (containerRef.current) {
      try {
        if (containerRef.current.requestFullscreen) {
          await containerRef.current.requestFullscreen()
          setIsFullscreen(true)
        }
      } catch (e) {
        console.error("Failed to enter fullscreen:", e)
      }
    }
  }, [])
  
  const exitFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      document.exitFullscreen()
      setIsFullscreen(false)
    }
  }, [])
  
  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === " ") {
        e.preventDefault()
        handlePlay()
      } else if (e.key === "Escape" && isFullscreen) {
        exitFullscreen()
      }
    }
    
    window.addEventListener("keydown", handleKeyPress)
    return () => window.removeEventListener("keydown", handleKeyPress)
  }, [handlePlay, isFullscreen, exitFullscreen])
  
  useEffect(() => {
    const handleFullscreenChange = () => {
      setIsFullscreen(!!document.fullscreenElement)
    }
    
    document.addEventListener("fullscreenchange", handleFullscreenChange)
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange)
  }, [])
  
  // Toggle left/right
  const [isSwapped, setIsSwapped] = useState(false)
  const toggleSwap = () => {
    setIsSwapped(!isSwapped)
  }
  
  const leftClip = isSwapped ? regeneratedClip : originalClip
  const rightClip = isSwapped ? originalClip : regeneratedClip
  const leftVideoRef = isSwapped ? regeneratedVideoRef : originalVideoRef
  const rightVideoRef = isSwapped ? originalVideoRef : regeneratedVideoRef
  
  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4">
      <div
        ref={containerRef}
        className="bg-white rounded-lg shadow-xl w-full max-w-7xl max-h-[90vh] overflow-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-xl font-semibold">Compare Clip Versions</h2>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={toggleSwap}
              title="Swap left/right"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={isFullscreen ? exitFullscreen : enterFullscreen}
              title={isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
            >
              {isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
            </Button>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
        
        {/* Content */}
        <div className="p-4">
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}
          
          {durationMismatch && (
            <Alert className="mb-4">
              <AlertDescription>
                Duration mismatch: {originalDuration.toFixed(1)}s vs {regeneratedDuration.toFixed(1)}s
                {isSynced && ` (synced to ${shorterDuration.toFixed(1)}s)`}
              </AlertDescription>
            </Alert>
          )}
          
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <LoadingSpinner />
            </div>
          )}
          
          {/* Video comparison */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            {/* Left video (original or swapped) */}
            <div className="space-y-2">
              <div className="text-sm font-medium">
                {isSwapped ? "Regenerated" : "Original"} (v{leftClip.version_number})
              </div>
              <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
                {leftClip.thumbnail_url && isLoading && (
                  <img
                    src={leftClip.thumbnail_url}
                    alt="Thumbnail"
                    className="w-full h-full object-cover"
                  />
                )}
                {leftClip.video_url ? (
                  <video
                    ref={leftVideoRef}
                    src={leftClip.video_url}
                    className="w-full h-full"
                    controls
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-white">
                    Video not available
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-600">
                Time: {formatDuration(leftClip === originalClip ? originalTime : regeneratedTime)}
              </div>
              <div className="text-xs text-gray-500 line-clamp-2">
                {leftClip.prompt}
              </div>
            </div>
            
            {/* Right video (regenerated or swapped) */}
            <div className="space-y-2">
              <div className="text-sm font-medium">
                {isSwapped ? "Original" : "Regenerated"} (v{rightClip.version_number})
                {rightClip.user_instruction && (
                  <span className="text-xs text-gray-500 ml-2">
                    &quot;{rightClip.user_instruction}&quot;
                  </span>
                )}
              </div>
              <div className="relative bg-black rounded-lg overflow-hidden aspect-video">
                {rightClip.thumbnail_url && isLoading && (
                  <img
                    src={rightClip.thumbnail_url}
                    alt="Thumbnail"
                    className="w-full h-full object-cover"
                  />
                )}
                {rightClip.video_url ? (
                  <video
                    ref={rightVideoRef}
                    src={rightClip.video_url}
                    className="w-full h-full"
                    controls
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-white">
                    Video not available
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-600">
                Time: {formatDuration(rightClip === regeneratedClip ? regeneratedTime : originalTime)}
              </div>
              <div className="text-xs text-gray-500 line-clamp-2">
                {rightClip.prompt}
              </div>
            </div>
          </div>
          
          {/* Controls */}
          <div className="flex items-center justify-center gap-4">
            <Button onClick={handlePlay} variant="default">
              {isPlaying ? (
                <>
                  <Pause className="h-4 w-4 mr-2" />
                  Pause
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Play
                </>
              )}
            </Button>
            <Button
              variant={isSynced ? "default" : "outline"}
              onClick={() => setIsSynced(!isSynced)}
            >
              {isSynced ? "Synchronized" : "Independent"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

