"use client"

import { useMemo } from "react"

export type Template = "standard" | "lipsync"

interface TemplateOption {
  value: Template
  label: string
  description: string
  costNote?: string
}

const TEMPLATES: TemplateOption[] = [
  {
    value: "standard",
    label: "Standard Video",
    description: "Standard video generation without lip synchronization"
  },
  {
    value: "lipsync",
    label: "Lipsync",
    description: "Apply lip synchronization to video clips (adds ~$0.10 per clip)",
    costNote: "Adds ~$0.50-$0.75 per job"
  }
]

interface TemplateSelectorProps {
  value: Template
  onChange: (template: Template) => void
  disabled?: boolean
}

export function TemplateSelector({
  value,
  onChange,
  disabled
}: TemplateSelectorProps) {
  const selectedTemplate = useMemo(() => {
    return TEMPLATES.find(t => t.value === value) || TEMPLATES[0]
  }, [value])

  return (
    <div className="space-y-2">
      <label htmlFor="template" className="text-sm font-medium">
        Template
      </label>
      <select
        id="template"
        value={value}
        onChange={(e) => onChange(e.target.value as Template)}
        disabled={disabled}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {TEMPLATES.map((template) => (
          <option key={template.value} value={template.value}>
            {template.label}
          </option>
        ))}
      </select>
      {selectedTemplate.description && (
        <p className="text-xs text-muted-foreground">
          {selectedTemplate.description}
          {selectedTemplate.costNote && (
            <span className="ml-1 font-medium text-foreground">
              {selectedTemplate.costNote}
            </span>
          )}
        </p>
      )}
    </div>
  )
}

