"use client"

import { useState, useRef } from "react"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Upload, X, Image as ImageIcon } from "lucide-react"
import { formatBytes } from "@/lib/utils"
import { cn } from "@/lib/utils"

export interface ReferenceImageUpload {
  id: string
  file: File
  type: "character" | "scene" | "object"
  title: string
  previewUrl: string
  error?: string
}

interface ReferenceImageUploaderProps {
  value: ReferenceImageUpload[]
  onChange: (uploads: ReferenceImageUpload[]) => void
  disabled?: boolean
  maxImages?: number
}

const MAX_FILE_SIZE = 20 * 1024 * 1024 // 20MB
const VALID_IMAGE_TYPES = ["image/png", "image/jpeg", "image/jpg"]

export function ReferenceImageUploader({
  value,
  onChange,
  disabled,
  maxImages = 2,
}: ReferenceImageUploaderProps) {
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    if (!disabled && value.length < maxImages) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (disabled || value.length >= maxImages) return

    const files = Array.from(e.dataTransfer.files).filter(
      (file) => file.type.startsWith("image/")
    )
    
    if (files.length > 0) {
      handleFiles(files)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      handleFiles(Array.from(files))
    }
  }

  const handleFiles = (files: File[]) => {
    const remainingSlots = maxImages - value.length
    const filesToAdd = files.slice(0, remainingSlots)
    
    const newUploads: ReferenceImageUpload[] = filesToAdd.map((file) => {
      // Validate file
      let error: string | undefined
      
      if (!VALID_IMAGE_TYPES.includes(file.type)) {
        error = "Invalid file format. Please upload PNG or JPEG"
      } else if (file.size > MAX_FILE_SIZE) {
        error = `File size must be less than ${formatBytes(MAX_FILE_SIZE)}`
      }
      
      const previewUrl = URL.createObjectURL(file)
      
      return {
        id: `${Date.now()}-${Math.random()}`,
        file,
        type: "character" as const,
        title: "",
        previewUrl,
        error,
      }
    })
    
    onChange([...value, ...newUploads])
    
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = ""
    }
  }

  const handleClick = () => {
    if (!disabled && value.length < maxImages) {
      fileInputRef.current?.click()
    }
  }

  const handleRemove = (id: string) => {
    const upload = value.find((u) => u.id === id)
    if (upload) {
      URL.revokeObjectURL(upload.previewUrl)
    }
    onChange(value.filter((u) => u.id !== id))
  }

  const handleTypeChange = (id: string, type: "character" | "scene" | "object") => {
    onChange(
      value.map((u) => (u.id === id ? { ...u, type } : u))
    )
  }

  const handleTitleChange = (id: string, title: string) => {
    onChange(
      value.map((u) => (u.id === id ? { ...u, title } : u))
    )
  }

  const canAddMore = value.length < maxImages

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between">
        <Label>Reference Images (Optional)</Label>
        <span className="text-sm text-muted-foreground">
          {value.length} / {maxImages}
        </span>
      </div>

      {/* Existing uploads */}
      {value.map((upload) => (
        <Card key={upload.id} className="overflow-hidden">
          <CardContent className="p-4">
            <div className="flex gap-4">
              {/* Preview */}
              <div className="relative h-24 w-24 flex-shrink-0 overflow-hidden rounded-md border">
                <img
                  src={upload.previewUrl}
                  alt={upload.file.name}
                  className="h-full w-full object-cover"
                />
              </div>

              {/* Details */}
              <div className="flex-1 space-y-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="font-medium text-sm">{upload.file.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {formatBytes(upload.file.size)}
                    </p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => handleRemove(upload.id)}
                    disabled={disabled}
                    className="h-8 w-8"
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </div>

                {/* Type selector */}
                <div className="space-y-1">
                  <Label className="text-xs">Type</Label>
                  <div className="flex gap-2">
                    {(["character", "scene", "object"] as const).map((type) => (
                      <Button
                        key={type}
                        type="button"
                        variant={upload.type === type ? "default" : "outline"}
                        size="sm"
                        onClick={() => handleTypeChange(upload.id, type)}
                        disabled={disabled}
                        className="text-xs capitalize"
                      >
                        {type}
                      </Button>
                    ))}
                  </div>
                </div>

                {/* Title input */}
                <div className="space-y-1">
                  <Label className="text-xs">Title *</Label>
                  <Input
                    type="text"
                    placeholder="e.g., protagonist, Alice, city street"
                    value={upload.title}
                    onChange={(e) => handleTitleChange(upload.id, e.target.value)}
                    disabled={disabled}
                    className="h-8 text-sm"
                    maxLength={100}
                  />
                </div>

                {/* Error message */}
                {upload.error && (
                  <Alert variant="destructive" className="py-2">
                    <AlertDescription className="text-xs">
                      {upload.error}
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ))}

      {/* Upload zone */}
      {canAddMore && (
        <Card
          className={cn(
            "cursor-pointer transition-colors",
            isDragging && "border-primary bg-primary/5",
            disabled && "cursor-not-allowed opacity-50"
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
              multiple={maxImages > 1}
            />

            <div className="flex flex-col items-center gap-2 text-center">
              <ImageIcon
                className={cn(
                  "h-12 w-12",
                  isDragging ? "text-primary" : "text-muted-foreground"
                )}
              />
              <div>
                <p className="font-medium">
                  {isDragging ? "Drop here" : "Drag and drop image file"}
                </p>
                <p className="text-sm text-muted-foreground">
                  or click to browse
                </p>
              </div>
              <p className="text-xs text-muted-foreground">
                PNG or JPEG (max {formatBytes(MAX_FILE_SIZE)})
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      {!canAddMore && (
        <p className="text-sm text-muted-foreground text-center">
          Maximum {maxImages} reference images
        </p>
      )}
    </div>
  )
}

