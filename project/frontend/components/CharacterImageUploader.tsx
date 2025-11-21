"use client"

import { useState, useRef } from "react"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Upload, X, Image as ImageIcon, Plus } from "lucide-react"
import { formatBytes } from "@/lib/utils"
import { cn } from "@/lib/utils"

export interface CharacterImage {
  file: File
  preview?: string
}

interface CharacterImageUploaderProps {
  value: CharacterImage | null
  onChange: (image: CharacterImage | null) => void
  error?: string
  disabled?: boolean
}

export function CharacterImageUploader({
  value = null,
  onChange,
  error,
  disabled = false,
}: CharacterImageUploaderProps) {
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    if (!disabled && !value) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled || value) return

    const file = Array.from(e.dataTransfer.files).find(
      (file) => file.type.startsWith("image/")
    )
    if (file) {
      handleFile(file)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      handleFile(file)
    }
    // Reset input so same file can be selected again
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleFile = (file: File) => {
    // Validate file
    if (!file.type.match(/^image\/(png|jpeg|jpg)$/i)) {
      throw new Error(
        `Invalid file type: ${file.name}. Only PNG and JPEG images are allowed.`
      )
    }

    if (file.size > 5 * 1024 * 1024) {
      throw new Error(
        `File too large: ${file.name}. Maximum size is 5MB.`
      )
    }

    // Create preview
    const preview = URL.createObjectURL(file)

    onChange({
      file,
      preview,
    })
  }

  const handleClick = () => {
    if (!disabled && !value) {
      fileInputRef.current?.click()
    }
  }

  const handleRemove = () => {
    if (value?.preview) {
      URL.revokeObjectURL(value.preview)
    }
    onChange(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  return (
    <div className="w-full space-y-4">
      <div className="space-y-2">
        <Label>Main Character Reference Image (Optional)</Label>
        <p className="text-sm text-muted-foreground">
          Upload a reference image for the main character. This will replace the
          auto-generated main character image. All other characters will be automatically generated.
        </p>
      </div>

      {/* Existing image */}
      {value && (
        <Card className="relative">
          <CardContent className="p-4">
            <div className="space-y-3">
              {/* Image preview */}
              <div className="relative aspect-square w-full overflow-hidden rounded-md bg-muted">
                {value.preview ? (
                  <img
                    src={value.preview}
                    alt="Main character reference"
                    className="h-full w-full object-cover"
                  />
                ) : (
                  <div className="flex h-full items-center justify-center">
                    <ImageIcon className="h-12 w-12 text-muted-foreground" />
                  </div>
                )}
                <Button
                  type="button"
                  variant="destructive"
                  size="icon"
                  className="absolute right-2 top-2 h-6 w-6"
                  onClick={handleRemove}
                  disabled={disabled}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>

              {/* File info */}
              <div className="text-xs text-muted-foreground">
                <p>{value.file.name}</p>
                <p>{formatBytes(value.file.size)}</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Upload area */}
      {!value && (
        <Card
          className={cn(
            "cursor-pointer transition-colors",
            isDragging && "border-primary bg-primary/5",
            disabled && "cursor-not-allowed opacity-50",
            error && "border-destructive"
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={handleClick}
        >
          <CardContent className="flex flex-col items-center justify-center p-8">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/jpg"
              onChange={handleFileSelect}
              className="hidden"
              disabled={disabled}
            />

            <div className="flex flex-col items-center gap-2 text-center">
              <Upload
                className={cn(
                  "h-12 w-12",
                  isDragging ? "text-primary" : "text-muted-foreground"
                )}
              />
              <div>
                <p className="font-medium">
                  {isDragging ? "Drop image here" : "Upload main character reference image"}
                </p>
                <p className="text-sm text-muted-foreground">
                  or click to browse
                </p>
              </div>
              <p className="text-xs text-muted-foreground">
                PNG or JPEG (max 5MB, min 512x512px)
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
    </div>
  )
}

