"use client"

import { useState, useEffect } from "react"

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

// Check if we're in production environment (client-side only)
// This function should only be called on the client side
const isProduction = (): boolean => {
  // Must be on client side to check
  if (typeof window === "undefined") {
    // On server side, assume production to prevent rendering
    return true
  }
  
  // Check NODE_ENV (set at build time)
  if (process.env.NODE_ENV === "production") {
    return true
  }
  
  // Check custom environment variable (can be set in Vercel)
  if (process.env.NEXT_PUBLIC_ENVIRONMENT === "production") {
    return true
  }
  
  // Check if explicitly disabled
  if (process.env.NEXT_PUBLIC_DISABLE_STOP_AT_STAGE === "true") {
    return true
  }
  
  // Check hostname
  // Hide on production domains (not localhost, not preview deployments)
  const hostname = window.location.hostname
  // Show component only on localhost or preview deployments
  // Preview deployments on Vercel have pattern: project-git-branch-username.vercel.app (contains multiple dashes)
  // Production on vercel.app: project.vercel.app (single subdomain)
  // Custom production domains: any other domain
  const isLocalhost = hostname === "localhost" || hostname.includes("127.0.0.1")
  const isPreviewDeployment = hostname.includes(".vercel.app") && 
                               (hostname.match(/-/g) || []).length >= 2 // Preview has multiple dashes
  
  // If not localhost and not a preview deployment, it's production - hide component
  if (!isLocalhost && !isPreviewDeployment) {
    return true
  }
  
  return false
}

export function StepSelector({ value, onChange, disabled }: StepSelectorProps) {
  // Use state to ensure we only check production status on client side
  const [shouldShow, setShouldShow] = useState(false)
  
  useEffect(() => {
    // Only show if NOT in production (client-side check)
    setShouldShow(!isProduction())
  }, [])
  
  // Hide in production - always use full pipeline (composer)
  if (!shouldShow) {
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

