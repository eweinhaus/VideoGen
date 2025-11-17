"use client"

import { useMemo, useEffect } from "react"
import type { VideoModel } from "./ModelSelector"

// Hardcoded aspect ratios matching backend configuration
const MODEL_ASPECT_RATIOS: Record<VideoModel, { ratios: string[]; default: string }> = {
  kling_v21: {
    ratios: ["16:9"],
    default: "16:9"
  },
  kling_v25_turbo: {
    ratios: ["16:9", "9:16", "1:1", "4:3", "3:4"],
    default: "16:9"
  },
  hailuo_23: {
    ratios: ["16:9", "9:16", "1:1"],
    default: "16:9"
  },
  wan_25_i2v: {
    ratios: ["16:9", "1:1", "9:16"],
    default: "16:9"
  },
  veo_31: {
    ratios: ["16:9", "9:16"],
    default: "16:9"
  }
}

interface AspectRatioSelectorProps {
  value: string
  onChange: (aspectRatio: string) => void
  modelKey: VideoModel
  disabled?: boolean
}

export function AspectRatioSelector({
  value,
  onChange,
  modelKey,
  disabled
}: AspectRatioSelectorProps) {
  const modelConfig = useMemo(() => {
    return MODEL_ASPECT_RATIOS[modelKey] || MODEL_ASPECT_RATIOS.kling_v21
  }, [modelKey])
  
  const aspectRatios = modelConfig.ratios
  
  // Reset to default when model changes, or validate current value
  useEffect(() => {
    if (!aspectRatios.includes(value)) {
      // Current value is not valid for this model, reset to default
      onChange(modelConfig.default)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelKey]) // Only depend on modelKey, onChange is stable from Zustand
  
  return (
    <div className="space-y-2">
      <label htmlFor="aspect_ratio" className="text-sm font-medium">
        Aspect Ratio
      </label>
      <select
        id="aspect_ratio"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {aspectRatios.map((ratio) => (
          <option key={ratio} value={ratio}>
            {ratio}
          </option>
        ))}
      </select>
    </div>
  )
}

