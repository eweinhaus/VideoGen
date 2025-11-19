"use client"

import { useState } from "react"
import { parseMultiClipInstruction } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Textarea } from "@/components/ui/textarea"
import { APIError } from "@/types/api"
import { LoadingSpinner } from "@/components/LoadingSpinner"

interface MultiClipInstructionInputProps {
  jobId: string
  totalClips: number
  onPreviewReady?: (preview: {
    target_clips: number[]
    per_clip_instructions: Array<{ clip_index: number; instruction: string }>
    estimated_cost: number
  }) => void
  onCancel: () => void
}

const EXAMPLE_INSTRUCTIONS = [
  "make all clips brighter",
  "make clips 2 and 4 darker",
  "make clips 1-3 more vibrant",
  "make the first 3 clips warmer",
  "make all clips except clip 2 more energetic",
  "make the chorus clips brighter",
]

export function MultiClipInstructionInput({
  jobId,
  totalClips,
  onPreviewReady,
  onCancel,
}: MultiClipInstructionInputProps) {
  const [instruction, setInstruction] = useState("")
  const [isParsing, setIsParsing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [preview, setPreview] = useState<{
    target_clips: number[]
    per_clip_instructions: Array<{ clip_index: number; instruction: string }>
    estimated_cost: number
    batch_discount_applied: boolean
  } | null>(null)

  const handleParse = async () => {
    if (!instruction.trim()) {
      setError("Please enter an instruction")
      return
    }

    setIsParsing(true)
    setError(null)
    setPreview(null)

    try {
      const response = await parseMultiClipInstruction(jobId, instruction.trim())
      setPreview({
        target_clips: response.target_clips,
        per_clip_instructions: response.per_clip_instructions,
        estimated_cost: response.estimated_cost,
        batch_discount_applied: response.batch_discount_applied,
      })
      onPreviewReady?.(response)
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError("Failed to parse instruction. Please try again.")
      }
    } finally {
      setIsParsing(false)
    }
  }

  const handleUseExample = (example: string) => {
    setInstruction(example)
    setError(null)
    setPreview(null)
  }

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle>Multi-Clip Instruction</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert>
          <AlertDescription>
            Enter an instruction to modify multiple clips at once. Examples: &quot;make all clips brighter&quot;, &quot;make clips 2 and 4 darker&quot;, &quot;make the first 3 clips warmer&quot;
          </AlertDescription>
        </Alert>

        <div className="space-y-2">
          <label htmlFor="instruction" className="text-sm font-medium">
            Instruction
          </label>
          <Textarea
            id="instruction"
            placeholder="e.g., make all clips brighter"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            rows={3}
          />
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium text-gray-700">Examples:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLE_INSTRUCTIONS.map((example, idx) => (
              <Button
                key={idx}
                variant="outline"
                size="sm"
                onClick={() => handleUseExample(example)}
                className="text-xs"
              >
                {example}
              </Button>
            ))}
          </div>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {preview && (
          <Card className="border-2 border-primary">
            <CardHeader>
              <CardTitle className="text-lg">Preview</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <p className="text-sm font-medium text-gray-700">
                  Target Clips: {preview.target_clips.length} clip{preview.target_clips.length !== 1 ? "s" : ""}
                </p>
                <p className="text-xs text-gray-500">
                  {preview.target_clips.map((idx) => `Clip ${idx + 1}`).join(", ")}
                </p>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-700">Estimated Cost</p>
                <p className="text-lg font-bold text-primary">
                  ${preview.estimated_cost.toFixed(2)}
                  {preview.batch_discount_applied && (
                    <span className="ml-2 text-xs text-green-600">(10% discount applied)</span>
                  )}
                </p>
              </div>
              <div className="max-h-48 overflow-y-auto space-y-2">
                {preview.per_clip_instructions.map((ci) => (
                  <div key={ci.clip_index} className="rounded-md bg-gray-50 p-2 text-sm">
                    <span className="font-medium">Clip {ci.clip_index + 1}:</span> {ci.instruction}
                  </div>
                ))}
              </div>
              <Alert>
                <AlertDescription>
                  Note: Batch regeneration is not yet implemented. This preview shows which clips would be modified.
                </AlertDescription>
              </Alert>
            </CardContent>
          </Card>
        )}

        <div className="flex justify-end space-x-2">
          <Button variant="outline" onClick={onCancel} disabled={isParsing}>
            Cancel
          </Button>
          <Button onClick={handleParse} disabled={isParsing || !instruction.trim()}>
            {isParsing ? (
              <>
                <LoadingSpinner className="mr-2 h-4 w-4" />
                Parsing...
              </>
            ) : (
              "Preview"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

