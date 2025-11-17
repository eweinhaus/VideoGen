"use client"

export type PipelineStage = 
  | "audio_parser"
  | "scene_planner"
  | "reference_generator"
  | "prompt_generator"
  | "video_generator"
  | "composer"

interface StepSelectorProps {
  value: PipelineStage | null
  onChange: (stage: PipelineStage | null) => void
  disabled?: boolean
}

const STAGE_OPTIONS: Array<{ value: PipelineStage; label: string; description: string }> = [
  {
    value: "audio_parser",
    label: "Audio Parser",
    description: "Stop after audio analysis (10% progress)"
  },
  {
    value: "scene_planner",
    label: "Scene Planner",
    description: "Stop after scene planning (20% progress)"
  },
  {
    value: "reference_generator",
    label: "Reference Generator",
    description: "Stop after reference image generation (30% progress)"
  },
  {
    value: "prompt_generator",
    label: "Prompt Generator",
    description: "Stop after prompt generation (40% progress)"
  },
  {
    value: "video_generator",
    label: "Video Generator",
    description: "Stop after video clip generation (85% progress)"
  },
  {
    value: "composer",
    label: "Composer",
    description: "Complete full pipeline (100% progress)"
  }
]

const isProduction = process.env.NODE_ENV === "production"

export function StepSelector({ value, onChange, disabled }: StepSelectorProps) {
  // Hide in production - always use full pipeline (composer)
  if (isProduction) {
    return null
  }

  return (
    <div className="space-y-3">
      <label className="text-sm font-medium">Stop After Stage (Testing Only)</label>
      <p className="text-xs text-muted-foreground">
        Select which stage the pipeline should stop at. The orchestrator will run up to and including the selected stage, then pause gracefully.
      </p>
      <div className="space-y-2 border rounded-md p-4 bg-muted/30">
        {STAGE_OPTIONS.map((option) => (
          <label
            key={option.value}
            className="flex items-start space-x-3 p-2 rounded-md hover:bg-muted/50 cursor-pointer"
          >
            <input
              type="radio"
              name="stop_at_stage"
              value={option.value}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              disabled={disabled}
              className="mt-1 h-4 w-4 text-primary focus:ring-primary"
            />
            <div className="flex-1">
              <div className="text-sm font-medium">{option.label}</div>
              <div className="text-xs text-muted-foreground">{option.description}</div>
            </div>
          </label>
        ))}
      </div>
    </div>
  )
}

