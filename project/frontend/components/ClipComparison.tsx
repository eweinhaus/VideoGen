"use client"

import { useState, useRef, useEffect, useCallback } from "react"
import Image from "next/image"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { X, RotateCcw, Play, Pause, Maximize, Minimize, Volume2, VolumeX } from "lucide-react"
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
  regeneratedClip: ClipVersion | null
  mode?: "side-by-side"
  syncPlayback?: boolean
  audioUrl?: string | null
  onClose: () => void
  onRevert?: (clipIndex: number, versionNumber: number) => Promise<void>
  clipIndex?: number
  clipStartTime?: number | null  // Start time of clip in full audio (for trimming)
  clipEndTime?: number | null    // End time of clip in full audio (for trimming)
  activeVersionNumber?: number   // NEW: which version is currently in main video
}

export function ClipComparison({
  originalClip,
  regeneratedClip,
  mode = "side-by-side",
  syncPlayback = true,
  audioUrl,
  onClose,
  onRevert,
  clipIndex,
  clipStartTime,
  clipEndTime,
  activeVersionNumber,
}: ClipComparisonProps) {
  // CRITICAL: Log props on mount to see what we're receiving
  useEffect(() => {
    console.log("🎬 ClipComparison received props:", {
      originalClipVersion: originalClip.version_number,
      originalClipUrl: originalClip.video_url,
      regeneratedClipVersion: regeneratedClip?.version_number,
      regeneratedClipUrl: regeneratedClip?.video_url,
      activeVersionNumber,
      versionsMatch: originalClip.version_number === regeneratedClip?.version_number,
      urlsMatch: originalClip.video_url === regeneratedClip?.video_url,
      BUG_DETECTED_IN_PROPS: originalClip.version_number === regeneratedClip?.version_number || originalClip.video_url === regeneratedClip?.video_url
    })
  }, []) // Only log on mount
  
  const [isLoading, setIsLoading] = useState(true)
  const [isPlaying, setIsPlaying] = useState(false)
  const [isSynced, setIsSynced] = useState(syncPlayback)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isReverting, setIsReverting] = useState(false)
  const [activeVersion, setActiveVersion] = useState<number>(
    activeVersionNumber ?? (regeneratedClip?.version_number ?? 1)
  )
  
  // Debug logging for active version
  useEffect(() => {
    console.log("🔍 ClipComparison Active Version Debug:", {
      activeVersionNumber,
      regeneratedClipVersion: regeneratedClip?.version_number,
      originalClipVersion: originalClip.version_number,
      initializedActiveVersion: activeVersion,
      buttonShouldSay: activeVersion === regeneratedClip?.version_number ? "Revert to Prior Version" : "Change clip to latest version",
      originalVideoUrl: originalClip.video_url?.substring(0, 100),
      regeneratedVideoUrl: regeneratedClip?.video_url?.substring(0, 100),
      urlsMatch: originalClip.video_url === regeneratedClip?.video_url,
      versionsMatch: originalClip.version_number === regeneratedClip?.version_number,
      BUG_DETECTED: originalClip.version_number === regeneratedClip?.version_number || originalClip.video_url === regeneratedClip?.video_url
    })
    
    // CRITICAL BUG DETECTION: If both clips have the same version number or URL, this is a bug
    if (regeneratedClip && (originalClip.version_number === regeneratedClip.version_number || originalClip.video_url === regeneratedClip.video_url)) {
      console.error("🚨 BUG DETECTED: Both original and regenerated clips are the same!", {
        originalVersion: originalClip.version_number,
        regeneratedVersion: regeneratedClip.version_number,
        originalUrl: originalClip.video_url?.substring(0, 100),
        regeneratedUrl: regeneratedClip.video_url?.substring(0, 100),
        versionsMatch: originalClip.version_number === regeneratedClip.version_number,
        urlsMatch: originalClip.video_url === regeneratedClip.video_url
      })
    }
  }, [activeVersionNumber, regeneratedClip?.version_number, originalClip.version_number, activeVersion, originalClip.video_url, regeneratedClip?.video_url])
  
  // Update activeVersion when activeVersionNumber prop changes
  useEffect(() => {
    if (activeVersionNumber !== undefined && activeVersionNumber !== null) {
      console.log(`🔄 Updating activeVersion from prop: ${activeVersionNumber}`)
      setActiveVersion(activeVersionNumber)
    }
  }, [activeVersionNumber])
  
  const originalVideoRef = useRef<HTMLVideoElement>(null)
  const regeneratedVideoRef = useRef<HTMLVideoElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  
  const [originalTime, setOriginalTime] = useState(0)
  const [regeneratedTime, setRegeneratedTime] = useState(0)
  const [originalVideoDuration, setOriginalVideoDuration] = useState<number | null>(null)
  const [regeneratedVideoDuration, setRegeneratedVideoDuration] = useState<number | null>(null)
  const [audioVolume, setAudioVolume] = useState(1.0) // Volume range: 0.0 to 1.0
  
  // CRITICAL: Ensure audio is positioned at clip start time when component mounts or boundaries change
  useEffect(() => {
    const audio = audioRef.current
    if (audio && clipStartTime !== null && clipStartTime !== undefined && audioUrl) {
      // Reset audio to clip start time (beginning of this clip's audio segment)
      // This ensures audio doesn't play from the beginning of the full track
      audio.currentTime = clipStartTime
      console.log(`🎵 Audio reset to clip start time: ${clipStartTime}s (clip ${clipIndex})`)
    }
  }, [clipStartTime, audioUrl, clipIndex])
  
  // Update audio volume when volume state changes
  useEffect(() => {
    const audio = audioRef.current
    if (audio) {
      audio.volume = audioVolume
    }
  }, [audioVolume])
  
  // Calculate duration mismatch - use video element duration if available, otherwise use clip duration
  const originalDuration = (originalVideoDuration ?? originalClip.duration) || 0
  const regeneratedDuration = (regeneratedVideoDuration ?? regeneratedClip?.duration) || 0
  const durationMismatch = regeneratedClip ? Math.abs(originalDuration - regeneratedDuration) > 0.1 : false
  const shorterDuration = regeneratedClip ? Math.min(originalDuration, regeneratedDuration) : originalDuration
  
  // Handle video load
  useEffect(() => {
    let loadedCount = 0
    const checkLoaded = () => {
      loadedCount++
      const totalVideos = (originalClip.video_url ? 1 : 0) + (regeneratedClip?.video_url ? 1 : 0)
      if (loadedCount >= totalVideos || totalVideos === 0) {
        setIsLoading(false)
      }
    }
    
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedVideoRef.current
    
    const cleanup: (() => void)[] = []
    
    if (originalVideo && originalClip.video_url) {
      const handleLoaded = () => {
        // Extract duration from video element if available
        if (originalVideo.duration && isFinite(originalVideo.duration)) {
          setOriginalVideoDuration(originalVideo.duration)
        }
        checkLoaded()
      }
      const handleError = () => {
        setError("Failed to load original video")
        checkLoaded()
      }
      originalVideo.addEventListener("loadeddata", handleLoaded)
      originalVideo.addEventListener("loadedmetadata", handleLoaded) // Also listen for metadata
      originalVideo.addEventListener("durationchange", handleLoaded) // Duration might change
      originalVideo.addEventListener("error", handleError)
      cleanup.push(() => {
        originalVideo.removeEventListener("loadeddata", handleLoaded)
        originalVideo.removeEventListener("loadedmetadata", handleLoaded)
        originalVideo.removeEventListener("durationchange", handleLoaded)
        originalVideo.removeEventListener("error", handleError)
      })
    } else {
      checkLoaded() // No video URL, count as loaded
    }
    
    if (regeneratedClip && regeneratedVideo && regeneratedClip.video_url) {
      const handleLoaded = () => {
        // Extract duration from video element if available
        if (regeneratedVideo.duration && isFinite(regeneratedVideo.duration)) {
          setRegeneratedVideoDuration(regeneratedVideo.duration)
        }
        checkLoaded()
      }
      const handleError = () => {
        setError("Failed to load regenerated video")
        checkLoaded()
      }
      regeneratedVideo.addEventListener("loadeddata", handleLoaded)
      regeneratedVideo.addEventListener("loadedmetadata", handleLoaded) // Also listen for metadata
      regeneratedVideo.addEventListener("durationchange", handleLoaded) // Duration might change
      regeneratedVideo.addEventListener("error", handleError)
      cleanup.push(() => {
        regeneratedVideo.removeEventListener("loadeddata", handleLoaded)
        regeneratedVideo.removeEventListener("loadedmetadata", handleLoaded)
        regeneratedVideo.removeEventListener("durationchange", handleLoaded)
        regeneratedVideo.removeEventListener("error", handleError)
      })
    } else {
      checkLoaded() // No video URL or no regenerated clip, count as loaded
    }
    
    return () => {
      cleanup.forEach(fn => fn())
    }
  }, [originalClip.video_url, regeneratedClip])
  
  // Synchronized playback
  const handlePlay = useCallback(async () => {
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedVideoRef.current
    const audio = audioRef.current
    
    if (isSynced && regeneratedClip) {
      // Sync both videos and audio
      if (originalVideo && regeneratedVideo) {
        if (isPlaying) {
          originalVideo.pause()
          regeneratedVideo.pause()
          if (audio) audio.pause()
        } else {
          // CRITICAL: Ensure videos start at 0 for clip comparison
          // Reset video positions to start of clip
          originalVideo.currentTime = 0
          regeneratedVideo.currentTime = 0
          
          // Sync to shorter duration if different
          if (durationMismatch) {
            const syncTime = Math.min(
              originalVideo.currentTime || 0,
              regeneratedVideo.currentTime || 0
            )
            originalVideo.currentTime = syncTime
            regeneratedVideo.currentTime = syncTime
            // For audio with clip boundaries, sync relative to clip start
            if (audio && clipStartTime !== null && clipStartTime !== undefined) {
              // CRITICAL: Audio should start at clipStartTime (beginning of this clip's audio segment)
              audio.currentTime = clipStartTime + syncTime
              console.log(`🎵 Audio synced to clip start: ${clipStartTime}s + video time: ${syncTime}s = ${audio.currentTime}s`)
            } else if (audio) {
              audio.currentTime = syncTime
            }
          } else {
            // Sync audio to video time (starting from clip start)
            const syncTime = originalVideo.currentTime || 0
            if (audio && clipStartTime !== null && clipStartTime !== undefined) {
              // CRITICAL: Audio should start at clipStartTime (beginning of this clip's audio segment)
              audio.currentTime = clipStartTime + syncTime
              console.log(`🎵 Audio synced to clip start: ${clipStartTime}s + video time: ${syncTime}s = ${audio.currentTime}s`)
            } else if (audio) {
              audio.currentTime = syncTime
            }
          }
          await Promise.all([originalVideo.play(), regeneratedVideo.play()])
          if (audio) {
            // Ensure audio is at correct position before playing
            if (clipStartTime !== null && clipStartTime !== undefined) {
              audio.currentTime = clipStartTime + (originalVideo.currentTime || 0)
            }
            await audio.play()
          }
        }
      }
    } else {
      // Independent playback mode
      // Play/pause both videos independently, but sync audio to the playing video
      
      const willBePlaying = !isPlaying
      
      // Control video playback
      if (originalVideo) {
        if (isPlaying) {
          originalVideo.pause()
        } else {
          // Reset to start of clip when starting playback
          originalVideo.currentTime = 0
          try {
            await originalVideo.play()
          } catch (e) {
            console.warn("Failed to play original video:", e)
          }
        }
      }
      if (regeneratedClip && regeneratedVideo) {
        if (isPlaying) {
          regeneratedVideo.pause()
        } else {
          // Reset to start of clip when starting playback
          regeneratedVideo.currentTime = 0
          try {
            await regeneratedVideo.play()
          } catch (e) {
            console.warn("Failed to play regenerated video:", e)
          }
        }
      }
      
      // Handle audio: Play if we're starting playback (regardless of number of videos)
      // Sync audio to first available video's time + clip start offset
      if (audio) {
        if (isPlaying) {
          // Pausing
          audio.pause()
        } else if (willBePlaying) {
          // Starting playback
          // Sync audio to first available video
          const syncVideo = originalVideo || regeneratedVideo
          if (syncVideo) {
            try {
              // CRITICAL: If we have clip boundaries, audio should start at clipStartTime (beginning of clip's audio segment)
              if (clipStartTime !== null && clipStartTime !== undefined) {
                const videoTime = syncVideo.currentTime || 0
                audio.currentTime = clipStartTime + videoTime
                console.log(`🎵 Audio synced to clip start: ${clipStartTime}s + video time: ${videoTime}s = ${audio.currentTime}s`)
              } else {
                audio.currentTime = syncVideo.currentTime || 0
              }
              await audio.play()
            } catch (e) {
              console.warn("Failed to play audio:", e)
            }
          }
        }
      }
    }
    
    setIsPlaying(!isPlaying)
  }, [isSynced, isPlaying, durationMismatch, regeneratedClip, clipStartTime])
  
  // Sync seek position (for synchronized mode)
  useEffect(() => {
    if (!isSynced || !regeneratedClip) return
    
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedVideoRef.current
    const audio = audioRef.current
    
    if (!originalVideo || !regeneratedVideo) return
    
    let isSyncing = false  // Prevent infinite loop from mutual triggering
    
    const syncVideos = (sourceVideo: HTMLVideoElement, targetVideo: HTMLVideoElement) => {
      if (isSyncing) return
      isSyncing = true
      
      try {
        const sourceTime = sourceVideo.currentTime || 0
        
        if (durationMismatch) {
          // Sync to shorter duration
          const maxTime = Math.min(
            originalVideo.duration || 0,
            regeneratedVideo.duration || 0
          )
          const targetTime = Math.min(sourceTime, maxTime)
          targetVideo.currentTime = targetTime
          // CRITICAL: Sync audio to clip start + video time (not just video time)
          if (audio) {
            if (clipStartTime !== null && clipStartTime !== undefined) {
              audio.currentTime = clipStartTime + targetTime
            } else {
              audio.currentTime = targetTime
            }
          }
        } else {
          // Sync to same time
          targetVideo.currentTime = sourceTime
          // CRITICAL: Sync audio to clip start + video time (not just video time)
          if (audio) {
            if (clipStartTime !== null && clipStartTime !== undefined) {
              audio.currentTime = clipStartTime + sourceTime
            } else {
              audio.currentTime = sourceTime
            }
          }
        }
      } finally {
        // Use setTimeout to reset flag after sync completes
        setTimeout(() => {
          isSyncing = false
        }, 50)
      }
    }
    
    const handleOriginalSeeked = () => syncVideos(originalVideo, regeneratedVideo)
    const handleRegeneratedSeeked = () => syncVideos(regeneratedVideo, originalVideo)
    
    originalVideo.addEventListener("seeked", handleOriginalSeeked)
    regeneratedVideo.addEventListener("seeked", handleRegeneratedSeeked)
    
    return () => {
      originalVideo.removeEventListener("seeked", handleOriginalSeeked)
      regeneratedVideo.removeEventListener("seeked", handleRegeneratedSeeked)
    }
  }, [isSynced, durationMismatch, regeneratedClip, clipStartTime])
  
  // Sync audio with video during playback (for independent mode)
  useEffect(() => {
    if (isSynced || !audioUrl || !audioRef.current) return
    
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedClip ? regeneratedVideoRef.current : null
    const audio = audioRef.current
    
    const syncAudioToVideo = () => {
      // Only sync if exactly one video is playing
      const originalPlaying = originalVideo && !originalVideo.paused
      const regeneratedPlaying = regeneratedVideo && !regeneratedVideo.paused
      
      if (originalPlaying && !regeneratedPlaying) {
        // CRITICAL: Sync audio to clip start + video time (not just video time)
        if (clipStartTime !== null && clipStartTime !== undefined) {
          audio.currentTime = clipStartTime + (originalVideo.currentTime || 0)
        } else {
          audio.currentTime = originalVideo.currentTime || 0
        }
      } else if (regeneratedPlaying && !originalPlaying) {
        // CRITICAL: Sync audio to clip start + video time (not just video time)
        if (clipStartTime !== null && clipStartTime !== undefined) {
          audio.currentTime = clipStartTime + (regeneratedVideo.currentTime || 0)
        } else {
          audio.currentTime = regeneratedVideo.currentTime || 0
        }
      }
    }
    
      if (originalVideo) {
        originalVideo.addEventListener("timeupdate", syncAudioToVideo)
      }
      if (regeneratedVideo) {
        regeneratedVideo.addEventListener("timeupdate", syncAudioToVideo)
      }
      
      return () => {
        if (originalVideo) {
          originalVideo.removeEventListener("timeupdate", syncAudioToVideo)
        }
        if (regeneratedVideo) {
          regeneratedVideo.removeEventListener("timeupdate", syncAudioToVideo)
        }
      }
    }, [isSynced, audioUrl, regeneratedClip, clipStartTime])
  
  // Update timestamps and enforce audio boundaries
  useEffect(() => {
    const originalVideo = originalVideoRef.current
    const regeneratedVideo = regeneratedClip ? regeneratedVideoRef.current : null
    const audio = audioRef.current
    
    const stopAudioAndVideos = () => {
      if (audio) {
        audio.pause()
        // Reset to clip start if boundaries exist
        if (clipStartTime !== null && clipStartTime !== undefined) {
          audio.currentTime = clipStartTime
        }
      }
      if (originalVideo) originalVideo.pause()
      if (regeneratedVideo) regeneratedVideo.pause()
      setIsPlaying(false)
    }
    
    const updateTimestamps = () => {
      if (originalVideo) {
        setOriginalTime(originalVideo.currentTime)
      }
      if (regeneratedVideo) {
        setRegeneratedTime(regeneratedVideo.currentTime)
      }
      
      // CRITICAL: Stop audio when video ends OR when audio reaches clip end time
      if (audio && isPlaying) {
        // Check if we've reached the end of either video
        const originalEnded = originalVideo && originalVideo.ended
        const regeneratedEnded = regeneratedVideo && regeneratedVideo.ended
        const originalNearEnd = originalVideo && originalVideo.currentTime >= (originalVideo.duration - 0.1)
        const regeneratedNearEnd = regeneratedVideo && regeneratedVideo.currentTime >= (regeneratedVideo.duration - 0.1)
        
        // Check if audio has reached clip end time
        const audioAtClipEnd = clipEndTime !== null && clipEndTime !== undefined && audio.currentTime >= clipEndTime
        
        // Stop if any video has ended or if audio reached clip end
        if (originalEnded || regeneratedEnded || originalNearEnd || regeneratedNearEnd || audioAtClipEnd) {
          console.log(`🛑 Stopping playback: originalEnded=${originalEnded}, regeneratedEnded=${regeneratedEnded}, audioAtClipEnd=${audioAtClipEnd}`)
          stopAudioAndVideos()
        }
      }
    }
    
    // Handle video ended events (more reliable than timeupdate checks)
    const handleOriginalEnded = () => {
      console.log("🛑 Original video ended, stopping audio")
      stopAudioAndVideos()
    }
    
    const handleRegeneratedEnded = () => {
      console.log("🛑 Regenerated video ended, stopping audio")
      stopAudioAndVideos()
    }
    
    const interval = setInterval(updateTimestamps, 100) // Update every 100ms
    
    if (originalVideo) {
      originalVideo.addEventListener("timeupdate", updateTimestamps)
      originalVideo.addEventListener("ended", handleOriginalEnded)
    }
    if (regeneratedVideo) {
      regeneratedVideo.addEventListener("timeupdate", updateTimestamps)
      regeneratedVideo.addEventListener("ended", handleRegeneratedEnded)
    }
    
    return () => {
      clearInterval(interval)
      if (originalVideo) {
        originalVideo.removeEventListener("timeupdate", updateTimestamps)
        originalVideo.removeEventListener("ended", handleOriginalEnded)
      }
      if (regeneratedVideo) {
        regeneratedVideo.removeEventListener("timeupdate", updateTimestamps)
        regeneratedVideo.removeEventListener("ended", handleRegeneratedEnded)
      }
    }
  }, [regeneratedClip, isPlaying, clipStartTime, clipEndTime])
  
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
      // Don't intercept keyboard shortcuts if user is typing in an input/textarea
      const target = e.target as HTMLElement
      const isTyping = target.tagName === 'INPUT' || 
                       target.tagName === 'TEXTAREA' || 
                       target.isContentEditable
      
      if (isTyping) {
        return // Let the input handle the key press normally
      }
      
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
  
  const leftClip = isSwapped && regeneratedClip ? regeneratedClip : originalClip
  const rightClip = isSwapped && regeneratedClip ? originalClip : regeneratedClip
  const leftVideoRef = isSwapped && regeneratedClip ? regeneratedVideoRef : originalVideoRef
  const rightVideoRef = isSwapped && regeneratedClip ? originalVideoRef : regeneratedVideoRef
  
  // CRITICAL DEBUG: Log which clips are being displayed
  useEffect(() => {
    console.log("🎬 ClipComparison Display Logic:", {
      isSwapped,
      leftClipVersion: leftClip.version_number,
      leftClipUrl: leftClip.video_url,
      rightClipVersion: rightClip?.version_number,
      rightClipUrl: rightClip?.video_url,
      originalClipVersion: originalClip.version_number,
      originalClipUrl: originalClip.video_url,
      regeneratedClipVersion: regeneratedClip?.version_number,
      regeneratedClipUrl: regeneratedClip?.video_url,
      BUG_DETECTED: leftClip.video_url === rightClip?.video_url || leftClip.version_number === rightClip?.version_number
    })
    
    if (rightClip && (leftClip.video_url === rightClip.video_url || leftClip.version_number === rightClip.version_number)) {
      console.error("🚨 BUG DETECTED: Left and right clips are the same!", {
        leftClipVersion: leftClip.version_number,
        rightClipVersion: rightClip.version_number,
        leftClipUrl: leftClip.video_url,
        rightClipUrl: rightClip.video_url,
        isSwapped,
        originalClipVersion: originalClip.version_number,
        regeneratedClipVersion: regeneratedClip?.version_number
      })
    }
  }, [isSwapped, leftClip, rightClip, originalClip, regeneratedClip])
  
  // Check if revert button should be shown
  const showRevertButton = regeneratedClip && onRevert && clipIndex !== undefined
  
  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4 lg:pl-[420px]">
      {/* Hidden audio element for synchronized playback */}
      {audioUrl && (
        <audio
          ref={audioRef}
          src={audioUrl}
          preload="metadata"
          onLoadedMetadata={() => {
            // Set audio time boundaries if clip start/end times are provided
            // This allows playing only the audio segment for this specific clip
            const audio = audioRef.current
            if (audio && clipStartTime !== null && clipStartTime !== undefined) {
              // CRITICAL: Set initial position to clip start time (beginning of this clip's audio segment)
              // This ensures audio is ready at the correct position when playback starts
              audio.currentTime = clipStartTime
              
              // Log for debugging
              console.log(`🎵 Audio initialized to clip boundaries: ${clipStartTime}s - ${clipEndTime || 'end'}s (clip ${clipIndex})`)
            } else {
              console.warn(`⚠️ No clip boundaries provided for audio trimming (clip ${clipIndex})`)
            }
          }}
          onTimeUpdate={() => {
            // Stop audio when reaching clip end time OR when videos end
            const audio = audioRef.current
            const originalVideo = originalVideoRef.current
            const regeneratedVideo = regeneratedVideoRef.current
            
            if (!audio) return
            
            // Check if audio reached clip end time
            const audioAtClipEnd = clipEndTime !== null && clipEndTime !== undefined && audio.currentTime >= clipEndTime
            
            // Check if any video has ended
            const originalEnded = originalVideo && originalVideo.ended
            const regeneratedEnded = regeneratedVideo && regeneratedVideo.ended
            
            // Stop if audio reached clip end OR if any video ended
            if (audioAtClipEnd || originalEnded || regeneratedEnded) {
              console.log(`🛑 Audio stopping: audioAtClipEnd=${audioAtClipEnd}, originalEnded=${originalEnded}, regeneratedEnded=${regeneratedEnded}`)
              audio.pause()
              // Reset to clip start for replay
              if (clipStartTime !== null && clipStartTime !== undefined) {
                audio.currentTime = clipStartTime
              }
              // Also pause videos if they're playing
              if (originalVideo) originalVideo.pause()
              if (regeneratedVideo) regeneratedVideo.pause()
              setIsPlaying(false)
            }
          }}
          onError={(e) => {
            console.warn("Failed to load audio:", e)
            // Don't show error to user, just log it
          }}
          style={{ display: "none" }}
        />
      )}
      <div
        ref={containerRef}
        className="bg-white rounded-lg shadow-xl w-full max-w-7xl 2xl:max-w-[90%] max-h-[90vh] overflow-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-xl font-semibold">Compare Clip Versions</h2>
          <div className="flex items-center gap-2">
            {/* Audio Volume Control */}
            {audioUrl && (
              <div className="flex items-center gap-2 px-2">
                <button
                  onClick={() => setAudioVolume(audioVolume > 0 ? 0 : 1.0)}
                  className="p-1 hover:bg-gray-100 rounded transition-colors"
                  title={audioVolume > 0 ? "Mute audio" : "Unmute audio"}
                >
                  {audioVolume > 0 ? (
                    <Volume2 className="h-4 w-4" />
                  ) : (
                    <VolumeX className="h-4 w-4" />
                  )}
                </button>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={audioVolume}
                  onChange={(e) => setAudioVolume(parseFloat(e.target.value))}
                  className="w-20 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary"
                  title={`Volume: ${Math.round(audioVolume * 100)}%`}
                />
                <span className="text-xs text-gray-500 w-8">
                  {Math.round(audioVolume * 100)}%
                </span>
              </div>
            )}
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
          {isReverting && (
            <Alert className="mb-4 bg-blue-50 border-blue-300">
              <div className="flex items-center gap-3">
                <LoadingSpinner className="h-4 w-4 flex-shrink-0" />
                <AlertDescription>
                  <strong>Recomposing video...</strong> This may take a few moments. The main video will update automatically when complete.
                </AlertDescription>
              </div>
            </Alert>
          )}
          
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
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
            {/* Left video (original or swapped) */}
            <div className="flex flex-col">
              <div className="text-sm font-medium min-h-[2.5rem] flex items-start mb-2">
                <span>
                  {isSwapped 
                    ? `Latest (v${leftClip.version_number})` 
                    : leftClip.version_number === 1 
                      ? `Original (v${leftClip.version_number})` 
                      : `Previous (v${leftClip.version_number})`
                  }
                </span>
              </div>
              <div className="relative bg-black rounded-lg overflow-hidden aspect-video flex-shrink-0">
                {leftClip.thumbnail_url && isLoading && (
                  <Image
                    src={leftClip.thumbnail_url}
                    alt="Thumbnail"
                    fill
                    className="object-cover"
                    unoptimized
                    onError={(e) => {
                      console.warn("Failed to load left clip thumbnail")
                      // Hide thumbnail on error - video will show instead
                      e.currentTarget.style.display = 'none'
                    }}
                  />
                )}
                {leftClip.video_url ? (
                  <video
                    key={`left-v${leftClip.version_number}-${leftClip.video_url.substring(0, 50)}`}
                    ref={leftVideoRef}
                    src={leftClip.video_url}
                    className="w-full h-full"
                    controls
                    onLoadStart={() => {
                      console.log(`🎥 Left video loading: v${leftClip.version_number}`, leftClip.video_url?.substring(0, 100))
                    }}
                    onLoadedData={() => {
                      const video = leftVideoRef.current
                      console.log(`✅ Left video loaded: v${leftClip.version_number}`, {
                        videoSrc: video?.src?.substring(0, 100),
                        expectedSrc: leftClip.video_url?.substring(0, 100),
                        matches: video?.src === leftClip.video_url
                      })
                    }}
                  />
                ) : (
                  <div className="flex items-center justify-center h-full text-white">
                    Video not available
                  </div>
                )}
              </div>
              <div className="text-xs text-gray-600 mt-2">
                Time: {formatDuration(leftClip === originalClip ? originalTime : regeneratedTime)}
              </div>
            </div>
            
            {/* Right video (regenerated or swapped) */}
            <div className="flex flex-col">
              {rightClip ? (
                <>
                  <div className="text-sm font-medium min-h-[2.5rem] flex items-start mb-2">
                    <span>
                      {isSwapped 
                        ? (rightClip.version_number === 1 ? `Original (v${rightClip.version_number})` : `Previous (v${rightClip.version_number})`)
                        : `Latest (v${rightClip.version_number})`
                      }
                      {rightClip.user_instruction && (
                        <span className="text-xs text-gray-500 ml-2 font-normal">
                          &quot;{rightClip.user_instruction}&quot;
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="relative bg-black rounded-lg overflow-hidden aspect-video flex-shrink-0">
                    {rightClip.thumbnail_url && isLoading && (
                      <Image
                        src={rightClip.thumbnail_url}
                        alt="Thumbnail"
                        fill
                        className="object-cover"
                        unoptimized
                        onError={(e) => {
                          console.warn("Failed to load right clip thumbnail")
                          // Hide thumbnail on error - video will show instead
                          e.currentTarget.style.display = 'none'
                        }}
                      />
                    )}
                    {rightClip.video_url ? (
                      <video
                        key={`right-v${rightClip.version_number}-${rightClip.video_url.substring(0, 50)}`}
                        ref={rightVideoRef}
                        src={rightClip.video_url}
                        className="w-full h-full"
                        controls
                        onLoadStart={() => {
                          console.log(`🎥 Right video loading: v${rightClip.version_number}`, rightClip.video_url?.substring(0, 100))
                        }}
                        onLoadedData={() => {
                          const video = rightVideoRef.current
                          console.log(`✅ Right video loaded: v${rightClip.version_number}`, {
                            videoSrc: video?.src?.substring(0, 100),
                            expectedSrc: rightClip.video_url?.substring(0, 100),
                            matches: video?.src === rightClip.video_url
                          })
                        }}
                      />
                    ) : (
                      <div className="flex items-center justify-center h-full text-white">
                        Video not available
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-gray-600 mt-2">
                    Time: {formatDuration(rightClip === regeneratedClip ? regeneratedTime : originalTime)}
                  </div>
                </>
              ) : (
                <>
                  <div className="text-sm font-medium text-gray-500">
                    Regenerated (Not Available)
                  </div>
                  <div className="relative bg-gray-100 rounded-lg overflow-hidden aspect-video flex items-center justify-center">
                    <div className="text-center text-gray-500 p-4">
                      <p className="text-sm">No regenerated version available yet.</p>
                      <p className="text-xs mt-2">Use the chat to modify this clip.</p>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
          
          {/* Controls */}
          <div className="flex flex-col gap-4 pb-4">
            <div className="border-t pt-4 px-4">
              <div className="flex items-center justify-between">
                {/* Revert button on far left */}
                <div className="flex-shrink-0">
                  {showRevertButton ? (
                    <Button
                      variant="outline"
                      disabled={isReverting}
                      onClick={async () => {
                        if (isReverting || !onRevert) return
                        
                        try {
                          setIsReverting(true)
                          setError(null)
                          
                          // Determine which version to apply based on what's currently in the main video
                          const targetVersion = activeVersion === regeneratedClip!.version_number 
                            ? originalClip.version_number  // Currently on latest (v5), switch to previous (v4)
                            : regeneratedClip!.version_number  // Currently on previous (v4), switch to latest (v5)
                          
                          console.log("🔄 Version Toggle Debug:", {
                            activeVersion,
                            originalClipVersion: originalClip.version_number,
                            regeneratedClipVersion: regeneratedClip!.version_number,
                            targetVersion,
                            clipIndex: clipIndex!
                          })
                          
                          await onRevert(clipIndex!, targetVersion)
                          
                          // Update active version after successful revert
                          setActiveVersion(targetVersion)
                          
                          // Keep loading state for a bit to show the recomposition is happening
                          // The parent component will handle SSE events and update the main video
                          setTimeout(() => {
                            setIsReverting(false)
                          }, 3000)  // Show loading for 3 seconds minimum
                          
                          // Don't close modal - let user see the result and toggle again if needed
                          // onClose() 
                        } catch (error) {
                          console.error("Failed to switch clip version:", error)
                          setError(error instanceof Error ? error.message : "Failed to switch clip version")
                          setIsReverting(false)
                        }
                      }}
                      className={`transition-colors ${
                        isReverting 
                          ? 'bg-orange-100 text-orange-600 border-orange-300 cursor-wait' 
                          : 'bg-orange-50 text-orange-700 border-orange-300 hover:bg-orange-100 hover:border-orange-400'
                      }`}
                    >
                      {isReverting ? (
                        <>
                          <LoadingSpinner className="h-4 w-4 mr-3" />
                          Recomposing Video...
                        </>
                      ) : activeVersion === regeneratedClip!.version_number ? (
                        <>
                          <RotateCcw className="h-4 w-4 mr-3" />
                          Revert to Prior Version
                        </>
                      ) : (
                        <>
                          <RotateCcw className="h-4 w-4 mr-3 rotate-180" />
                          Change clip to latest version
                        </>
                      )}
                    </Button>
                  ) : (
                    <div className="w-[180px]" />
                  )}
                </div>
                
                {/* Playback controls centered */}
                <div className="flex items-center gap-4">
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
                    disabled={!regeneratedClip}
                  >
                    {isSynced ? "Synchronized" : "Independent"}
                  </Button>
                </div>
                
                {/* Right spacer for symmetry */}
                <div className="w-[180px] flex-shrink-0" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

