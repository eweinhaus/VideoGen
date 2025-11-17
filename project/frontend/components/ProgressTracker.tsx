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
  VideoGenerationStartEvent,
  VideoGenerationCompleteEvent,
  VideoGenerationFailedEvent,
  VideoGenerationRetryEvent,
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
  
  // Merge stages from database with local SSE-updated stages, prioritizing SSE updates
  // This prevents database lag from overriding real-time SSE completion events
  const displayStages = useMemo(() => {
    // CRITICAL: Always prioritize local stages from SSE - they're real-time
    // Only use database stages as fallback or to fill in missing stages
    if (stages.length > 0) {
      // We have local stages from SSE - use them as base
      const localStagesMap = new Map(stages.map(s => [s.name, s]))
      
      // Merge with database stages, but don't downgrade completed stages
      if (currentJob?.stages && Object.keys(currentJob.stages).length > 0) {
        Object.entries(currentJob.stages).forEach(([name, stageData]) => {
          const dbStatus = (stageData.status || "pending") as "pending" | "processing" | "completed" | "failed"
          const localStage = localStagesMap.get(name)
          
          if (!localStage) {
            // Stage exists in DB but not in local state - add it
            localStagesMap.set(name, { name, status: dbStatus })
          } else if (localStage.status === "completed" || localStage.status === "failed") {
            // Never downgrade completed or failed stages from SSE
            // Keep the local state
          } else {
            // For pending/processing stages, prefer database status if it's more advanced
            if (dbStatus === "completed" || dbStatus === "failed") {
              localStagesMap.set(name, { name, status: dbStatus })
            }
          }
        })
      }
      
      return Array.from(localStagesMap.values())
    }
    
    // Fallback: Use database stages if no local stages
    if (currentJob?.stages && Object.keys(currentJob.stages).length > 0) {
      return Object.entries(currentJob.stages).map(([name, stageData]) => ({
        name,
        status: (stageData.status || "pending") as "pending" | "processing" | "completed" | "failed",
      }))
    }
    
    // No stages at all
    return []
  }, [currentJob?.stages, stages])
  const [audioResults, setAudioResults] = useState<AudioParserResultsEvent | null>(null)
  const [scenePlanResults, setScenePlanResults] = useState<ScenePlannerResultsEvent | null>(null)
  const [promptResults, setPromptResults] = useState<PromptGeneratorResultsEvent | null>(null)
  const [referenceState, setReferenceState] = useState<ReferenceGenerationState>(initialReferenceState)
  const [videoTotals, setVideoTotals] = useState<{ total: number; completed: number; failed: number; retries: number }>({ total: 0, completed: 0, failed: 0, retries: 0 })
  const [clipStatuses, setClipStatuses] = useState<Record<number, "pending" | "processing" | "completed" | "failed" | "retrying">>({})
  
  // Timer state
  const [remainingTime, setRemainingTime] = useState<number | null>(initialValues.estimatedRemaining)
  const [timerStarted, setTimerStarted] = useState<boolean>(false)
  const [hasStarted, setHasStarted] = useState<boolean>(false)

  const { updateJob } = jobStore()
  // Removed truncatePrompt - show full prompt text as requested
  
  // Sync state when job data updates (for SSE updates to work correctly)
  useEffect(() => {
    if (currentJob) {
      // If job is completed, mark all stages as completed
      if (currentJob.status === "completed") {
        setStages((prev) => {
          const expectedStages = [
            "audio_parser",
            "scene_planner",
            "reference_generator",
            "prompt_generation",
            "video_generation",
            "composition",
          ]
          const updated = prev.map((s) => {
            if (s.status !== "failed") {
              return { ...s, status: "completed" as const }
            }
            return s
          })
          // Ensure all expected stages exist
          const existingNames = new Set(updated.map(s => s.name))
          expectedStages.forEach(stageName => {
            if (!existingNames.has(stageName)) {
              updated.push({ name: stageName, status: "completed" as const })
            }
          })
          return updated
        })
      }
      
      // Update state to match job data (SSE will override these)
      if (currentJob.progress !== undefined) {
        setProgress((prev) => currentJob.progress !== prev ? currentJob.progress : prev)
      }
      if (currentJob.currentStage !== undefined) {
        setCurrentStage((prev) => currentJob.currentStage !== prev ? currentJob.currentStage : prev)
      }
      if (currentJob.estimatedRemaining !== undefined) {
        const newRemaining = currentJob.estimatedRemaining ?? null
        setEstimatedRemaining((prev) => newRemaining !== prev ? newRemaining : prev)
        // Only update remainingTime if it's a new value (don't reset countdown unnecessarily)
        setRemainingTime((prev) => {
          // If we have a new estimate that's significantly different, update it
          // Otherwise, let the countdown continue
          if (newRemaining === null) return null
          if (prev === null) return newRemaining
          // Only update if the new value is significantly different (more than 10 seconds)
          // This prevents resetting the countdown on every render or minor updates
          // Allow updates if the new value is much larger (new estimate) or much smaller (shouldn't happen)
          if (Math.abs(newRemaining - prev) > 10 || newRemaining > prev) {
            return newRemaining
          }
          return prev // Keep the countdown going
        })
      }
      if (currentJob.totalCost !== undefined) {
        setCost((prev) => currentJob.totalCost !== prev ? (currentJob.totalCost ?? null) : prev)
      }
      
      if (currentJob.stages) {
        // Normalize stage names from database to match UI expectations
        const normalizeStageName = (name: string): string => {
          const n = name.toLowerCase()
          if (n === "audio_analysis") return "audio_parser"
          if (n === "scene_planning") return "scene_planner"
          if (n === "reference_generation") return "reference_generator"
          if (n === "prompt_generator") return "prompt_generation"
          if (n === "video_generator") return "video_generation"
          if (n === "composer") return "composition"
          return n
        }
        
        const jobStages = Object.entries(currentJob.stages).map(([name, stageData]) => ({
          name: normalizeStageName(name), // Normalize database stage names
          status: (stageData.status || "pending") as "pending" | "processing" | "completed" | "failed",
        }))
        setStages((prev) => {
          // CRITICAL: Don't overwrite local SSE stages with empty database stages
          // If database has no stages but we have local stages from SSE, keep local stages
          if (jobStages.length === 0 && prev.length > 0) {
            return prev
          }
          // Merge database stages with local stages, prioritizing completed status
          const mergedStages = new Map<string, { name: string; status: "pending" | "processing" | "completed" | "failed" }>()
          
          // Add all local stages first
          prev.forEach(s => {
            mergedStages.set(s.name, s)
          })
          
          // Add/update with database stages, but don't downgrade completed stages
          jobStages.forEach(dbStage => {
            const existing = mergedStages.get(dbStage.name)
            if (!existing) {
              // New stage from database
              mergedStages.set(dbStage.name, dbStage)
            } else if (existing.status !== "completed" && existing.status !== "failed") {
              // Update if database has more advanced status (completed/failed)
              if (dbStage.status === "completed" || dbStage.status === "failed") {
                mergedStages.set(dbStage.name, dbStage)
              }
            }
            // If local stage is already completed, keep it (don't downgrade)
          })
          
          const mergedArray = Array.from(mergedStages.values())
          const stagesChanged = JSON.stringify(mergedArray) !== JSON.stringify(prev)
          return stagesChanged ? mergedArray : prev
        })
      }
    }
  }, [currentJob]) // Only depend on currentJob to avoid infinite loops

  useEffect(() => {
    // Only reset referenceState when jobId changes, not when other values update
    // This prevents reference images from disappearing when video generation starts
    setReferenceState(initialReferenceState)
    setRemainingTime(initialValues.estimatedRemaining)
    setTimerStarted(false)
    setHasStarted(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]) // Removed initialValues.estimatedRemaining to prevent resetting reference images
  
  // Restore audio results from job data or stage metadata when page loads/refreshes
  // This ensures audio analysis section persists on page reload
  useEffect(() => {
    if (!audioResults) {
      // Try to restore from job.audioData first (if stored in jobs table)
      if (currentJob?.audioData) {
        try {
          const restoredAudioResults: AudioParserResultsEvent = {
            bpm: currentJob.audioData.bpm,
            duration: currentJob.audioData.duration,
            beat_timestamps: currentJob.audioData.beat_timestamps,
            beat_count: currentJob.audioData.beat_timestamps.length,
            song_structure: currentJob.audioData.song_structure,
            mood: currentJob.audioData.mood,
            lyrics_count: currentJob.audioData.lyrics?.length || 0,
            clip_boundaries_count: currentJob.audioData.clip_boundaries?.length || 0,
            clip_boundaries: currentJob.audioData.clip_boundaries,
            metadata: currentJob.audioData.metadata,
          }
          setAudioResults(restoredAudioResults)
          console.log("✅ Restored audio results from job.audioData")
          return
        } catch (error) {
          console.error("Failed to restore audio from job.audioData:", error)
        }
      }
      
      // Fallback: Try to restore from audio_parser stage metadata
      if (currentJob?.stages) {
        const audioParserStage = currentJob.stages.audio_parser || currentJob.stages.audio_analysis
        const audioMetadata = audioParserStage?.metadata?.audio_analysis
        if (audioMetadata) {
          try {
            const restoredAudioResults: AudioParserResultsEvent = {
              bpm: audioMetadata.bpm || 0,
              duration: audioMetadata.duration || 0,
              beat_timestamps: audioMetadata.beat_timestamps || [],
              beat_count: audioMetadata.beat_count || audioMetadata.beat_timestamps?.length || 0,
              song_structure: audioMetadata.song_structure || [],
              mood: audioMetadata.mood || { primary: "", confidence: 0 },
              lyrics_count: audioMetadata.lyrics_count || audioMetadata.lyrics?.length || 0,
              clip_boundaries_count: audioMetadata.clip_boundaries_count || audioMetadata.clip_boundaries?.length || 0,
              clip_boundaries: audioMetadata.clip_boundaries || [],
              metadata: audioMetadata.metadata || {},
            }
            setAudioResults(restoredAudioResults)
            console.log("✅ Restored audio results from stage metadata")
          } catch (error) {
            console.error("Failed to restore audio from stage metadata:", error)
          }
        }
      }
    }
  }, [currentJob?.audioData, currentJob?.stages, audioResults])
  
  // Restore video generation state from prompt results when page loads/refreshes
  // This ensures video generation section persists on page reload
  useEffect(() => {
    // If we have prompt results but no video totals, initialize from prompt results
    if (promptResults && promptResults.total_clips > 0) {
      setVideoTotals((prev) => {
        // Only update if we don't have totals yet, or if prompt results has more clips
        if (prev.total === 0 || promptResults.total_clips > prev.total) {
          return {
            total: promptResults.total_clips,
            completed: prev.completed, // Preserve existing completed count
            failed: prev.failed, // Preserve existing failed count
            retries: prev.retries, // Preserve existing retries count
          }
        }
        return prev
      })
      // Initialize clip statuses if we don't have them yet
      setClipStatuses((prev) => {
        if (Object.keys(prev).length === 0 && promptResults.total_clips > 0) {
          const initialStatuses: Record<number, "pending"> = {}
          for (let i = 0; i < promptResults.total_clips; i++) {
            initialStatuses[i] = "pending"
          }
          return initialStatuses
        }
        return prev
      })
    }
  }, [promptResults])
  
  // Restore scene plan and prompt data from stage metadata when page loads/refreshes
  // This ensures section content persists on page reload
  useEffect(() => {
    if (!currentJob?.stages) {
      console.log("⚠️ No stages found in currentJob:", currentJob)
      return
    }
    
    console.log("🔍 Checking stages for restoration:", Object.keys(currentJob.stages))
    
    // Restore scene plan from scene_planner stage metadata
    if (!scenePlanResults) {
      const scenePlannerStage = currentJob.stages.scene_planner || currentJob.stages.scene_planning
      console.log("🔍 Scene planner stage:", scenePlannerStage ? "found" : "not found", scenePlannerStage?.metadata ? "has metadata" : "no metadata")
      const scenePlanMetadata = scenePlannerStage?.metadata?.scene_plan
      if (scenePlanMetadata) {
        try {
          const restoredScenePlan: ScenePlannerResultsEvent = {
            job_id: jobId,
            video_summary: scenePlanMetadata.video_summary || "",
            characters: scenePlanMetadata.characters || [],
            scenes: scenePlanMetadata.scenes || [],
            style: scenePlanMetadata.style || {
              color_palette: [],
              visual_style: "",
              mood: "",
              lighting: "",
              cinematography: "",
            },
            clip_scripts: scenePlanMetadata.clip_scripts || [],
            transitions: scenePlanMetadata.transitions || [],
          }
          setScenePlanResults(restoredScenePlan)
          console.log("✅ Restored scene plan from metadata")
        } catch (error) {
          console.error("❌ Failed to restore scene plan from metadata:", error)
        }
      } else {
        console.log("⚠️ Scene plan metadata not found in stage")
      }
    } else {
      console.log("✅ Scene plan already restored")
    }
    
    // Restore prompt data from prompt_generator stage metadata
    // Note: metadata structure is {clip_prompts: {clip_prompts: [...], total_clips: N, ...}}
    if (!promptResults) {
      const promptGeneratorStage = currentJob.stages.prompt_generator || currentJob.stages.prompt_generation
      console.log("🔍 Prompt generator stage:", promptGeneratorStage ? "found" : "not found", promptGeneratorStage?.metadata ? "has metadata" : "no metadata")
      console.log("🔍 Full metadata:", JSON.stringify(promptGeneratorStage?.metadata, null, 2))
      
      // The metadata structure is: {clip_prompts: {clip_prompts: [...], total_clips: N, ...}}
      const promptData = promptGeneratorStage?.metadata?.clip_prompts
      const clipPromptsArray = promptData?.clip_prompts
      
      if (clipPromptsArray && Array.isArray(clipPromptsArray) && clipPromptsArray.length > 0) {
        try {
          const restoredPrompts: PromptGeneratorResultsEvent = {
            total_clips: promptData.total_clips || clipPromptsArray.length,
            generation_time: promptData.generation_time || 0,
            llm_used: promptData.llm_used || false,
            llm_model: promptData.llm_model || null,
            clip_prompts: clipPromptsArray.map((cp: any) => ({
              clip_index: cp.clip_index || 0,
              prompt: cp.prompt || "",
              negative_prompt: cp.negative_prompt || "",
              duration: cp.duration || 5.0,
              scene_reference_url: cp.scene_reference_url || null,
              character_reference_urls: cp.character_reference_urls || [],
              metadata: cp.metadata || {},
            })),
          }
          setPromptResults(restoredPrompts)
          console.log("✅ Restored prompt data from metadata, total clips:", restoredPrompts.total_clips)
        } catch (error) {
          console.error("❌ Failed to restore prompt data from metadata:", error)
        }
      } else {
        console.log("⚠️ Prompt metadata not found or empty. promptData:", promptData, "clipPromptsArray:", clipPromptsArray)
      }
    } else {
      console.log("✅ Prompt data already restored")
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentJob?.stages, scenePlanResults, promptResults, jobId])
  
  // Restore reference images state when job data is loaded on refresh
  // This ensures reference images section doesn't disappear when page is refreshed
  useEffect(() => {
    if (!currentJob) {
      console.log("⚠️ No currentJob for reference restoration")
      return
    }
    
    if (Object.keys(referenceState.images).length > 0) {
      console.log("✅ Reference images already in state, skipping restoration")
      return
    }
    
    console.log("🔍 Checking for reference images restoration. currentJob.stages:", currentJob.stages)
    const referenceStage = currentJob.stages?.reference_generator || currentJob.stages?.reference_generation
    console.log("🔍 Reference stage:", referenceStage)
    const referenceMetadata = referenceStage?.metadata?.reference_images
    console.log("🔍 Reference metadata:", referenceMetadata)
    
    if (referenceMetadata) {
      try {
        console.log("🔍 Restoring reference images from metadata:", referenceMetadata)
        
        // Build images map from scene_references and character_references
        const images: Record<string, ReferenceImageEntry> = {}
        
        // Add scene references
        if (referenceMetadata.scene_references && Array.isArray(referenceMetadata.scene_references)) {
          referenceMetadata.scene_references.forEach((ref: any) => {
            const imageId = ref.scene_id || ref.image_url
            const key = `scene:${imageId}`
            images[key] = {
              key,
              imageId,
              imageType: "scene",
              status: "completed",
              imageUrl: ref.image_url,
              cost: parseFloat(ref.cost) || 0,
              generationTime: ref.generation_time || 0
            }
          })
        }
        
        // Add character references
        if (referenceMetadata.character_references && Array.isArray(referenceMetadata.character_references)) {
          referenceMetadata.character_references.forEach((ref: any) => {
            const imageId = ref.character_id || ref.image_url
            const key = `character:${imageId}`
            images[key] = {
              key,
              imageId,
              imageType: "character",
              status: "completed",
              imageUrl: ref.image_url,
              cost: parseFloat(ref.cost) || 0,
              generationTime: ref.generation_time || 0
            }
          })
        }
        
        if (Object.keys(images).length > 0) {
          setReferenceState({
            totalImages: referenceMetadata.total_references || Object.keys(images).length,
            completedImages: referenceMetadata.total_references || Object.keys(images).length,
            images
          })
          console.log("✅ Restored reference images from metadata, total:", Object.keys(images).length)
        } else {
          console.log("⚠️ Reference metadata found but no images in it")
        }
      } catch (error) {
        console.error("❌ Failed to restore reference images from metadata:", error)
      }
    } else {
      console.log("⚠️ No reference images metadata found in stage")
    }
  }, [currentJob, referenceState.images])
  
  // Restore video clips state when job data is loaded on refresh
  useEffect(() => {
    if (!currentJob) {
      console.log("⚠️ No currentJob for video clips restoration")
      return
    }
    
    // FIX: Check if clipStatuses is empty, not videoTotals.total
    // videoTotals.total can be set from promptResults before clips are restored,
    // causing a race condition where restoration is skipped even though clipStatuses is empty
    const hasClipStatuses = Object.keys(clipStatuses).length > 0
    if (hasClipStatuses) {
      console.log("✅ Video clips already in state, skipping restoration")
      return
    }
    
    console.log("🔍 Checking for video clips restoration. currentJob.stages:", currentJob.stages)
    const videoStage = currentJob.stages?.video_generator || currentJob.stages?.video_generation
    console.log("🔍 Video stage:", videoStage)
    const clipsMetadata = videoStage?.metadata?.clips
    console.log("🔍 Clips metadata:", clipsMetadata)
    
    if (clipsMetadata && clipsMetadata.clips && Array.isArray(clipsMetadata.clips)) {
      try {
        console.log("🔍 Restoring video clips from metadata:", clipsMetadata)
        
        const statuses: Record<number, "pending" | "processing" | "completed" | "failed" | "retrying"> = {}
        let completed = 0
        let failed = 0
        let retries = 0
        
        clipsMetadata.clips.forEach((clip: any) => {
          const clipIndex = clip.clip_index
          const clipStatus = clip.status === "success" ? "completed" : "failed"
          statuses[clipIndex] = clipStatus
          
          if (clipStatus === "completed") {
            completed++
          } else if (clipStatus === "failed") {
            failed++
          }
          
          if (clip.retry_count > 0) {
            retries += clip.retry_count
          }
        })
        
        setClipStatuses(statuses)
        setVideoTotals({
          total: clipsMetadata.total_clips || clipsMetadata.clips.length,
          completed,
          failed,
          retries
        })
        console.log("✅ Restored video clips from metadata, total:", clipsMetadata.total_clips || clipsMetadata.clips.length, "completed:", completed)
      } catch (error) {
        console.error("❌ Failed to restore video clips from metadata:", error)
      }
    } else {
      console.log("⚠️ No video clips metadata found in stage")
    }
  }, [currentJob, clipStatuses])
  
  // Timer effect - starts when job begins and stops when complete/failed
  useEffect(() => {
    if (!timerStarted && currentJob && currentJob.status === "processing") {
      setTimerStarted(true)
    }
    
    if (!timerStarted) return
    
    // Stop timer if job is complete or failed
    if (currentJob && (currentJob.status === "completed" || currentJob.status === "failed")) {
      return
    }
    
    const interval = setInterval(() => {
      // Update remaining time (countdown) if available
      setRemainingTime((prev) => {
        if (prev === null || prev <= 0) {
          // Update job store when timer reaches 0
          if (prev === 0) {
            updateJob(jobId, { estimatedRemaining: 0 })
          }
          return prev
        }
        const newValue = prev - 1
        // Update job store with countdown value so header stays in sync
        updateJob(jobId, { estimatedRemaining: newValue })
        return newValue
      })
    }, 1000)
    
    return () => clearInterval(interval)
  }, [timerStarted, currentJob, jobId, updateJob])

  const referenceKey = (imageType: string, imageId: string) => `${imageType}:${imageId}`
  
  // Format remaining time (countdown)
  const formatRemainingTime = (seconds: number | null): string => {
    if (seconds === null) return ""
    if (seconds < 0) return "Less than a minute remaining"
    if (seconds < 60) return "Less than a minute remaining"
    
    const minutes = Math.ceil(seconds / 60)
    return `About ${minutes} minute${minutes !== 1 ? 's' : ''} remaining`
  }

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

      // Use total_images from event if provided (most accurate), otherwise use current count
      // Event value is authoritative - always prefer it over calculated values
      const totalImages = data.total_images !== undefined 
        ? Math.max(data.total_images, prev.totalImages) 
        : Math.max(prev.totalImages ?? 0, Object.keys({ ...prev.images, [key]: updatedEntry }).length)

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
      const wasAlreadyCompleted = previousEntry?.status === "completed"
      
      // Event's total_images is authoritative - always use it if provided
      const totalImages = data.total_images !== undefined 
        ? data.total_images 
        : Math.max(prev.totalImages ?? 0, Object.keys({ ...prev.images, [key]: {} }).length)
      
      // Event's completed_images is authoritative - always use it if provided
      // Otherwise, only increment if this image wasn't already completed
      let finalCompletedImages: number
      if (data.completed_images !== undefined) {
        // Use event's completed_images (authoritative)
        finalCompletedImages = Math.min(data.completed_images, totalImages)
      } else if (wasAlreadyCompleted) {
        // Already counted, don't increment
        finalCompletedImages = prev.completedImages
      } else {
        // Increment by 1, but cap at totalImages
        finalCompletedImages = Math.min(prev.completedImages + 1, totalImages)
      }

      return {
        totalImages: Math.max(totalImages, prev.totalImages ?? 0), // Never decrease total
        completedImages: Math.max(finalCompletedImages, prev.completedImages), // Never decrease completed
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
      // Debug logging for all stage updates
      console.log("📡 Stage update received:", { stage: data.stage, status: data.status, data })
      
      // Normalize stage names so spinners/checkmarks display correctly
      const normalize = (name: string) => {
        const n = name.toLowerCase()
        if (n === "audio_analysis") return "audio_parser"
        if (n === "scene_planning") return "scene_planner"
        if (n === "reference_generation") return "reference_generator"
        if (n === "prompt_generator") return "prompt_generation"
        if (n === "video_generator") return "video_generation"
        if (n === "composer") return "composition"
        return n
      }
      const stage = normalize(data.stage)
      console.log("📡 Normalized stage:", { original: data.stage, normalized: stage, status: data.status })
      if (!hasStarted) setHasStarted(true)
      setCurrentStage(stage)
      
      const statusMap: Record<string, "pending" | "processing" | "completed" | "failed"> = {
        started: "processing",
        processing: "processing",
        completed: "completed",
        failed: "failed",
        pending: "pending",
      }
      const status = statusMap[(data.status || "").toLowerCase()] || "processing"
      
      // Debug logging for stage completions
      if (stage === "audio_parser" && status === "completed") {
        console.log("✅ Audio parser completed:", { stage, status, data })
      }
      if (stage === "prompt_generation" && status === "completed") {
        console.log("✅ Prompt generator completed:", { stage, status, data })
      }
      if (stage === "composition" && status === "completed") {
        console.log("✅ Composer completed:", { stage, status, data })
      }
      
      setStages((prev) => {
        // Normalize all existing stage names for consistent comparison
        const normalizeStageName = (name: string): string => {
          const n = name.toLowerCase()
          if (n === "audio_analysis") return "audio_parser"
          if (n === "scene_planning") return "scene_planner"
          if (n === "reference_generation") return "reference_generator"
          if (n === "prompt_generator") return "prompt_generation"
          if (n === "video_generator") return "video_generation"
          if (n === "composer") return "composition"
          return n
        }
        // Find existing stage using normalized names
        const existing = prev.find((s) => normalizeStageName(s.name) === stage)

        // Define stage order for marking previous stages as completed
        const stageOrder = [
          "audio_parser",
          "scene_planner",
          "reference_generator",
          "prompt_generation",
          "video_generation",
          "composition",
        ]
        
        // Stage is already normalized from the normalize() function above
        const normalizedStage = stage
        const currentStageIndex = stageOrder.indexOf(normalizedStage)

        // Mark all previous stages as completed when a stage completes OR when a new stage starts (and it's a later stage)
        const shouldMarkPreviousCompleted = status === "completed" || (currentStageIndex !== -1 && currentStageIndex > 0)
        
        // Update or add stage
        let updatedStages = prev.map((s) => {
          const normalizedSName = normalizeStageName(s.name)
          const sStageIndex = stageOrder.indexOf(normalizedSName)
          
          // If this is the stage being updated, update its status (compare normalized names)
          if (normalizedSName === normalizedStage) {
            // Don't downgrade from completed to processing
            if (s.status === "completed" && status === "processing") {
              return s // Keep completed status
            }
            // Always mark as completed if status is "completed"
            if (status === "completed") {
              return { ...s, status: "completed" as const }
            }
            return { ...s, status: status as "pending" | "processing" | "completed" | "failed" }
          }
          
          // Mark previous stages as completed when current stage completes or new stage starts
          if (shouldMarkPreviousCompleted && sStageIndex !== -1 && sStageIndex < currentStageIndex && s.status !== "completed" && s.status !== "failed") {
            return { ...s, status: "completed" as const }
          }
          
          return s
        })
        
        // If stage doesn't exist yet, add it
        if (!existing) {
          // Ensure we mark all previous stages as completed before adding the new one
          if (shouldMarkPreviousCompleted) {
            updatedStages = updatedStages.map((s) => {
              const normalizedSName = normalizeStageName(s.name)
              const sStageIndex = stageOrder.indexOf(normalizedSName)
              if (sStageIndex !== -1 && sStageIndex < currentStageIndex && s.status !== "completed" && s.status !== "failed") {
                return { ...s, status: "completed" as const }
              }
              return s
            })
          }
          const finalStatus = status === "completed" ? "completed" as const : (status as "pending" | "processing" | "completed" | "failed")
          updatedStages = [...updatedStages, { name: normalizedStage, status: finalStatus }]
        }
        
        // Persist stages to job store for persistence (only update if changed to prevent unnecessary re-renders)
        const stagesRecord = updatedStages.reduce((acc, s) => {
          acc[s.name] = { status: s.status }
          return acc
        }, {} as Record<string, { status: string }>)
        // Use setTimeout to debounce job store updates and prevent cascading re-renders
        setTimeout(() => {
          updateJob(jobId, { currentStage: normalizedStage, stages: stagesRecord })
        }, 0)
        
        return updatedStages
      })
    },
    onProgress: (data: ProgressEvent) => {
      console.log("📊 Progress event handler called:", data)
      setProgress(data.progress)
      updateJob(jobId, { progress: data.progress })
      if (data.estimated_remaining !== undefined && data.estimated_remaining !== null) {
        setEstimatedRemaining(data.estimated_remaining)
        setRemainingTime(data.estimated_remaining)
        // Update job store so header can display estimated time
        updateJob(jobId, { estimatedRemaining: data.estimated_remaining })
      }
      // Handle cost from initial progress event (includes total_cost in initial state)
      if (data.total_cost !== undefined && data.total_cost !== null) {
        setCost(data.total_cost)
        updateJob(jobId, { totalCost: data.total_cost })
      }
      
      // If progress event includes stage and status, also update stage status
      // This handles cases where stage updates come through progress events
      if (data.stage && data.status) {
        console.log("📊 Progress event includes stage status, triggering stage update:", { stage: data.stage, status: data.status })
        // Trigger stage update handler with the stage info from progress event
        const stageUpdateData = {
          stage: data.stage,
          status: data.status
        } as StageUpdateEvent
        // Call the stage update handler directly
        const normalize = (name: string) => {
          const n = name.toLowerCase()
          if (n === "audio_analysis") return "audio_parser"
          if (n === "scene_planning") return "scene_planner"
          if (n === "reference_generation") return "reference_generator"
          if (n === "prompt_generator") return "prompt_generation"
          if (n === "video_generator") return "video_generation"
          if (n === "composer") return "composition"
          return n
        }
        const stage = normalize(stageUpdateData.stage)
        if (!hasStarted) setHasStarted(true)
        setCurrentStage(stage)
        
        const statusMap: Record<string, "pending" | "processing" | "completed" | "failed"> = {
          started: "processing",
          processing: "processing",
          completed: "completed",
          failed: "failed",
          pending: "pending",
          queued: "pending",
        }
        const status = statusMap[(stageUpdateData.status || "").toLowerCase()] || "processing"
        
        // Update stages state
        setStages((prev) => {
          const normalizeStageName = (name: string): string => {
            const n = name.toLowerCase()
            if (n === "audio_analysis") return "audio_parser"
            if (n === "scene_planning") return "scene_planner"
            if (n === "reference_generation") return "reference_generator"
            if (n === "prompt_generator") return "prompt_generation"
            if (n === "video_generator") return "video_generation"
            if (n === "composer") return "composition"
            return n
          }
          const existing = prev.find((s) => normalizeStageName(s.name) === stage)
          
          const stageOrder = [
            "audio_parser",
            "scene_planner",
            "reference_generator",
            "prompt_generation",
            "video_generation",
            "composition",
          ]
          const currentStageIndex = stageOrder.indexOf(stage)
          const shouldMarkPreviousCompleted = status === "completed" || (currentStageIndex !== -1 && currentStageIndex > 0)
          
          let updatedStages = prev.map((s) => {
            const normalizedSName = normalizeStageName(s.name)
            const sStageIndex = stageOrder.indexOf(normalizedSName)
            
            if (normalizedSName === stage) {
              if (s.status === "completed" && status === "processing") {
                return s
              }
              if (status === "completed") {
                return { ...s, status: "completed" as const }
              }
              return { ...s, status: status as "pending" | "processing" | "completed" | "failed" }
            }
            
            if (shouldMarkPreviousCompleted && sStageIndex !== -1 && sStageIndex < currentStageIndex && s.status !== "completed" && s.status !== "failed") {
              return { ...s, status: "completed" as const }
            }
            
            return s
          })
          
          if (!existing) {
            if (shouldMarkPreviousCompleted) {
              updatedStages = updatedStages.map((s) => {
                const normalizedSName = normalizeStageName(s.name)
                const sStageIndex = stageOrder.indexOf(normalizedSName)
                if (sStageIndex !== -1 && sStageIndex < currentStageIndex && s.status !== "completed" && s.status !== "failed") {
                  return { ...s, status: "completed" as const }
                }
                return s
              })
            }
            const finalStatus = status === "completed" ? "completed" as const : (status as "pending" | "processing" | "completed" | "failed")
            updatedStages = [...updatedStages, { name: stage, status: finalStatus }]
          }
          
          const stagesRecord = updatedStages.reduce((acc, s) => {
            acc[s.name] = { status: s.status }
            return acc
          }, {} as Record<string, { status: string }>)
          setTimeout(() => {
            updateJob(jobId, { currentStage: stage, stages: stagesRecord })
          }, 0)
          
          return updatedStages
        })
      }
    },
    onCostUpdate: (data: CostUpdateEvent) => {
      console.log("💰 Cost update received in ProgressTracker:", data)
      setCost(data.total)
      updateJob(jobId, { totalCost: data.total })
    },
    onCompleted: (data: CompletedEvent) => {
      updateJob(jobId, {
        status: "completed",
        videoUrl: data.video_url,
        progress: 100,
      })
      // Mark all stages as completed when job completes
      setStages((prev) => {
        const updated = prev.map((s) => {
          if (s.status !== "failed") {
            return { ...s, status: "completed" as const }
          }
          return s
        })
        // Also ensure all expected stages exist and are marked as completed
        const expectedStages = [
          "audio_parser",
          "scene_planner",
          "reference_generator",
          "prompt_generation",
          "video_generation",
          "composition",
        ]
        const existingNames = new Set(updated.map(s => s.name))
        expectedStages.forEach(stageName => {
          if (!existingNames.has(stageName)) {
            updated.push({ name: stageName, status: "completed" as const })
          }
        })
        return updated
      })
      // Update job store with all completed stages
      const stagesRecord: Record<string, { status: string }> = {}
      const allStages = ["audio_parser", "scene_planner", "reference_generator", "prompt_generation", "video_generation", "composition"]
      allStages.forEach(stage => {
        stagesRecord[stage] = { status: "completed" }
      })
      updateJob(jobId, { stages: stagesRecord })
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
      // Initialize video totals from prompt results if not already set
      setVideoTotals((prev) => {
        if (data.total_clips > 0 && prev.total === 0) {
          return {
            total: data.total_clips,
            completed: 0,
            failed: 0,
            retries: 0,
          }
        }
        return prev
      })
      // Initialize all clips as pending if we have a new total
      if (data.total_clips > 0) {
        setClipStatuses((prev) => {
          // Only initialize if we don't have statuses yet
          if (Object.keys(prev).length === 0) {
            const initialStatuses: Record<number, "pending"> = {}
            for (let i = 0; i < data.total_clips; i++) {
              initialStatuses[i] = "pending"
            }
            return initialStatuses
          }
          return prev
        })
      }
    },
    onVideoGenerationStart: (data: VideoGenerationStartEvent) => {
      setClipStatuses((prev) => ({ ...prev, [data.clip_index]: "processing" }))
      setVideoTotals((prev) => ({
        total: Math.max(prev.total, data.total_clips || prev.total || (promptResults?.total_clips ?? 0)),
        completed: prev.completed,
        failed: prev.failed,
        retries: prev.retries,
      }))
    },
    onVideoGenerationComplete: (data: VideoGenerationCompleteEvent) => {
      setClipStatuses((prev) => ({ ...prev, [data.clip_index]: "completed" }))
      setVideoTotals((prev) => ({
        total: prev.total || (promptResults?.total_clips ?? 0),
        completed: prev.completed + 1,
        failed: prev.failed,
        retries: prev.retries,
      }))
    },
    onVideoGenerationFailed: (data: VideoGenerationFailedEvent) => {
      setClipStatuses((prev) => ({ ...prev, [data.clip_index]: "failed" }))
      setVideoTotals((prev) => ({
        total: prev.total || (promptResults?.total_clips ?? 0),
        completed: prev.completed,
        failed: prev.failed + 1,
        retries: prev.retries,
      }))
    },
    onVideoGenerationRetry: (data: VideoGenerationRetryEvent) => {
      setClipStatuses((prev) => ({ ...prev, [data.clip_index]: "retrying" }))
      setVideoTotals((prev) => ({
        total: prev.total || (promptResults?.total_clips ?? 0),
        completed: prev.completed,
        failed: prev.failed,
        retries: prev.retries + 1,
      }))
    },
    onReferenceGenerationStart: handleReferenceStart,
    onReferenceGenerationComplete: handleReferenceComplete,
    onReferenceGenerationFailed: handleReferenceFailed,
    onReferenceGenerationRetry: handleReferenceRetry,
  })

  return (
    <div className="w-full space-y-4">
      {/* Loading overlay to make the transition smoother until SSE is ready */}
      {!hasStarted && !isConnected && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-background/70 backdrop-blur-sm">
          <div className="w-[320px] rounded-lg border bg-card p-5 shadow-lg">
            <div className="mb-3 text-sm font-medium">Preparing job progress…</div>
            <Progress value={Math.min(displayProgress || 10, 90)} className="h-2" />
            <div className="mt-2 text-xs text-muted-foreground">Connecting to server…</div>
          </div>
        </div>
      )}
      <div className="space-y-3 p-4 bg-muted/30 rounded-lg border min-h-[120px] flex flex-col justify-center">
        <div className="flex items-center justify-between mb-2">
          <span className="text-base font-semibold">Progress</span>
          <span className="text-base font-semibold text-muted-foreground">{displayProgress}%</span>
        </div>
        <Progress value={displayProgress} className="h-3" />
        {(remainingTime !== null && remainingTime !== undefined) || displayStage === "audio_parser" || displayStage === "audio_analysis" ? (
          <p className="text-sm text-muted-foreground mt-2">
            {remainingTime !== null && remainingTime !== undefined
              ? formatRemainingTime(remainingTime)
              : (displayStage === "audio_parser" || displayStage === "audio_analysis")
              ? "Estimating time remaining..."
              : ""}
          </p>
        ) : null}
      </div>

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

      {/* Only show connection message if job is still processing and not connected */}
      {!isConnected && !sseError && currentJob && currentJob.status === "processing" && (
        <Alert>
          <AlertDescription>Connecting to server...</AlertDescription>
        </Alert>
      )}

      {/* Show Audio Analysis section if we have results OR if the stage is completed (for refresh scenarios) */}
      {(audioResults || currentJob?.stages?.audio_parser?.status === "completed" || currentJob?.stages?.audio_analysis?.status === "completed") && (
        <CollapsibleCard title="Audio Analysis" defaultOpen={false}>
            {audioResults ? (
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">BPM</p>
                  <p className="text-xl font-bold leading-tight">{audioResults.bpm.toFixed(1)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Duration</p>
                  <p className="text-xl font-bold leading-tight">{formatDuration(audioResults.duration)}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Beats Detected</p>
                  <p className="text-xl font-bold leading-tight">{audioResults.beat_count}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Structure Segments</p>
                  <p className="text-xl font-bold leading-tight">{audioResults.song_structure.length}</p>
                </div>
              </div>
              
              <div>
                <p className="text-xs font-medium text-muted-foreground mb-1">Mood</p>
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
                <p className="text-xs font-medium text-muted-foreground mb-1">Song Structure</p>
                <div className="space-y-0.5">
                  {audioResults.song_structure.map((seg, idx) => (
                    <div key={idx} className="flex items-center justify-between text-xs">
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
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    First {Math.min(20, audioResults.beat_timestamps.length)} Beats (seconds)
                  </p>
                  <p className="text-xs font-mono text-muted-foreground leading-tight">
                    {audioResults.beat_timestamps.map(t => t.toFixed(2)).join(", ")}
                  </p>
                </div>
              )}

              {audioResults.clip_boundaries && audioResults.clip_boundaries.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground mb-1">
                    Clip Boundaries ({audioResults.clip_boundaries.length} clips)
                  </p>
                  <div className="space-y-0.5 max-h-60 overflow-y-auto">
                    {audioResults.clip_boundaries.map((boundary, idx) => (
                      <div key={idx} className="flex items-center justify-between text-xs p-1.5 bg-muted/30 rounded">
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
                <div className="mt-2 pt-2 border-t">
                  <p className="text-xs font-medium text-muted-foreground mb-1">Analysis Metadata</p>
                  <div className="space-y-1 text-xs leading-tight">
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
            ) : (
              <div className="text-sm text-muted-foreground">
                Audio analysis completed. Data will be restored when available.
              </div>
            )}
        </CollapsibleCard>
      )}

      {/* Show Scene Planning section if we have results OR if the stage is completed (for refresh scenarios) */}
      {(scenePlanResults || currentJob?.stages?.scene_planner?.status === "completed") && (
        <CollapsibleCard title="Scene Planning" defaultOpen={false}>
            {scenePlanResults ? (
            <div className="space-y-2">
              <div className="prose prose-sm max-w-none dark:prose-invert">
                <h3 className="text-base font-semibold mb-1">Video Summary</h3>
                <p className="text-sm text-muted-foreground leading-tight">{scenePlanResults.video_summary}</p>
                
                <h3 className="text-base font-semibold mt-2 mb-1">Characters</h3>
                <ul className="list-disc list-inside space-y-0.5 text-sm">
                  {scenePlanResults.characters.map((char) => (
                    <li key={char.id} className="leading-tight">
                      <strong>{char.id}</strong> ({char.role}): {char.description}
                    </li>
                  ))}
                </ul>
                
                <h3 className="text-base font-semibold mt-2 mb-1">Scenes</h3>
                <ul className="list-disc list-inside space-y-0.5 text-sm">
                  {scenePlanResults.scenes.map((scene) => (
                    <li key={scene.id} className="leading-tight">
                      <strong>{scene.id}</strong> ({scene.time_of_day}): {scene.description}
                    </li>
                  ))}
                </ul>
                
                <h3 className="text-base font-semibold mt-2 mb-1">Style</h3>
                <div className="space-y-1 text-sm leading-tight">
                  <p><strong>Visual Style:</strong> {scenePlanResults.style.visual_style}</p>
                  <p><strong>Mood:</strong> {scenePlanResults.style.mood}</p>
                  <p><strong>Lighting:</strong> {scenePlanResults.style.lighting}</p>
                  <p><strong>Cinematography:</strong> {scenePlanResults.style.cinematography}</p>
                  <div>
                    <strong>Color Palette:</strong>
                    <div className="flex gap-1.5 mt-0.5">
                      {scenePlanResults.style.color_palette.map((color, idx) => (
                        <div
                          key={idx}
                          className="w-6 h-6 rounded border border-gray-300"
                          style={{ backgroundColor: color }}
                          title={color}
                        />
                      ))}
                    </div>
                  </div>
                </div>
                
                <h3 className="text-base font-semibold mt-2 mb-1">Clip Scripts</h3>
                <div className="space-y-1.5">
                  {scenePlanResults.clip_scripts.map((clip) => (
                    <div key={clip.clip_index} className="border-l-4 border-primary pl-3 py-1">
                      <div className="flex items-center justify-between mb-0.5">
                        <strong className="text-sm">Clip {clip.clip_index}</strong>
                        <span className="text-xs text-muted-foreground">
                          {clip.start.toFixed(1)}s - {clip.end.toFixed(1)}s
                        </span>
                      </div>
                      <p className="text-xs leading-tight">{clip.visual_description}</p>
                      <div className="text-xs text-muted-foreground mt-0.5 space-y-0 leading-tight">
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
                
                <h3 className="text-base font-semibold mt-2 mb-1">Transitions</h3>
                <div className="space-y-1">
                  {scenePlanResults.transitions.map((trans, idx) => (
                    <div key={idx} className="text-xs leading-tight">
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
            ) : (
              <div className="text-sm text-muted-foreground">
                Scene planning completed. Data will be restored when available.
              </div>
            )}
        </CollapsibleCard>
      )}

      {/* Show Reference Generation section if we have images OR if the stage is completed (for refresh scenarios) */}
      {(referenceImages.length > 0 || 
        currentJob?.stages?.reference_generator?.status === "completed" || 
        currentJob?.stages?.reference_generation?.status === "completed" ||
        stages.some(s => {
          const normalized = s.name.toLowerCase()
          return (normalized === "reference_generator" || normalized === "reference_generation") && s.status === "completed"
        })) && (
        <CollapsibleCard 
          title="Reference Generation" 
          defaultOpen={false}
        >
          {referenceImages.length > 0 ? (
          <div className="space-y-4">
            <div>
              <p className="text-sm text-muted-foreground mb-2">
                {referenceImages.filter(img => img.status === "completed").length}/{Math.max(referenceState.totalImages, referenceImages.length)} images ready
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
          ) : (
            <div className="text-sm text-muted-foreground">
              Reference generation completed. Images will be restored when available.
            </div>
          )}
        </CollapsibleCard>
      )}

      {/* Show Prompt Generation section if we have results OR if the stage is completed (for refresh scenarios) */}
      {(promptResults || 
        currentJob?.stages?.prompt_generator?.status === "completed" || 
        currentJob?.stages?.prompt_generation?.status === "completed" ||
        stages.some(s => {
          const normalized = s.name.toLowerCase()
          return (normalized === "prompt_generation" || normalized === "prompt_generator") && s.status === "completed"
        })) && (
        <CollapsibleCard title="Prompt Generation" defaultOpen={false}>
          {promptResults ? (
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
          ) : (
            <div className="text-sm text-muted-foreground">
              Prompt generation completed. Data will be restored when available.
            </div>
          )}
        </CollapsibleCard>
      )}

      {/* Show Video Generation section if we have totals OR if the stage is completed (for refresh scenarios) */}
      {(videoTotals.total > 0 || 
        currentJob?.stages?.video_generator?.status === "completed" || 
        currentJob?.stages?.video_generation?.status === "completed" ||
        stages.some(s => {
          const normalized = s.name.toLowerCase()
          return (normalized === "video_generation" || normalized === "video_generator") && s.status === "completed"
        })) && (
        <CollapsibleCard title="Video Generation" defaultOpen={false}>
          {videoTotals.total > 0 ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Overall Progress</span>
              <span className="font-medium">
                {videoTotals.completed}/{videoTotals.total} clips completed
              </span>
            </div>
            <Progress
              value={
                videoTotals.total > 0 ? (videoTotals.completed / videoTotals.total) * 100 : 0
              }
              className="h-2"
            />
            <div className="text-xs text-muted-foreground flex gap-4">
              <span>Failed: {videoTotals.failed}</span>
              <span>Retries: {videoTotals.retries}</span>
            </div>
            {videoTotals.total > 0 && (
              <div className="mt-2 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2">
                {Array.from({ length: videoTotals.total }).map((_, idx) => {
                  const status = clipStatuses[idx] || "pending"
                  return (
                    <div
                      key={idx}
                      className={
                        "flex items-center justify-between rounded border px-2 py-1 text-xs " +
                        (status === "completed"
                          ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                          : status === "failed"
                          ? "bg-rose-50 border-rose-200 text-rose-800"
                          : status === "retrying"
                          ? "bg-amber-50 border-amber-200 text-amber-800"
                          : "bg-muted/30 border-muted-200 text-muted-foreground")
                      }
                    >
                      <span>Clip {idx}</span>
                      <span
                        className={
                          "ml-2 h-3 w-3 rounded-full " +
                          (status === "completed"
                            ? "bg-emerald-500"
                            : status === "failed"
                            ? "bg-rose-500"
                            : status === "retrying"
                            ? "bg-amber-500"
                            : "bg-muted-foreground animate-pulse")
                        }
                        title={status}
                      />
                    </div>
                  )
                })}
              </div>
            )}
          </div>
          ) : (
            <div className="text-sm text-muted-foreground">
              Video generation in progress. Clip statuses will be restored when available.
            </div>
          )}
        </CollapsibleCard>
      )}
    </div>
  )
}

