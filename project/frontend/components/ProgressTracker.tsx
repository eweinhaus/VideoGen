"use client"

import { useState, useEffect, useMemo } from "react"
import Image from "next/image"
import { useSSE } from "@/hooks/useSSE"
import { jobStore } from "@/stores/jobStore"
import { Progress } from "@/components/ui/progress"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { CollapsibleCard } from "@/components/ui/collapsible-card"
import { StageIndicator } from "@/components/StageIndicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import type {
  StageUpdateEvent,
  ProgressEvent,
  MessageEvent,
  CostUpdateEvent,
  CompletedEvent,
  ErrorEvent,
  AudioParserResultsEvent,
  ScenePlannerResultsEvent,
  PromptGeneratorResultsEvent,
  ReferenceGenerationStartEvent,
  ReferenceGenerationCompleteEvent,
  ReferenceGenerationFailedEvent,
  ReferenceGenerationRetryEvent,
} from "@/types/sse"
import { formatDuration } from "@/lib/utils"

type ReferenceImageStatus = "pending" | "completed" | "failed" | "retrying"

interface ReferenceImageEntry {
  key: string
  imageId: string
  imageType: string
  status: ReferenceImageStatus
  imageUrl?: string
  cost?: number
  generationTime?: number
  retryCount?: number
  reason?: string
}

interface ReferenceGenerationState {
  totalImages: number
  completedImages: number
  images: Record<string, ReferenceImageEntry>
}

const initialReferenceState: ReferenceGenerationState = {
  totalImages: 0,
  completedImages: 0,
  images: {},
}

const referenceStatusClasses: Record<ReferenceImageStatus, string> = {
  completed: "bg-emerald-100 text-emerald-800",
  pending: "bg-slate-100 text-slate-600",
  failed: "bg-rose-100 text-rose-800",
  retrying: "bg-amber-100 text-amber-800",
}

const referenceStatusLabels: Record<ReferenceImageStatus, string> = {
  completed: "Ready",
  pending: "Generating",
  failed: "Failed",
  retrying: "Retrying",
}

interface ProgressTrackerProps {
  jobId: string
  onComplete?: (videoUrl: string) => void
  onError?: (error: string) => void
}

export function ProgressTracker({
  jobId,
  onComplete,
  onError,
}: ProgressTrackerProps) {
  const { currentJob: storeJob } = jobStore()
  const currentJob = storeJob?.id === jobId ? storeJob : null
  
  // Memoize initial values to prevent flicker on first render
  const initialValues = useMemo(() => {
    if (!currentJob) {
      return {
        progress: 0,
        currentStage: null,
        estimatedRemaining: null,
        cost: null,
        stages: [] as Array<{ name: string; status: "pending" | "processing" | "completed" | "failed" }>,
      }
    }
    
    const stages = currentJob.stages
      ? Object.entries(currentJob.stages).map(([name, stageData]) => ({
          name,
          status: (stageData.status || "pending") as "pending" | "processing" | "completed" | "failed",
        }))
      : []
    
    return {
      progress: currentJob.progress ?? 0,
      currentStage: currentJob.currentStage ?? null,
      estimatedRemaining: currentJob.estimatedRemaining ?? null,
      cost: currentJob.totalCost ?? null,
      stages,
    }
  }, [currentJob])
  
  // Use state for values that can be updated by SSE, but prefer memoized values for initial render
  const [progress, setProgress] = useState(initialValues.progress)
  const [currentStage, setCurrentStage] = useState<string | null>(initialValues.currentStage)
  const [estimatedRemaining, setEstimatedRemaining] = useState<number | null>(initialValues.estimatedRemaining)
  const [cost, setCost] = useState<number | null>(initialValues.cost)
  const [stages, setStages] = useState<
    Array<{ name: string; status: "pending" | "processing" | "completed" | "failed" }>
  >(initialValues.stages)
  
  // Use memoized values directly in render to prevent flicker, but allow state updates from SSE
  // This ensures we show correct values immediately when job data is available
  const displayProgress = currentJob?.progress !== undefined ? currentJob.progress : progress
  const displayStage = currentJob?.currentStage !== undefined ? currentJob.currentStage : currentStage
  const displayEstimatedRemaining = currentJob?.estimatedRemaining !== undefined ? currentJob.estimatedRemaining : estimatedRemaining
  const displayCost = currentJob?.totalCost !== undefined ? currentJob.totalCost : cost
  const displayStages = currentJob?.stages 
    ? Object.entries(currentJob.stages).map(([name, stageData]) => ({
        name,
        status: (stageData.status || "pending") as "pending" | "processing" | "completed" | "failed",
      }))
    : stages
  const [audioResults, setAudioResults] = useState<AudioParserResultsEvent | null>(null)
  const [scenePlanResults, setScenePlanResults] = useState<ScenePlannerResultsEvent | null>(null)
  const [promptResults, setPromptResults] = useState<PromptGeneratorResultsEvent | null>(null)
  const [referenceState, setReferenceState] = useState<ReferenceGenerationState>(initialReferenceState)

  const { updateJob } = jobStore()
  // Removed truncatePrompt - show full prompt text as requested
  
  // Sync state when job data updates (for SSE updates to work correctly)
  useEffect(() => {
    if (currentJob) {
      // Update state to match job data (SSE will override these)
      if (currentJob.progress !== undefined) {
        setProgress((prev) => currentJob.progress !== prev ? currentJob.progress : prev)
      }
      if (currentJob.currentStage !== undefined) {
        setCurrentStage((prev) => currentJob.currentStage !== prev ? currentJob.currentStage : prev)
      }
      if (currentJob.estimatedRemaining !== undefined) {
        setEstimatedRemaining((prev) => currentJob.estimatedRemaining !== prev ? (currentJob.estimatedRemaining ?? null) : prev)
      }
      if (currentJob.totalCost !== undefined) {
        setCost((prev) => currentJob.totalCost !== prev ? (currentJob.totalCost ?? null) : prev)
      }
      
      if (currentJob.stages) {
        const jobStages = Object.entries(currentJob.stages).map(([name, stageData]) => ({
          name,
          status: (stageData.status || "pending") as "pending" | "processing" | "completed" | "failed",
        }))
        setStages((prev) => {
          const stagesChanged = JSON.stringify(jobStages) !== JSON.stringify(prev)
          return stagesChanged ? jobStages : prev
        })
      }
    }
  }, [currentJob]) // Only depend on currentJob to avoid infinite loops

  useEffect(() => {
    setReferenceState(initialReferenceState)
  }, [jobId])

  const referenceKey = (imageType: string, imageId: string) => `${imageType}:${imageId}`

  const handleReferenceStart = (data: ReferenceGenerationStartEvent) => {
    const key = referenceKey(data.image_type, data.image_id)
    setReferenceState((prev) => {
      const existing = prev.images[key]
      const updatedEntry: ReferenceImageEntry = {
        key,
        imageId: data.image_id,
        imageType: data.image_type,
        status: existing?.status === "completed" ? "completed" : "pending",
        imageUrl: existing?.imageUrl,
        cost: existing?.cost,
        generationTime: existing?.generationTime,
        retryCount: existing?.retryCount,
      }

      const totalImagesCandidate = data.total_images ?? prev.totalImages ?? Object.keys({ ...prev.images, [key]: updatedEntry }).length
      const totalImages = Math.max(totalImagesCandidate, prev.totalImages)

      return {
        totalImages,
        completedImages: prev.completedImages,
        images: {
          ...prev.images,
          [key]: updatedEntry,
        },
      }
    })
  }

  const handleReferenceComplete = (data: ReferenceGenerationCompleteEvent) => {
    const key = referenceKey(data.image_type, data.image_id)
    setReferenceState((prev) => {
      const previousEntry = prev.images[key]
      const completedCandidate =
        data.completed_images ??
        (previousEntry?.status === "completed" ? prev.completedImages : prev.completedImages + 1)
      const completedImages = Math.max(completedCandidate, prev.completedImages)
      const totalImagesCandidate = data.total_images ?? prev.totalImages ?? Object.keys(prev.images).length

      return {
        totalImages: Math.max(totalImagesCandidate, prev.totalImages),
        completedImages,
        images: {
          ...prev.images,
          [key]: {
            key,
            imageId: data.image_id,
            imageType: data.image_type,
            status: "completed",
            imageUrl: data.image_url,
            generationTime: data.generation_time,
            cost: data.cost,
            retryCount: data.retry_count,
          },
        },
      }
    })
  }

  const handleReferenceFailed = (data: ReferenceGenerationFailedEvent) => {
    const key = referenceKey(data.image_type, data.image_id)
    setReferenceState((prev) => ({
      ...prev,
      images: {
        ...prev.images,
        [key]: {
          key,
          imageId: data.image_id,
          imageType: data.image_type,
          status: "failed",
          imageUrl: prev.images[key]?.imageUrl,
          generationTime: prev.images[key]?.generationTime,
          cost: prev.images[key]?.cost,
          retryCount: data.retry_count ?? prev.images[key]?.retryCount,
          reason: data.reason || "Generation failed",
        },
      },
    }))
  }

  const handleReferenceRetry = (data: ReferenceGenerationRetryEvent) => {
    const key = referenceKey(data.image_type, data.image_id)
    setReferenceState((prev) => {
      const existing = prev.images[key]
      return {
        ...prev,
        images: {
          ...prev.images,
          [key]: {
            key,
            imageId: data.image_id,
            imageType: data.image_type,
            status: "retrying",
            imageUrl: existing?.imageUrl,
            generationTime: existing?.generationTime,
            cost: existing?.cost,
            retryCount: data.retry_count,
            reason: data.reason,
          },
        },
      }
    })
  }

  const referenceImages = useMemo(() => {
    return Object.values(referenceState.images).sort((a, b) => {
      if (a.imageType === b.imageType) {
        return a.imageId.localeCompare(b.imageId)
      }
      return a.imageType.localeCompare(b.imageType)
    })
  }, [referenceState.images])

  const referenceProgressValue =
    referenceState.totalImages > 0 ? (referenceState.completedImages / referenceState.totalImages) * 100 : 0

  const { isConnected, error: sseError } = useSSE(jobId, {
    onStageUpdate: (data: StageUpdateEvent) => {
      setCurrentStage(data.stage)
      updateJob(jobId, { currentStage: data.stage })
      
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
    onProgress: (data: ProgressEvent) => {
      setProgress(data.progress)
      updateJob(jobId, { progress: data.progress })
      if (data.estimated_remaining) {
        setEstimatedRemaining(data.estimated_remaining)
      }
    },
    onCostUpdate: (data: CostUpdateEvent) => {
      setCost(data.total)
      updateJob(jobId, { totalCost: data.total })
    },
    onCompleted: (data: CompletedEvent) => {
      updateJob(jobId, {
        status: "completed",
        videoUrl: data.video_url,
        progress: 100,
      })
      onComplete?.(data.video_url)
    },
    onError: (data: ErrorEvent) => {
      updateJob(jobId, {
        status: "failed",
        errorMessage: data.error,
      })
      onError?.(data.error)
    },
    onAudioParserResults: (data: AudioParserResultsEvent) => {
      setAudioResults(data)
    },
    onScenePlannerResults: (data: ScenePlannerResultsEvent) => {
      setScenePlanResults(data)
    },
    onPromptGeneratorResults: (data: PromptGeneratorResultsEvent) => {
      setPromptResults(data)
    },
    onReferenceGenerationStart: handleReferenceStart,
    onReferenceGenerationComplete: handleReferenceComplete,
    onReferenceGenerationFailed: handleReferenceFailed,
    onReferenceGenerationRetry: handleReferenceRetry,
  })

  return (
    <div className="w-full space-y-4">
      <div className="space-y-3 p-4 bg-muted/30 rounded-lg border min-h-[120px] flex flex-col justify-center">
        <div className="flex items-center justify-between mb-2">
          <span className="text-base font-semibold">Progress</span>
          <span className="text-base font-semibold text-muted-foreground">{displayProgress}%</span>
        </div>
        <Progress value={displayProgress} className="h-3" />
      </div>

      {displayEstimatedRemaining !== null && (
        <p className="text-sm text-muted-foreground">
          Estimated time remaining: {formatDuration(displayEstimatedRemaining)}
        </p>
      )}

      {displayCost !== null && (
        <p className="text-sm text-muted-foreground">
          Total cost: ${displayCost.toFixed(2)}
        </p>
      )}

      <StageIndicator 
        stages={displayStages} 
        currentStage={displayStage}
      />

      {sseError && (
        <Alert variant="destructive">
          <AlertDescription>{sseError}</AlertDescription>
        </Alert>
      )}

      {!isConnected && !sseError && (
        <Alert>
          <AlertDescription>Connecting to server...</AlertDescription>
        </Alert>
      )}

      {audioResults && (
        <CollapsibleCard title="Audio Analysis Results" defaultOpen={true}>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm font-medium text-muted-foreground">BPM</p>
                  <p className="text-2xl font-bold">{audioResults.bpm.toFixed(1)}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Duration</p>
                  <p className="text-2xl font-bold">{formatDuration(audioResults.duration)}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Beats Detected</p>
                  <p className="text-2xl font-bold">{audioResults.beat_count}</p>
                </div>
                <div>
                  <p className="text-sm font-medium text-muted-foreground">Structure Segments</p>
                  <p className="text-2xl font-bold">{audioResults.song_structure.length}</p>
                </div>
              </div>
              
              <div>
                <p className="text-sm font-medium text-muted-foreground mb-2">Mood</p>
                <div className="flex items-center gap-2">
                  <span className="font-semibold capitalize">{audioResults.mood.primary}</span>
                  {audioResults.mood.energy_level && (
                    <span className="text-sm text-muted-foreground">
                      ({audioResults.mood.energy_level} energy)
                    </span>
                  )}
                  {audioResults.mood.confidence && (
                    <span className="text-xs text-muted-foreground">
                      {Math.round(audioResults.mood.confidence * 100)}% confidence
                    </span>
                  )}
                </div>
              </div>

              <div>
                <p className="text-sm font-medium text-muted-foreground mb-2">Song Structure</p>
                <div className="space-y-1">
                  {audioResults.song_structure.map((seg, idx) => (
                    <div key={idx} className="flex items-center justify-between text-sm">
                      <span className="capitalize font-medium">{seg.type}</span>
                      <span className="text-muted-foreground">
                        {seg.start.toFixed(1)}s - {seg.end.toFixed(1)}s
                      </span>
                      <span className={`px-2 py-1 rounded text-xs ${
                        seg.energy === "high" ? "bg-red-100 text-red-800" :
                        seg.energy === "medium" ? "bg-yellow-100 text-yellow-800" :
                        "bg-blue-100 text-blue-800"
                      }`}>
                        {seg.energy} energy
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {audioResults.beat_timestamps.length > 0 && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-2">
                    First {Math.min(20, audioResults.beat_timestamps.length)} Beats (seconds)
                  </p>
                  <p className="text-xs font-mono text-muted-foreground">
                    {audioResults.beat_timestamps.map(t => t.toFixed(2)).join(", ")}
                  </p>
                </div>
              )}

              {audioResults.clip_boundaries && audioResults.clip_boundaries.length > 0 && (
                <div>
                  <p className="text-sm font-medium text-muted-foreground mb-2">
                    Clip Boundaries ({audioResults.clip_boundaries.length} clips)
                  </p>
                  <div className="space-y-1 max-h-60 overflow-y-auto">
                    {audioResults.clip_boundaries.map((boundary, idx) => (
                      <div key={idx} className="flex items-center justify-between text-sm p-2 bg-muted/30 rounded">
                        <span className="font-medium">Clip {idx + 1}</span>
                        <span className="text-muted-foreground">
                          {boundary.start.toFixed(1)}s - {boundary.end.toFixed(1)}s
                        </span>
                        <span className="text-xs text-muted-foreground">
                          ({boundary.duration.toFixed(1)}s)
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {audioResults.metadata && (
                <div className="mt-4 pt-4 border-t">
                  <p className="text-sm font-medium text-muted-foreground mb-2">Analysis Metadata</p>
                  <div className="space-y-2 text-xs">
                    {audioResults.metadata.cache_hit && (
                      <p className="text-green-600">✓ Results from cache</p>
                    )}
                    {audioResults.metadata.fallback_used && audioResults.metadata.fallback_used.length > 0 && (
                      <div>
                        <p className="text-amber-600 font-medium">⚠ Fallbacks used:</p>
                        <ul className="list-disc list-inside ml-2 text-amber-600">
                          {audioResults.metadata.fallback_used.map((fallback, idx) => (
                            <li key={idx}>{fallback}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {audioResults.metadata.beat_detection_confidence !== undefined && (
                      <p className="text-muted-foreground">
                        Beat detection confidence: {Math.round(audioResults.metadata.beat_detection_confidence * 100)}%
                      </p>
                    )}
                    {audioResults.metadata.structure_confidence !== undefined && (
                      <p className="text-muted-foreground">
                        Structure confidence: {Math.round(audioResults.metadata.structure_confidence * 100)}%
                      </p>
                    )}
                    {audioResults.metadata.processing_time !== undefined && (
                      <p className="text-muted-foreground">
                        Processing time: {audioResults.metadata.processing_time.toFixed(2)}s
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
        </CollapsibleCard>
      )}

      {referenceImages.length > 0 && (
        <CollapsibleCard 
          title="Reference Images" 
          defaultOpen={true}
        >
          <div className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground mb-2">
                {referenceState.completedImages}/{referenceState.totalImages || referenceImages.length} images ready
              </p>
              <Progress value={referenceProgressValue} className="h-2" />
            </div>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {referenceImages.map((entry) => (
                <div key={entry.key} className="space-y-2 rounded-lg border p-3">
                  <div className="flex items-center justify-between text-sm">
                    <div className="font-semibold capitalize">
                      {entry.imageType} · {entry.imageId}
                    </div>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${referenceStatusClasses[entry.status]}`}>
                      {referenceStatusLabels[entry.status]}
                    </span>
                  </div>
                  {entry.imageUrl ? (
                    <div className="relative h-40 w-full overflow-hidden rounded-md border bg-muted/30">
                      <Image
                        src={entry.imageUrl}
                        alt={`${entry.imageType} ${entry.imageId}`}
                        fill
                        className="object-cover"
                        loading="lazy"
                        unoptimized
                      />
                    </div>
                  ) : (
                    <div className="flex h-40 items-center justify-center rounded-md border border-dashed bg-muted/30 text-xs text-muted-foreground">
                      {entry.status === "failed" ? "Image unavailable" : "Waiting for image"}
                    </div>
                  )}
                  <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                    {typeof entry.generationTime === "number" && (
                      <span>{entry.generationTime.toFixed(1)}s</span>
                    )}
                    {typeof entry.cost === "number" && <span>${entry.cost.toFixed(3)}</span>}
                    {entry.retryCount ? <span>Retries: {entry.retryCount}</span> : null}
                  </div>
                  {entry.reason && (
                    <p className="text-xs text-muted-foreground">
                      {entry.reason}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        </CollapsibleCard>
      )}

      {scenePlanResults && (
        <CollapsibleCard title="Scene Plan" defaultOpen={false}>
            <div className="space-y-4">
              <div className="prose prose-sm max-w-none dark:prose-invert">
                <h3 className="text-lg font-semibold">Video Summary</h3>
                <p className="text-muted-foreground">{scenePlanResults.video_summary}</p>
                
                <h3 className="text-lg font-semibold mt-4">Characters</h3>
                <ul className="list-disc list-inside space-y-1">
                  {scenePlanResults.characters.map((char) => (
                    <li key={char.id}>
                      <strong>{char.id}</strong> ({char.role}): {char.description}
                    </li>
                  ))}
                </ul>
                
                <h3 className="text-lg font-semibold mt-4">Scenes</h3>
                <ul className="list-disc list-inside space-y-1">
                  {scenePlanResults.scenes.map((scene) => (
                    <li key={scene.id}>
                      <strong>{scene.id}</strong> ({scene.time_of_day}): {scene.description}
                    </li>
                  ))}
                </ul>
                
                <h3 className="text-lg font-semibold mt-4">Style</h3>
                <div className="space-y-2">
                  <p><strong>Visual Style:</strong> {scenePlanResults.style.visual_style}</p>
                  <p><strong>Mood:</strong> {scenePlanResults.style.mood}</p>
                  <p><strong>Lighting:</strong> {scenePlanResults.style.lighting}</p>
                  <p><strong>Cinematography:</strong> {scenePlanResults.style.cinematography}</p>
                  <div>
                    <strong>Color Palette:</strong>
                    <div className="flex gap-2 mt-1">
                      {scenePlanResults.style.color_palette.map((color, idx) => (
                        <div
                          key={idx}
                          className="w-8 h-8 rounded border border-gray-300"
                          style={{ backgroundColor: color }}
                          title={color}
                        />
                      ))}
                    </div>
                  </div>
                </div>
                
                <h3 className="text-lg font-semibold mt-4">Clip Scripts</h3>
                <div className="space-y-3">
                  {scenePlanResults.clip_scripts.map((clip) => (
                    <div key={clip.clip_index} className="border-l-4 border-primary pl-4 py-2">
                      <div className="flex items-center justify-between mb-1">
                        <strong>Clip {clip.clip_index}</strong>
                        <span className="text-sm text-muted-foreground">
                          {clip.start.toFixed(1)}s - {clip.end.toFixed(1)}s
                        </span>
                      </div>
                      <p className="text-sm">{clip.visual_description}</p>
                      <div className="text-xs text-muted-foreground mt-1 space-y-0.5">
                        <p><strong>Motion:</strong> {clip.motion}</p>
                        <p><strong>Camera:</strong> {clip.camera_angle}</p>
                        <p><strong>Beat Intensity:</strong> {clip.beat_intensity}</p>
                        {clip.lyrics_context && (
                          <p><strong>Lyrics:</strong> {clip.lyrics_context}</p>
                        )}
                        <p><strong>Characters:</strong> {clip.characters.join(", ")}</p>
                        <p><strong>Scenes:</strong> {clip.scenes.join(", ")}</p>
                      </div>
                    </div>
                  ))}
                </div>
                
                <h3 className="text-lg font-semibold mt-4">Transitions</h3>
                <div className="space-y-2">
                  {scenePlanResults.transitions.map((trans, idx) => (
                    <div key={idx} className="text-sm">
                      <strong>Clip {trans.from_clip} → Clip {trans.to_clip}:</strong> {trans.type}
                      {trans.duration > 0 && ` (${trans.duration.toFixed(2)}s)`}
                      {trans.rationale && (
                        <span className="text-muted-foreground"> - {trans.rationale}</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
        </CollapsibleCard>
      )}

      {promptResults && (
        <CollapsibleCard title="Clip Prompts" defaultOpen={false}>
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {promptResults.llm_used
                ? `Optimized by ${promptResults.llm_model ?? "LLM"}`
                : "Generated via deterministic template"}
            </p>
            <div className="space-y-3">
              {promptResults.clip_prompts.map((clip) => (
                <div key={clip.clip_index} className="border-l-4 border-primary/70 pl-4 py-2 space-y-1">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-semibold">Clip {clip.clip_index}</span>
                    <span className="text-muted-foreground">{clip.duration.toFixed(1)}s</span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap break-words">{clip.prompt}</p>
                  <div className="text-xs text-muted-foreground flex flex-wrap gap-3">
                    {clip.metadata?.style_keywords?.length ? (
                      <span>Style: {clip.metadata.style_keywords.slice(0, 3).join(", ")}</span>
                    ) : null}
                    {clip.metadata?.word_count ? (
                      <span>Words: {clip.metadata.word_count}</span>
                    ) : null}
                    {clip.metadata?.reference_mode ? (
                      <span>References: {clip.metadata.reference_mode}</span>
                    ) : null}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </CollapsibleCard>
      )}
    </div>
  )
}

