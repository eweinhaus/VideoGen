"use client"

import { useState, useEffect } from "react"
import { ChevronUp, ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

interface FloatingChatProps {
  children: React.ReactNode
  title: string
  jobId: string
  defaultMinimized?: boolean
  position?: "bottom-left" | "bottom-right"
  maxWidth?: string
  maxHeight?: string
}

export function FloatingChat({
  children,
  title,
  jobId,
  defaultMinimized = false,
  position = "bottom-left",
  maxWidth = "400px",
  maxHeight = "600px",
}: FloatingChatProps) {
  const minimizeStateKey = `clip_chat_minimized_${jobId}`
  
  // Load minimized state from localStorage, default to not minimized (open)
  const [isMinimized, setIsMinimized] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem(minimizeStateKey)
      if (saved !== null) {
        return JSON.parse(saved)
      }
    } catch (err) {
      // Default to not minimized (open) on error
    }
    return defaultMinimized
  })

  // Save minimize state to localStorage
  const handleToggleMinimize = () => {
    const newState = !isMinimized
    setIsMinimized(newState)
    try {
      localStorage.setItem(minimizeStateKey, JSON.stringify(newState))
    } catch (err) {
      console.error("Failed to save minimize state:", err)
    }
  }

  return (
    <div
      className={cn(
        "fixed z-50 transition-all duration-300 ease-in-out shadow-lg border bg-card text-card-foreground",
        // Mobile: bottom sheet (full width, rounded top corners)
        "bottom-0 left-0 w-full max-w-full rounded-t-lg rounded-b-none",
        // Desktop: positioned on left with spacing, behavior depends on minimized state
        isMinimized 
          ? "md:bottom-4 md:left-4 md:top-auto md:w-[400px] md:max-w-[400px] md:rounded-lg md:h-[60px]"
          : "md:left-4 md:top-0 md:bottom-0 md:w-[400px] md:max-w-[400px] md:rounded-lg md:h-full"
      )}
      style={{
        maxWidth: maxWidth,
        height: isMinimized ? "60px" : "auto",
        maxHeight: isMinimized ? "60px" : undefined,
      }}
    >
      {/* Header */}
      <div
        className={cn(
          "flex items-center justify-between p-3 border-b bg-card",
          "cursor-pointer"
        )}
        onClick={handleToggleMinimize}
      >
        <h3 className="text-sm font-semibold">{title}</h3>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 w-6 p-0"
          onClick={(e) => {
            e.stopPropagation()
            handleToggleMinimize()
          }}
        >
          {isMinimized ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </Button>
      </div>

      {/* Content - animated collapse */}
      <div
        className={cn(
          "overflow-hidden transition-all duration-300 ease-in-out",
          isMinimized ? "opacity-0 max-h-0" : "opacity-100"
        )}
        style={{
          maxHeight: isMinimized ? "0" : undefined,
          height: isMinimized ? "0" : "calc(100% - 60px)",
          overflow: isMinimized ? "hidden" : "auto",
        }}
      >
        <div className="flex flex-col h-full">
          {children}
        </div>
      </div>
    </div>
  )
}

