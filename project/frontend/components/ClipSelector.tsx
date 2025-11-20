"use client"

import { useState, useEffect, useRef } from "react"
import Image from "next/image"
import { getJobClips } from "@/lib/api"
import { ClipData } from "@/types/api"
import { Card, CardContent } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { Button } from "@/components/ui/button"
import { formatDuration } from "@/lib/utils"
import { cn } from "@/lib/utils"
import { StyleTransferDialog } from "@/components/StyleTransferDialog"
import { MultiClipInstructionInput } from "@/components/MultiClipInstructionInput"
import { LayoutGrid, Rows } from "lucide-react"

interface ClipSelectorProps {
  jobId: string
  onClipSelect: (clipIndex: number, timestampStart?: number) => void
  selectedClipIndex?: number
  totalClips?: number
}

/**
 * Format timestamp in seconds to "M:SS" format.
 */
function formatTimestamp(seconds: number): string {
  const roundedSeconds = Math.round(seconds)
  const mins = Math.floor(roundedSeconds / 60)
  const secs = roundedSeconds % 60
  return `${mins}:${secs.toString().padStart(2, "0")}`
}

/**
 * Truncate lyrics to first 2-3 lines.
 */
function truncateLyrics(lyrics: string | null, maxLength: number = 100): string | null {
  if (!lyrics) return null
  
  if (lyrics.length <= maxLength) {
    return lyrics
  }
  
  // Find last space before maxLength to avoid cutting words
  const truncatePos = lyrics.lastIndexOf(" ", maxLength)
  if (truncatePos > 0) {
    return lyrics.substring(0, truncatePos) + "..."
  }
  
  return lyrics.substring(0, maxLength - 3) + "..."
}

export function ClipSelector({
  jobId,
  onClipSelect,
  selectedClipIndex,
  totalClips,
}: ClipSelectorProps) {
  const [clips, setClips] = useState<ClipData[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [styleTransferSource, setStyleTransferSource] = useState<number | null>(null)
  const [showStyleTransfer, setShowStyleTransfer] = useState(false)
  const [showMultiClip, setShowMultiClip] = useState(false)
  const [failedThumbnails, setFailedThumbnails] = useState<Set<number>>(new Set())
  const [isGridView, setIsGridView] = useState(false)
  const toggleButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    let mounted = true

    async function fetchClips() {
      try {
        setLoading(true)
        setError(null)
        
        const response = await getJobClips(jobId)
        
        if (!mounted) return
        
        setClips(response.clips)
        setLoading(false)
      } catch (err) {
        if (!mounted) return
        
        const errorMessage = err instanceof Error ? err.message : "Failed to load clips"
        setError(errorMessage)
        setLoading(false)
      }
    }

    fetchClips()

    return () => {
      mounted = false
    }
  }, [jobId])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <LoadingSpinner />
        <p className="mt-4 text-sm text-muted-foreground">Loading clips...</p>
      </div>
    )
  }

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>
          <div className="flex items-center justify-between">
            <span>Failed to load clips: {error}</span>
            <button
              onClick={() => window.location.reload()}
              className="ml-4 text-sm underline hover:no-underline"
            >
              Retry
            </button>
          </div>
        </AlertDescription>
      </Alert>
    )
  }

  if (clips.length === 0) {
    return (
      <Alert>
        <AlertDescription>
          No clips available for this job. The video may not have completed generation yet.
        </AlertDescription>
      </Alert>
    )
  }

  const handleClipClick = (clipIndex: number, timestampStart: number, e: React.MouseEvent) => {
    // Check for Ctrl/Cmd click for style transfer
    if (e.ctrlKey || e.metaKey) {
      if (styleTransferSource === null) {
        setStyleTransferSource(clipIndex)
        setShowStyleTransfer(false)
      } else if (styleTransferSource !== clipIndex) {
        setShowStyleTransfer(true)
      }
    } else {
      onClipSelect(clipIndex, timestampStart)
      setStyleTransferSource(null)
      setShowStyleTransfer(false)
    }
  }

  const handleToggleView = () => {
    if (!toggleButtonRef.current) {
      setIsGridView(!isGridView)
      return
    }

    // Get button position before layout change (relative to viewport)
    const buttonRect = toggleButtonRef.current.getBoundingClientRect()
    const buttonViewportTop = buttonRect.top

    // Toggle the view
    setIsGridView(!isGridView)

    // Use requestAnimationFrame to wait for DOM update, then scroll
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (toggleButtonRef.current) {
          const newButtonRect = toggleButtonRef.current.getBoundingClientRect()
          const newButtonViewportTop = newButtonRect.top
          const difference = newButtonViewportTop - buttonViewportTop
          
          // Scroll to compensate for the difference to keep button in same viewport position
          if (Math.abs(difference) > 1) {
            window.scrollBy({
              top: -difference,
              behavior: 'auto'
            })
          }
        }
      })
    })
  }

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Select a Clip to Edit</h2>
        <div className="flex gap-2">
          <Button
            ref={toggleButtonRef}
            variant="outline"
            size="sm"
            onClick={handleToggleView}
            title={isGridView ? "Switch to row view" : "Switch to grid view"}
          >
            {isGridView ? (
              <>
                <Rows className="h-4 w-4 mr-1" />
                Row
              </>
            ) : (
              <>
                <LayoutGrid className="h-4 w-4 mr-1" />
                Grid
              </>
            )}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowMultiClip(!showMultiClip)}
          >
            {showMultiClip ? "Hide" : "Multi-Clip"} Mode
          </Button>
        </div>
      </div>

      {showMultiClip && (
        <MultiClipInstructionInput
          jobId={jobId}
          totalClips={clips.length}
          onCancel={() => setShowMultiClip(false)}
        />
      )}

      {showStyleTransfer && styleTransferSource !== null && selectedClipIndex !== undefined && (
        <StyleTransferDialog
          jobId={jobId}
          sourceClipIndex={styleTransferSource}
          targetClipIndex={selectedClipIndex}
          totalClips={clips.length}
          onTransferComplete={() => {
            setShowStyleTransfer(false)
            setStyleTransferSource(null)
            // Refresh clips
            window.location.reload()
          }}
          onCancel={() => {
            setShowStyleTransfer(false)
            setStyleTransferSource(null)
          }}
        />
      )}

      {styleTransferSource !== null && !showStyleTransfer && (
        <Alert>
          <AlertDescription>
            Source clip selected: {styleTransferSource + 1}. Ctrl/Cmd+Click another clip to transfer style, or click normally to select.
          </AlertDescription>
        </Alert>
      )}
      
      {isGridView ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {clips.map((clip) => {
            const isSelected = selectedClipIndex === clip.clip_index
            const timestampRange = `${formatTimestamp(clip.timestamp_start)} - ${formatTimestamp(clip.timestamp_end)}`
            const lyricsPreview = truncateLyrics(clip.lyrics_preview)

            return (
              <Card
                key={clip.clip_index}
                className={cn(
                  "cursor-pointer transition-all hover:shadow-md",
                  isSelected
                    ? "ring-2 ring-primary ring-offset-2"
                    : "hover:border-primary/50"
                )}
                onClick={(e) => handleClipClick(clip.clip_index, clip.timestamp_start, e)}
              >
                <CardContent className="p-0">
                  {/* Thumbnail */}
                  <div className="relative aspect-video w-full overflow-hidden rounded-t-lg bg-muted">
                    {clip.thumbnail_url && !failedThumbnails.has(clip.clip_index) ? (
                      <Image
                        src={clip.thumbnail_url}
                        alt={`Clip ${clip.clip_index + 1} thumbnail`}
                        fill
                        className="object-cover"
                        loading="lazy"
                        sizes="(max-width: 768px) 50vw, (max-width: 1024px) 33vw, 25vw"
                        onError={() => {
                          console.warn(`Failed to load thumbnail for clip ${clip.clip_index + 1}`)
                          setFailedThumbnails(prev => new Set(prev).add(clip.clip_index))
                        }}
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center bg-muted">
                        <div className="text-center">
                          <svg
                            className="mx-auto h-12 w-12 text-muted-foreground"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                            />
                          </svg>
                          <p className="mt-2 text-xs text-muted-foreground">
                            Thumbnail unavailable
                          </p>
                        </div>
                      </div>
                    )}
                    
                    {/* Clip index badge */}
                    <div className="absolute left-2 top-2 rounded bg-black/70 px-2 py-1 text-xs font-semibold text-white">
                      Clip {clip.clip_index + 1}
                    </div>
                    
                    {/* Duration overlay */}
                    <div className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-1 text-xs text-white">
                      {formatDuration(clip.duration)}
                    </div>
                    
                    {/* Regenerated badge */}
                    {clip.is_regenerated && (
                      <div className="absolute left-2 bottom-2 rounded bg-primary/90 px-2 py-1 text-xs font-semibold text-white">
                        Regenerated
                      </div>
                    )}
                  </div>
                  
                  {/* Clip metadata */}
                  <div className="p-3">
                    {/* Timestamp range */}
                    <p className="text-xs font-medium text-muted-foreground">
                      {timestampRange}
                    </p>
                    
                    {/* Lyrics preview */}
                    {lyricsPreview ? (
                      <p className="mt-2 line-clamp-2 text-sm text-foreground">
                        {lyricsPreview}
                      </p>
                    ) : (
                      <p className="mt-2 text-xs text-muted-foreground italic">
                        No lyrics available
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      ) : (
        <div className="flex gap-4 overflow-x-auto overflow-y-hidden pb-2 scrollbar-thin scrollbar-thumb-muted scrollbar-track-transparent">
          {clips.map((clip) => {
            const isSelected = selectedClipIndex === clip.clip_index
            const timestampRange = `${formatTimestamp(clip.timestamp_start)} - ${formatTimestamp(clip.timestamp_end)}`
            const lyricsPreview = truncateLyrics(clip.lyrics_preview)

            return (
              <Card
                key={clip.clip_index}
                className={cn(
                  "cursor-pointer transition-all hover:shadow-md flex-shrink-0",
                  "w-64",
                  isSelected
                    ? "ring-2 ring-primary ring-offset-2"
                    : "hover:border-primary/50"
                )}
                onClick={(e) => handleClipClick(clip.clip_index, clip.timestamp_start, e)}
              >
                <CardContent className="p-0">
                  {/* Thumbnail */}
                  <div className="relative aspect-video w-full overflow-hidden rounded-t-lg bg-muted">
                    {clip.thumbnail_url && !failedThumbnails.has(clip.clip_index) ? (
                      <Image
                        src={clip.thumbnail_url}
                        alt={`Clip ${clip.clip_index + 1} thumbnail`}
                        fill
                        className="object-cover"
                        loading="lazy"
                        sizes="256px"
                        onError={() => {
                          console.warn(`Failed to load thumbnail for clip ${clip.clip_index + 1}`)
                          setFailedThumbnails(prev => new Set(prev).add(clip.clip_index))
                        }}
                      />
                    ) : (
                      <div className="flex h-full items-center justify-center bg-muted">
                        <div className="text-center">
                          <svg
                            className="mx-auto h-12 w-12 text-muted-foreground"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
                            />
                          </svg>
                          <p className="mt-2 text-xs text-muted-foreground">
                            Thumbnail unavailable
                          </p>
                        </div>
                      </div>
                    )}
                    
                    {/* Clip index badge */}
                    <div className="absolute left-2 top-2 rounded bg-black/70 px-2 py-1 text-xs font-semibold text-white">
                      Clip {clip.clip_index + 1}
                    </div>
                    
                    {/* Duration overlay */}
                    <div className="absolute bottom-2 right-2 rounded bg-black/70 px-2 py-1 text-xs text-white">
                      {formatDuration(clip.duration)}
                    </div>
                    
                    {/* Regenerated badge */}
                    {clip.is_regenerated && (
                      <div className="absolute left-2 bottom-2 rounded bg-primary/90 px-2 py-1 text-xs font-semibold text-white">
                        Regenerated
                      </div>
                    )}
                  </div>
                  
                  {/* Clip metadata */}
                  <div className="p-3">
                    {/* Timestamp range */}
                    <p className="text-xs font-medium text-muted-foreground whitespace-nowrap">
                      {timestampRange}
                    </p>
                    
                    {/* Lyrics preview */}
                    {lyricsPreview ? (
                      <p className="mt-2 line-clamp-2 text-sm text-foreground">
                        {lyricsPreview}
                      </p>
                    ) : (
                      <p className="mt-2 text-xs text-muted-foreground italic">
                        No lyrics available
                      </p>
                    )}
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}

