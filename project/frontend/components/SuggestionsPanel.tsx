"use client"

import { useState, useEffect, useCallback } from "react"
import { getSuggestions, applySuggestion } from "@/lib/api"
import { Suggestion } from "@/types/api"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { APIError } from "@/types/api"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { cn } from "@/lib/utils"

interface SuggestionsPanelProps {
  jobId: string
  clipIndex: number
  onSuggestionApplied?: () => void
}

export function SuggestionsPanel({
  jobId,
  clipIndex,
  onSuggestionApplied,
}: SuggestionsPanelProps) {
  const [suggestions, setSuggestions] = useState<Suggestion[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [isApplying, setIsApplying] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [cached, setCached] = useState(false)
  const [rateLimitCountdown, setRateLimitCountdown] = useState<number | null>(null)

  const loadSuggestions = useCallback(async () => {
    setIsLoading(true)
    setError(null)

    try {
      const response = await getSuggestions(jobId, clipIndex)
      setSuggestions(response.suggestions)
      setCached(response.cached)
    } catch (err) {
      if (err instanceof APIError) {
        if (err.statusCode === 429) {
          // Rate limit exceeded
          const retryAfter = parseInt(err.message.match(/\d+/)?.[0] || "60")
          setRateLimitCountdown(retryAfter)
          setError(`Rate limit exceeded. Please try again in ${retryAfter} seconds.`)
        } else {
          setError(err.message)
        }
      } else {
        setError("Failed to load suggestions. Please try again.")
      }
    } finally {
      setIsLoading(false)
    }
  }, [jobId, clipIndex])

  useEffect(() => {
    loadSuggestions()
  }, [loadSuggestions])

  // Countdown timer for rate limit
  useEffect(() => {
    if (rateLimitCountdown !== null && rateLimitCountdown > 0) {
      const timer = setTimeout(() => {
        setRateLimitCountdown(rateLimitCountdown - 1)
      }, 1000)
      return () => clearTimeout(timer)
    } else if (rateLimitCountdown === 0) {
      setRateLimitCountdown(null)
      setError(null)
    }
  }, [rateLimitCountdown])

  const handleApplySuggestion = async (suggestion: Suggestion, index: number) => {
    setIsApplying(`${index}`)
    setError(null)

    try {
      await applySuggestion(jobId, clipIndex, `${index}`)
      onSuggestionApplied?.()
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError("Failed to apply suggestion. Please try again.")
      }
      setIsApplying(null)
    }
  }

  const getTypeColor = (type: string) => {
    switch (type) {
      case "quality":
        return "bg-blue-100 text-blue-800"
      case "consistency":
        return "bg-green-100 text-green-800"
      case "creative":
        return "bg-purple-100 text-purple-800"
      default:
        return "bg-gray-100 text-gray-800"
    }
  }

  const groupedSuggestions = suggestions.reduce((acc, suggestion, index) => {
    if (!acc[suggestion.type]) {
      acc[suggestion.type] = []
    }
    acc[suggestion.type].push({ ...suggestion, index })
    return acc
  }, {} as Record<string, Array<Suggestion & { index: number }>>)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>AI Suggestions for Clip {clipIndex + 1}</CardTitle>
          <Button
            variant="outline"
            size="sm"
            onClick={loadSuggestions}
            disabled={isLoading || rateLimitCountdown !== null}
          >
            {isLoading ? (
              <>
                <LoadingSpinner className="mr-2 h-4 w-4" />
                Loading...
              </>
            ) : (
              "Refresh"
            )}
          </Button>
        </div>
        {cached && (
          <p className="text-sm text-gray-500">Showing cached suggestions</p>
        )}
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <Alert variant={rateLimitCountdown ? undefined : "destructive"}>
            <AlertDescription>
              {error}
              {rateLimitCountdown !== null && (
                <span className="ml-2 font-mono">
                  ({rateLimitCountdown}s)
                </span>
              )}
            </AlertDescription>
          </Alert>
        )}

        {isLoading && suggestions.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <LoadingSpinner className="h-8 w-8" />
          </div>
        ) : suggestions.length === 0 ? (
          <Alert>
            <AlertDescription>
              No suggestions available. Try refreshing or check back later.
            </AlertDescription>
          </Alert>
        ) : (
          <div className="space-y-6">
            {Object.entries(groupedSuggestions).map(([type, typeSuggestions]) => (
              <div key={type} className="space-y-2">
                <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-700">
                  {type}
                </h3>
                <div className="space-y-3">
                  {typeSuggestions.map((suggestion) => (
                    <Card key={suggestion.index} className="border">
                      <CardContent className="pt-4">
                        <div className="space-y-3">
                          <div className="flex items-start justify-between">
                            <p className="text-sm text-gray-700">
                              {suggestion.description}
                            </p>
                            <span
                              className={cn(
                                "ml-2 rounded-full px-2 py-1 text-xs font-medium",
                                getTypeColor(suggestion.type)
                              )}
                            >
                              {(suggestion.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <div className="rounded-md bg-gray-50 p-2">
                            <p className="text-xs text-gray-600">
                              Example: &quot;{suggestion.example_instruction}&quot;
                            </p>
                          </div>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleApplySuggestion(suggestion, suggestion.index)}
                            disabled={isApplying === `${suggestion.index}`}
                            className="w-full"
                          >
                            {isApplying === `${suggestion.index}` ? (
                              <>
                                <LoadingSpinner className="mr-2 h-4 w-4" />
                                Applying...
                              </>
                            ) : (
                              "Apply This Suggestion"
                            )}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

