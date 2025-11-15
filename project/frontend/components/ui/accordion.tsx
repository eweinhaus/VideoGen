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
  const [isOpen, setIsOpen] = React.useState(defaultOpen)

  return (
    <div className={cn("border rounded-lg overflow-hidden", className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 text-left hover:bg-muted/50 transition-colors border-b"
      >
        <span className="font-semibold text-lg">{title}</span>
        <ChevronDown
          className={cn(
            "h-5 w-5 text-muted-foreground transition-transform duration-200",
            isOpen && "transform rotate-180"
          )}
        />
      </button>
      <div
        className={cn(
          "transition-all duration-200 ease-in-out overflow-hidden",
          isOpen ? "max-h-[5000px] opacity-100" : "max-h-0 opacity-0"
        )}
      >
        <div className="p-4 pt-[10px]">
          {children}
        </div>
      </div>
    </div>
  )
}
