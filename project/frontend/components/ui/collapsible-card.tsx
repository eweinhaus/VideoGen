"use client"

import * as React from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"

interface CollapsibleCardProps {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
  className?: string
}

export function CollapsibleCard({
  title,
  defaultOpen = false,
  children,
  className,
}: CollapsibleCardProps) {
  const [isOpen, setIsOpen] = React.useState(false) // Always default to closed
  const contentRef = React.useRef<HTMLDivElement>(null)
  const measureRef = React.useRef<HTMLDivElement>(null)
  const headerRef = React.useRef<HTMLDivElement>(null)
  const [contentHeight, setContentHeight] = React.useState<number>(0)

  // Handle initial mount - only set to open if defaultOpen is explicitly true
  React.useEffect(() => {
    if (defaultOpen) {
      setIsOpen(true)
    }
  }, [defaultOpen])

  // Measure content height using hidden element
  const measureHeight = React.useCallback(() => {
    if (measureRef.current) {
      return measureRef.current.scrollHeight
    }
    return 0
  }, [])

  // Handle opening/closing animation
  React.useEffect(() => {
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
    } else {
      // Closing: Get current height, then animate to 0
      const currentHeight = measureHeight()
      if (currentHeight > 0) {
        setContentHeight(currentHeight)
        // Use double RAF to ensure smooth transition
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            setContentHeight(0)
          })
        })
      } else {
        setContentHeight(0)
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

  // Set initial height if defaultOpen is true
  React.useEffect(() => {
    if (defaultOpen && measureRef.current) {
      requestAnimationFrame(() => {
        const height = measureHeight()
        if (height > 0) {
          setContentHeight(height)
        }
      })
    }
  }, [defaultOpen, measureHeight])

  const handleToggle = () => {
    const wasOpen = isOpen
    const willOpen = !wasOpen
    
    // Only track position when opening (not closing)
    if (willOpen && headerRef.current) {
      // Get header position before opening
      const headerRect = headerRef.current.getBoundingClientRect()
      const headerViewportTop = headerRect.top
      
      // Toggle the state
      setIsOpen(willOpen)
      
      // After opening, scroll to keep header in same viewport position
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (headerRef.current) {
            const newHeaderRect = headerRef.current.getBoundingClientRect()
            const newHeaderViewportTop = newHeaderRect.top
            const difference = newHeaderViewportTop - headerViewportTop
            
            // Scroll to compensate for the difference to keep header in same viewport position
            if (Math.abs(difference) > 1) {
              window.scrollBy({
                top: -difference,
                behavior: 'auto'
              })
            }
          }
        })
      })
    } else {
      // Just toggle when closing
      setIsOpen(willOpen)
    }
  }

  return (
    <Card className={cn("mt-6 relative", className)}>
      <CardHeader 
        ref={headerRef}
        className="py-5 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={handleToggle}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-xl leading-none">{title}</CardTitle>
          <ChevronDown
            className={cn(
              "h-4 w-4 transition-transform duration-300 ease-in-out text-muted-foreground",
              isOpen && "transform rotate-180"
            )}
          />
        </div>
      </CardHeader>
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
        <div className="pt-[15px] px-6 pb-6">
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
        <div ref={contentRef} className="pt-[15px] px-6 pb-6">
          {children}
        </div>
      </div>
    </Card>
  )
}

