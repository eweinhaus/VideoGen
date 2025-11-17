"use client"

import * as React from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

interface AccordionItemProps {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
  className?: string
}

export function AccordionItem({
  title,
  children,
  defaultOpen = false,
  className,
}: AccordionItemProps) {
  const [isOpen, setIsOpen] = React.useState(false) // Always default to closed
  const contentRef = React.useRef<HTMLDivElement>(null)
  const measureRef = React.useRef<HTMLDivElement>(null)
  const [contentHeight, setContentHeight] = React.useState<number>(0)
  const prevIsOpenRef = React.useRef<boolean>(false)

  // Measure content height using hidden element
  const measureHeight = React.useCallback(() => {
    if (measureRef.current) {
      return measureRef.current.scrollHeight
    }
    return 0
  }, [])

  // Handle initial mount - only set to open if defaultOpen is true
  React.useEffect(() => {
    if (defaultOpen) {
      setIsOpen(true)
      prevIsOpenRef.current = true
      // Set initial height after mount
      requestAnimationFrame(() => {
        const height = measureHeight()
        if (height > 0) {
          setContentHeight(height)
        }
      })
    }
  }, [defaultOpen, measureHeight])

  // Handle opening/closing animation
  React.useEffect(() => {
    // Only animate when isOpen state actually changes
    if (isOpen === prevIsOpenRef.current) return
    
    const wasOpen = prevIsOpenRef.current
    prevIsOpenRef.current = isOpen

    if (isOpen) {
      // Opening: Measure height and animate to it
      const height = measureHeight()
      if (height > 0) {
        // Set to 0 first to ensure we start from closed state
        setContentHeight(0)
        // Then animate to full height in next frame
        requestAnimationFrame(() => {
          setContentHeight(height)
        })
      }
    } else if (wasOpen) {
      // Closing: Get current height from measureRef (which has full height), then animate to 0
      const currentHeight = measureHeight()
      if (currentHeight > 0) {
        setContentHeight(currentHeight)
        // Use double RAF to ensure smooth transition
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setContentHeight(0)
          })
        })
      }
    }
  }, [isOpen, measureHeight])

  // Update height when children change (if open)
  React.useEffect(() => {
    if (isOpen) {
      const height = measureHeight()
      if (height > 0) {
        setContentHeight(height)
      }
    }
  }, [children, isOpen, measureHeight])

  return (
    <div className={cn("border rounded-lg overflow-hidden relative", className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-muted/50 transition-colors border-b"
      >
        <span className="font-semibold text-lg">{title}</span>
        <ChevronDown
          className={cn(
            "h-5 w-5 text-muted-foreground transition-transform duration-300 ease-in-out",
            isOpen && "transform rotate-180"
          )}
        />
      </button>
      {/* Hidden element for measuring content height - positioned off-screen */}
      <div
        ref={measureRef}
        className="absolute opacity-0 pointer-events-none"
        style={{ 
          visibility: 'hidden',
          position: 'absolute',
          top: '-9999px',
          left: '-9999px',
          width: '100%'
        }}
      >
        <div className="pt-[15px] px-4 pb-4">
          {children}
        </div>
      </div>
      {/* Animated content wrapper */}
      <div
        className="overflow-hidden transition-all duration-300 ease-in-out"
        style={{
          height: `${contentHeight}px`,
        }}
      >
        <div ref={contentRef} className="pt-[15px] px-4 pb-4">
          {children}
        </div>
      </div>
    </div>
  )
}
