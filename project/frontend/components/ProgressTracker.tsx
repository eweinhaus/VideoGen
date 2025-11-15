"use client"

import { useState, useEffect } from "react"
import { useSSE } from "@/hooks/useSSE"
import { jobStore } from "@/stores/jobStore"
import { Progress } from "@/components/ui/progress"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { StageIndicator } from "@/components/StageIndicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import type { StageUpdateEvent, ProgressEvent, MessageEvent, CostUpdateEvent, CompletedEvent, ErrorEvent, AudioParserResultsEvent, ScenePlannerResultsEvent } from "@/types/sse"
import { formatDuration } from "@/lib/utils"

interface ProgressTrackerProps {
  jobId: string
  onComplete?: (videoUrl: string) => void
  onError?: (error: string) => void
}

interface StatusMessage {
  text: string
  stage?: string
  timestamp: Date
}

export function ProgressTracker({
  jobId,
  onComplete,
  onError,
}: ProgressTrackerProps) {
  const { currentJob: storeJob } = jobStore()
  const currentJob = storeJob?.id === jobId ? storeJob : null
  const [progress, setProgress] = useState(currentJob?.progress || 0)
  const [currentStage, setCurrentStage] = useState<string | null>(currentJob?.currentStage || null)
  const [messages, setMessages] = useState<StatusMessage[]>([])
  const [estimatedRemaining, setEstimatedRemaining] = useState<number | null>(
    currentJob?.estimatedRemaining || null
  )
  const [cost, setCost] = useState<number | null>(currentJob?.totalCost || null)
  const [stages, setStages] = useState<
    Array<{ name: string; status: "pending" | "processing" | "completed" | "failed" }>
  >([])
  const [audioResults, setAudioResults] = useState<AudioParserResultsEvent | null>(null)
  const [scenePlanResults, setScenePlanResults] = useState<ScenePlannerResultsEvent | null>(null)

  const { updateJob } = jobStore()
  
  // Initialize progress from job state if available
  useEffect(() => {
    if (currentJob) {
      if (currentJob.progress !== undefined) setProgress(currentJob.progress)
      if (currentJob.currentStage) setCurrentStage(currentJob.currentStage)
      if (currentJob.estimatedRemaining) setEstimatedRemaining(currentJob.estimatedRemaining)
      if (currentJob.totalCost) setCost(currentJob.totalCost)
    }
  }, [currentJob])

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
    onMessage: (data: MessageEvent) => {
      setMessages((prev) => [
        { text: data.text, stage: data.stage, timestamp: new Date() },
        ...prev.slice(0, 4), // Keep last 5 messages
      ])
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
  })

  return (
    <div className="w-full space-y-4">
      <div className="space-y-3 p-4 bg-muted/30 rounded-lg border min-h-[120px] flex flex-col justify-center">
        <div className="flex items-center justify-between mb-2">
          <span className="text-base font-semibold">Progress</span>
          <span className="text-base font-semibold text-muted-foreground">{progress}%</span>
        </div>
        <Progress value={progress} className="h-3" />
      </div>

      {estimatedRemaining !== null && (
        <p className="text-sm text-muted-foreground">
          Estimated time remaining: {formatDuration(estimatedRemaining)}
        </p>
      )}

      {cost !== null && (
        <p className="text-sm text-muted-foreground">
          Total cost: ${cost.toFixed(2)}
        </p>
      )}

      <StageIndicator 
        stages={stages} 
        currentStage={currentStage}
      />

      {messages.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Status Messages</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              {messages.map((msg, index) => (
                <div key={index} className="text-sm">
                  <p className="font-medium">{msg.text}</p>
                  {msg.stage && (
                    <p className="text-xs text-muted-foreground">
                      {msg.stage}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

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
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Audio Analysis Results</CardTitle>
          </CardHeader>
          <CardContent>
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
            </div>
          </CardContent>
        </Card>
      )}

      {scenePlanResults && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Scene Plan</CardTitle>
          </CardHeader>
          <CardContent>
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
          </CardContent>
        </Card>
      )}
    </div>
  )
}

