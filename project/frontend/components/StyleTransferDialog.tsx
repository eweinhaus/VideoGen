"use client"

import { useState } from "react"
import { transferStyle } from "@/lib/api"
import { StyleTransferOptions } from "@/types/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Checkbox } from "@/components/ui/checkbox"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { APIError } from "@/types/api"
import { LoadingSpinner } from "@/components/LoadingSpinner"

interface StyleTransferDialogProps {
  jobId: string
  sourceClipIndex: number
  targetClipIndex: number
  totalClips: number
  onTransferComplete?: () => void
  onCancel: () => void
}

export function StyleTransferDialog({
  jobId,
  sourceClipIndex,
  targetClipIndex,
  totalClips,
  onTransferComplete,
  onCancel,
}: StyleTransferDialogProps) {
  const [transferOptions, setTransferOptions] = useState<StyleTransferOptions>({
    color_palette: true,
    lighting: true,
    mood: true,
    preserve_characters: true,
  })
  const [additionalInstruction, setAdditionalInstruction] = useState("")
  const [isTransferring, setIsTransferring] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleTransfer = async () => {
    if (sourceClipIndex === targetClipIndex) {
      setError("Source and target clips must be different")
      return
    }

    setIsTransferring(true)
    setError(null)

    try {
      await transferStyle(
        jobId,
        sourceClipIndex,
        targetClipIndex,
        transferOptions,
        additionalInstruction.trim() || undefined
      )

      onTransferComplete?.()
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError("Failed to transfer style. Please try again.")
      }
      setIsTransferring(false)
    }
  }

  return (
    <Card className="w-full max-w-2xl">
      <CardHeader>
        <CardTitle>Apply Style from Clip {sourceClipIndex + 1} to Clip {targetClipIndex + 1}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <Alert>
          <AlertDescription>
            Select which style elements to transfer from clip {sourceClipIndex + 1} to clip {targetClipIndex + 1}.
          </AlertDescription>
        </Alert>

        <div className="space-y-3">
          <div className="flex items-center space-x-2">
            <Checkbox
              id="color_palette"
              checked={transferOptions.color_palette ?? true}
              onChange={(e) =>
                setTransferOptions({ ...transferOptions, color_palette: e.target.checked })
              }
            />
            <Label htmlFor="color_palette" className="cursor-pointer">
              Color Palette
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="lighting"
              checked={transferOptions.lighting ?? true}
              onChange={(e) =>
                setTransferOptions({ ...transferOptions, lighting: e.target.checked })
              }
            />
            <Label htmlFor="lighting" className="cursor-pointer">
              Lighting Style
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="mood"
              checked={transferOptions.mood ?? true}
              onChange={(e) =>
                setTransferOptions({ ...transferOptions, mood: e.target.checked })
              }
            />
            <Label htmlFor="mood" className="cursor-pointer">
              Mood/Atmosphere
            </Label>
          </div>

          <div className="flex items-center space-x-2">
            <Checkbox
              id="preserve_characters"
              checked={transferOptions.preserve_characters ?? true}
              onChange={(e) =>
                setTransferOptions({ ...transferOptions, preserve_characters: e.target.checked })
              }
            />
            <Label htmlFor="preserve_characters" className="cursor-pointer">
              Preserve Characters
            </Label>
          </div>
        </div>

        <div className="space-y-2">
          <Label htmlFor="additional_instruction">Additional Instruction (Optional)</Label>
          <Textarea
            id="additional_instruction"
            placeholder="e.g., 'make it more dramatic' or 'add more motion'"
            value={additionalInstruction}
            onChange={(e) => setAdditionalInstruction(e.target.value)}
            rows={2}
          />
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex justify-end space-x-2">
          <Button variant="outline" onClick={onCancel} disabled={isTransferring}>
            Cancel
          </Button>
          <Button onClick={handleTransfer} disabled={isTransferring}>
            {isTransferring ? (
              <>
                <LoadingSpinner className="mr-2 h-4 w-4" />
                Transferring...
              </>
            ) : (
              "Transfer Style"
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

