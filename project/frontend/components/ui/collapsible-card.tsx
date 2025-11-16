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
  const [isOpen, setIsOpen] = React.useState(defaultOpen)

  return (
    <Card className={cn("mt-6", className)}>
      <CardHeader 
        className="py-4 cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg leading-none">{title}</CardTitle>
            <ChevronDown
              className={cn(
              "h-4 w-4 transition-transform duration-200 text-muted-foreground",
                isOpen && "transform rotate-180"
              )}
            />
        </div>
      </CardHeader>
      {isOpen && <CardContent>{children}</CardContent>}
    </Card>
  )
}

