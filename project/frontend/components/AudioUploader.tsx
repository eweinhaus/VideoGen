"use client"

import { useState, useRef } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Upload, X, FileAudio } from "lucide-react"
import { formatBytes } from "@/lib/utils"
import { cn } from "@/lib/utils"

interface AudioUploaderProps {
  value: File | null
  onChange: (file: File | null) => void
  error?: string
  disabled?: boolean
}

export function AudioUploader({
  value,
  onChange,
  error,
  disabled,
}: AudioUploaderProps) {
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    if (!disabled) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled) return

    const file = e.dataTransfer.files[0]
    if (file) {
      onChange(file)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      onChange(file)
    }
  }

  const handleClick = () => {
    if (!disabled) {
      fileInputRef.current?.click()
    }
  }

  const handleRemove = () => {
    onChange(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  return (
    <div className="w-full">
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
            accept="audio/*"
            onChange={handleFileSelect}
            className="hidden"
            disabled={disabled}
          />

          {value ? (
            <div className="flex w-full items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <FileAudio className="h-8 w-8 text-primary" />
                <div className="flex flex-col">
                  <p className="font-medium">{value.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {formatBytes(value.size)} • {value.type.split("/")[1]?.toUpperCase() || "AUDIO"}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={(e) => {
                  e.stopPropagation()
                  handleRemove()
                }}
                disabled={disabled}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-2 text-center">
              <Upload
                className={cn(
                  "h-12 w-12",
                  isDragging ? "text-primary" : "text-muted-foreground"
                )}
              />
              <div>
                <p className="font-medium">
                  {isDragging ? "Drop here" : "Drag and drop audio file"}
                </p>
                <p className="text-sm text-muted-foreground">
                  or click to browse
                </p>
              </div>
              <p className="text-xs text-muted-foreground">
                MP3, WAV, or FLAC (max 10MB)
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive" className="mt-2">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {disabled && !value && (
        <p className="mt-2 text-sm text-muted-foreground">Upload disabled</p>
      )}
    </div>
  )
}

