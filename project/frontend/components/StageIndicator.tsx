"use client"

import { Card, CardContent } from "@/components/ui/card"
import { Check, X, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface Stage {
  name: string
  status: "pending" | "processing" | "completed" | "failed"
}

interface StageIndicatorProps {
  stages: Stage[]
  currentStage: string | null
  showOnly?: string[] // Optional: only show specific stages
}

const STAGE_DISPLAY_NAMES: Record<string, string> = {
  audio_parser: "Audio Analysis",
  audio_analysis: "Audio Analysis", // Alias for compatibility
  scene_planner: "Scene Planning",
  scene_planning: "Scene Planning", // Alias for compatibility
  reference_generator: "Reference Generation",
  reference_generation: "Reference Generation", // Alias for compatibility
  prompt_generation: "Prompt Generation",
  video_generation: "Video Generation",
  composition: "Composition",
}

const STAGE_ORDER = [
  "audio_parser",
  "scene_planner",
  "reference_generator",
  "prompt_generation",
  "video_generation",
  "composition",
]

export function StageIndicator({ stages, currentStage, showOnly }: StageIndicatorProps) {
  const stagesToShow = showOnly || STAGE_ORDER
  const orderedStages = stagesToShow.map((stageName) => {
    const stage = stages.find((s) => s.name === stageName)
    return {
      name: stageName,
      displayName: STAGE_DISPLAY_NAMES[stageName] || stageName,
      status: stage?.status || "pending",
      isCurrent: stageName === currentStage,
    }
  })

  const getStatusIcon = (status: string, isCurrent: boolean) => {
    if (status === "completed") {
      return <Check className="h-5 w-5 text-green-600" />
    }
    if (status === "failed") {
      return <X className="h-5 w-5 text-destructive" />
    }
    if (status === "processing" || isCurrent) {
      return <Loader2 className="h-5 w-5 animate-spin text-primary" />
    }
    return <div className="h-5 w-5 rounded-full border-2 border-muted-foreground" />
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex flex-row flex-nowrap gap-4 overflow-x-auto">
          {orderedStages.map((stage, index) => (
            <div
              key={stage.name}
              className={cn(
                "flex items-center gap-2 flex-shrink-0 whitespace-nowrap"
              )}
            >
              {getStatusIcon(stage.status, stage.isCurrent)}
              <span
                className={cn(
                  "text-sm",
                  stage.status === "completed" && "text-muted-foreground",
                  (stage.status === "processing" || stage.isCurrent) &&
                    "font-semibold text-primary",
                  stage.status === "failed" && "text-destructive",
                  stage.status === "pending" && "text-muted-foreground"
                )}
              >
                {stage.displayName}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

