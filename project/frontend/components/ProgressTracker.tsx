"use client"

import { useState, useEffect } from "react"
import { useSSE } from "@/hooks/useSSE"
import { jobStore } from "@/stores/jobStore"
import { Progress } from "@/components/ui/progress"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { StageIndicator } from "@/components/StageIndicator"
import { Alert, AlertDescription } from "@/components/ui/alert"
import type { StageUpdateEvent, ProgressEvent, MessageEvent, CostUpdateEvent, CompletedEvent, ErrorEvent, AudioParserResultsEvent } from "@/types/sse"
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
  const [debugInfo, setDebugInfo] = useState<string>("")
  const [dataSource, setDataSource] = useState<"sse" | "database" | null>(null)

  const { updateJob, fetchJob } = jobStore()

  // Detect if data looks like fallback/uniform pattern
  const detectFallbackPattern = (results: AudioParserResultsEvent): {
    isFallback: boolean
    reasons: string[]
  } => {
    const reasons: string[] = []
    let isFallback = false

    // Check for exactly 120 BPM (common fallback)
    if (Math.abs(results.bpm - 120) < 0.1) {
      reasons.push("BPM is exactly 120.0 (suspicious)")
      isFallback = true
    }

    // Check for uniform beat intervals (0.5s = 120 BPM)
    if (results.beat_timestamps.length > 10) {
      const intervals: number[] = []
      for (let i = 1; i < Math.min(20, results.beat_timestamps.length); i++) {
        intervals.push(results.beat_timestamps[i] - results.beat_timestamps[i - 1])
      }
      const avgInterval = intervals.reduce((a, b) => a + b, 0) / intervals.length
      const isUniform = intervals.every(iv => Math.abs(iv - avgInterval) < 0.01)
      if (isUniform && Math.abs(avgInterval - 0.5) < 0.01) {
        reasons.push("Beats are uniformly spaced at 0.5s intervals (fallback pattern)")
        isFallback = true
      }
    }

    // Check for uniform structure pattern (intro-verse-chorus-verse-chorus-outro)
    if (results.song_structure.length === 6) {
      const types = results.song_structure.map(s => s.type.toLowerCase())
      const uniformPattern = ["intro", "verse", "chorus", "verse", "chorus", "outro"]
      if (types.every((t, i) => t === uniformPattern[i])) {
        reasons.push("Structure matches uniform fallback pattern (intro-verse-chorus-verse-chorus-outro)")
        isFallback = true
      }
    }

    // Check for uniform segment durations (10s, 20s, 20s, 20s, 20s, 10s)
    if (results.song_structure.length >= 4) {
      const durations = results.song_structure.map(s => s.end - s.start)
      const firstDuration = durations[0]
      const middleDuration = durations[1]
      const lastDuration = durations[durations.length - 1]
      if (
        Math.abs(firstDuration - 10) < 0.1 &&
        Math.abs(middleDuration - 20) < 0.1 &&
        Math.abs(lastDuration - 10) < 0.1 &&
        durations.slice(1, -1).every(d => Math.abs(d - 20) < 0.1)
      ) {
        reasons.push("Segments have uniform durations (10s, 20s, 20s, ...)")
        isFallback = true
      }
    }

    return { isFallback, reasons }
  }
  
  // Initialize progress from job state if available
  useEffect(() => {
    if (currentJob) {
      if (currentJob.progress !== undefined) setProgress(currentJob.progress)
      if (currentJob.currentStage) setCurrentStage(currentJob.currentStage)
      if (currentJob.estimatedRemaining) setEstimatedRemaining(currentJob.estimatedRemaining)
      if (currentJob.totalCost) setCost(currentJob.totalCost)
    }
  }, [currentJob])

  // Try to fetch audio_data from job if SSE event not received
  useEffect(() => {
    const checkForAudioData = async () => {
      if (!audioResults && currentJob && currentJob.id === jobId) {
        try {
          // Fetch job to get audio_data from database
          await fetchJob(jobId)
          setDebugInfo("Checking database for audio_data...")
        } catch (err: any) {
          setDebugInfo(`Error fetching job: ${err?.message || String(err)}`)
        }
      }
    }
    
    // Check after 5 seconds if no audio results received
    const timer = setTimeout(checkForAudioData, 5000)
    return () => clearTimeout(timer)
  }, [audioResults, currentJob, jobId, fetchJob])

  // Convert audioData from job to audioResults format if available
  // Only use database data if SSE event hasn't been received after a delay
  useEffect(() => {
    if (!audioResults && currentJob?.audioData) {
      const audioData = currentJob.audioData
      
      // Check if this looks like fallback data
      const isLikelyFallback = 
        Math.abs(audioData.bpm - 120) < 0.1 || // Exactly 120 BPM
        (audioData.beat_timestamps.length > 10 && 
         audioData.beat_timestamps.slice(1, 6).every((t, i) => 
           Math.abs((t - audioData.beat_timestamps[i]) - 0.5) < 0.01
         )) // Uniform 0.5s intervals
      
      if (isLikelyFallback) {
        console.warn("⚠️ Database contains fallback data, waiting for SSE event...")
        setDebugInfo("Database has fallback data - waiting for real analysis via SSE")
        return // Don't use fallback data from database
      }
      
      const converted: AudioParserResultsEvent = {
        bpm: audioData.bpm,
        duration: audioData.duration,
        beat_timestamps: audioData.beat_timestamps,
        beat_count: audioData.beat_timestamps.length,
        song_structure: audioData.song_structure,
        mood: audioData.mood,
        lyrics_count: audioData.lyrics.length,
        clip_boundaries_count: audioData.clip_boundaries.length,
        metadata: audioData.metadata,
      }
      console.log("✅ Loaded audio data from database:", converted)
      setAudioResults(converted)
      setDataSource("database")
      setDebugInfo("Loaded audio data from database (SSE event not received)")
    }
  }, [audioResults, currentJob])

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
      console.log("✅ Received audio_parser_results event:", data)
      setAudioResults(data)
      setDataSource("sse")
      setDebugInfo("Received audio data via SSE")
    },
  })

  return (
    <div className="w-full space-y-4">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">Progress</span>
          <span className="text-sm text-muted-foreground">{progress}%</span>
        </div>
        <Progress value={progress} />
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

      <StageIndicator stages={stages} currentStage={currentStage} />

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

      {!audioResults && (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-lg">Audio Analysis Status</CardTitle>
          </CardHeader>
          <CardContent>
            <Alert variant="warning">
              <AlertDescription>
                ⏳ Waiting for audio analysis results...
                {debugInfo && <div className="mt-2 text-xs">{debugInfo}</div>}
                <div className="mt-2 text-xs text-muted-foreground">
                  If this persists, the SSE event may not have been sent. Check backend logs.
                </div>
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      )}

      {audioResults && (() => {
        const fallbackCheck = detectFallbackPattern(audioResults)
        return (
          <Card className="mt-6">
            <CardHeader>
              <CardTitle className="text-lg">Audio Analysis Results</CardTitle>
              
              {/* Data Source Info */}
              <div className="mt-2 text-xs text-muted-foreground">
                Data source: <span className="font-mono">{dataSource || "unknown"}</span>
                {debugInfo && <span className="ml-2">• {debugInfo}</span>}
              </div>

              {/* Fallback Detection Warning */}
              {fallbackCheck.isFallback && (
                <Alert variant="destructive" className="mt-2">
                  <AlertDescription>
                    <div className="font-semibold mb-1">⚠️ FALLBACK DATA DETECTED</div>
                    <div className="text-sm space-y-1">
                      {fallbackCheck.reasons.map((reason, idx) => (
                        <div key={idx}>• {reason}</div>
                      ))}
                    </div>
                    <div className="mt-2 text-xs">
                      This appears to be uniform fallback data, not actual audio analysis. 
                      Check backend logs for audio parser errors.
                    </div>
                  </AlertDescription>
                </Alert>
              )}

              {/* Backend Fallback Warning */}
              {audioResults.metadata?.fallback_used && audioResults.metadata.fallback_used.length > 0 && (
                <Alert variant="warning" className="mt-2">
                  <AlertDescription>
                    ⚠️ Backend components used fallback methods: {audioResults.metadata.fallback_used.join(", ")}
                  </AlertDescription>
                </Alert>
              )}
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

              {/* Enhanced Debug Info Section - Always Visible */}
              <div className="mt-4 pt-4 border-t">
                <p className="text-sm font-semibold mb-2">Diagnostic Information</p>
                <div className="space-y-2 text-xs">
                  <div className="p-2 bg-muted rounded">
                    <div className="font-mono space-y-1">
                      <div><span className="font-semibold">Data Source:</span> <span className={dataSource === "sse" ? "text-green-600" : dataSource === "database" ? "text-yellow-600" : "text-gray-600"}>{dataSource || "unknown"}</span></div>
                      {debugInfo && <div><span className="font-semibold">Status:</span> {debugInfo}</div>}
                      {fallbackCheck.isFallback && (
                        <div className="text-destructive font-bold">⚠️ FALLBACK PATTERN DETECTED</div>
                      )}
                    </div>
                  </div>
                  
                  {audioResults.metadata && (
                    <div className="p-2 bg-muted rounded">
                      <div className="font-semibold mb-1">Backend Metadata:</div>
                      <div className="space-y-1 font-mono">
                        {audioResults.metadata.cache_hit !== undefined && (
                          <div>Cache Hit: {audioResults.metadata.cache_hit ? "Yes" : "No"}</div>
                        )}
                        {audioResults.metadata.processing_time !== undefined && (
                          <div>Processing Time: {audioResults.metadata.processing_time.toFixed(2)}s</div>
                        )}
                        {audioResults.metadata.beat_detection_confidence !== undefined && (
                          <div>Beat Detection Confidence: {(audioResults.metadata.beat_detection_confidence * 100).toFixed(1)}%</div>
                        )}
                        {audioResults.metadata.structure_confidence !== undefined && (
                          <div>Structure Confidence: {(audioResults.metadata.structure_confidence * 100).toFixed(1)}%</div>
                        )}
                        {audioResults.metadata.mood_confidence !== undefined && (
                          <div>Mood Confidence: {(audioResults.metadata.mood_confidence * 100).toFixed(1)}%</div>
                        )}
                      </div>
                    </div>
                  )}
                  
                  <div className="p-2 bg-muted rounded">
                    <div className="font-semibold mb-1">Beat Analysis:</div>
                    <div className="space-y-1 font-mono text-xs">
                      {audioResults.beat_timestamps.length > 0 && (
                        <div>First 5 beats: {audioResults.beat_timestamps.slice(0, 5).map(t => t.toFixed(2)).join(", ")}s</div>
                      )}
                      {audioResults.beat_timestamps.length > 5 && (
                        <div>Beat intervals (first 5): {audioResults.beat_timestamps.slice(1, 6).map((t, i) => 
                          (t - audioResults.beat_timestamps[i]).toFixed(3)
                        ).join(", ")}s</div>
                      )}
                      {audioResults.beat_timestamps.length > 0 && (
                        <div>Calculated BPM from intervals: {audioResults.beat_timestamps.length > 1 ? 
                          (60 / ((audioResults.beat_timestamps.slice(1, 6).reduce((a, b, i) => a + (b - audioResults.beat_timestamps[i]), 0) / Math.min(5, audioResults.beat_timestamps.length - 1)))).toFixed(1) : "N/A"
                        }</div>
                      )}
                    </div>
                  </div>
                  
                  <div className="p-2 bg-muted rounded">
                    <div className="font-semibold mb-1">Summary:</div>
                    <div className="space-y-1 font-mono">
                      <div>Lyrics: {audioResults.lyrics_count} words</div>
                      <div>Clip Boundaries: {audioResults.clip_boundaries_count} clips</div>
                      <div>Structure Segments: {audioResults.song_structure.length}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
        )
      })()}
    </div>
  )
}

