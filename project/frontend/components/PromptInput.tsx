"use client"

import { Textarea } from "@/components/ui/textarea"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { cn } from "@/lib/utils"

interface PromptInputProps {
  value: string
  onChange: (value: string) => void
  error?: string
  disabled?: boolean
}

export function PromptInput({
  value,
  onChange,
  error,
  disabled,
}: PromptInputProps) {
  const length = value.length
  const isValid = length >= 50 && length <= 500
  const isTooShort = length > 0 && length < 50
  const isTooLong = length > 500

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e.target.value)
  }

  return (
    <div className="w-full space-y-2">
      <div className="relative">
        <Textarea
          value={value}
          onChange={handleChange}
          placeholder="Describe your vision for the music video... (50-500 characters)"
          disabled={disabled}
          className={cn(
            "min-h-[120px] resize-y",
            isValid && !error && "border-green-500 focus-visible:ring-green-500",
            (isTooShort || isTooLong || error) && "border-destructive focus-visible:ring-destructive"
          )}
        />
        <div
          className={cn(
            "absolute bottom-2 right-2 text-xs",
            isValid && !error && "text-green-600",
            (isTooShort || isTooLong || error) && "text-destructive",
            !isValid && length === 0 && "text-muted-foreground"
          )}
        >
          {length} / 500
        </div>
      </div>

      {isTooShort && !error && (
        <Alert variant="destructive">
          <AlertDescription>
            Prompt must be at least 50 characters
          </AlertDescription>
        </Alert>
      )}

      {isTooLong && !error && (
        <Alert variant="destructive">
          <AlertDescription>
            Prompt must be at most 500 characters
          </AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {disabled && (
        <p className="text-sm text-muted-foreground">Input disabled</p>
      )}
    </div>
  )
}

