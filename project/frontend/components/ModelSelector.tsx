"use client"

export type VideoModel = 
  | "kling_v21"
  | "kling_v25_turbo"
  | "hailuo_23"
  | "wan_25_i2v"
  | "veo_31"

interface ModelSelectorProps {
  value: VideoModel
  onChange: (model: VideoModel) => void
  disabled?: boolean
}

const MODEL_OPTIONS: Array<{ value: VideoModel; label: string }> = [
  {
    value: "kling_v25_turbo",
    label: "Kling v2.5 Turbo"
  },
  {
    value: "kling_v21",
    label: "Kling v2.1"
  },
  {
    value: "hailuo_23",
    label: "Hailuo 2.3"
  },
  {
    value: "wan_25_i2v",
    label: "Wan 2.5 i2v"
  },
  {
    value: "veo_31",
    label: "Veo 3.1"
  }
]

export function ModelSelector({ value, onChange, disabled }: ModelSelectorProps) {
  return (
    <div className="space-y-2">
      <label htmlFor="video_model" className="text-sm font-medium">
        Model
      </label>
      <select
        id="video_model"
        value={value}
        onChange={(e) => onChange(e.target.value as VideoModel)}
        disabled={disabled}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {MODEL_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

