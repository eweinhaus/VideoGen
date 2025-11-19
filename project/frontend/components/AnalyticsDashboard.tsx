"use client"

import { useState, useEffect, useCallback } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { LoadingSpinner } from "@/components/LoadingSpinner"
import { Download, RefreshCw, TrendingUp, DollarSign, CheckCircle, XCircle } from "lucide-react"
import { getJobAnalytics, getUserAnalytics, exportJobAnalytics, JobAnalyticsResponse, UserAnalyticsResponse } from "@/lib/api"
import { APIError } from "@/types/api"
import { authStore } from "@/stores/authStore"

interface AnalyticsDashboardProps {
  jobId?: string
  userId?: string
}

export function AnalyticsDashboard({ jobId, userId }: AnalyticsDashboardProps) {
  const [jobAnalytics, setJobAnalytics] = useState<JobAnalyticsResponse | null>(null)
  const [userAnalytics, setUserAnalytics] = useState<UserAnalyticsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isExporting, setIsExporting] = useState(false)
  
  const loadAnalytics = useCallback(async () => {
    setLoading(true)
    setError(null)
    
    try {
      if (jobId) {
        const jobData = await getJobAnalytics(jobId)
        setJobAnalytics(jobData)
      }
      
      if (userId) {
        const userData = await getUserAnalytics(userId)
        setUserAnalytics(userData)
      } else {
        // Try to get user ID from auth store
        const currentUser = authStore.getState().user
        if (currentUser?.id) {
          const userData = await getUserAnalytics(currentUser.id)
          setUserAnalytics(userData)
        }
      }
    } catch (err) {
      if (err instanceof APIError) {
        setError(err.message)
      } else {
        setError("Failed to load analytics")
      }
      console.error("Failed to load analytics:", err)
    } finally {
      setLoading(false)
    }
  }, [jobId, userId])
  
  useEffect(() => {
    loadAnalytics()
  }, [loadAnalytics])
  
  const handleExport = async () => {
    if (!jobId) return
    
    setIsExporting(true)
    try {
      const blob = await exportJobAnalytics(jobId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `job_${jobId}_analytics_${new Date().toISOString().split("T")[0]}.csv`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error("Failed to export analytics:", err)
      setError("Failed to export analytics")
    } finally {
      setIsExporting(false)
    }
  }
  
  const generateInsights = (): string[] => {
    const insights: string[] = []
    
    if (jobAnalytics) {
      const avgIterations = jobAnalytics.total_regenerations / (jobId ? 1 : 1) // Simplified
      if (avgIterations > 2 && typeof avgIterations === "number") {
        insights.push(`You regenerate clips an average of ${avgIterations.toFixed(1)} times - consider using templates for faster results`)
      }
      
      if (jobAnalytics.success_rate > 0.9 && typeof jobAnalytics.success_rate === "number") {
        insights.push(`Your success rate is ${(jobAnalytics.success_rate * 100).toFixed(0)}% - great job!`)
      }
      
      if (jobAnalytics.most_common_modifications.length > 0) {
        const mostCommon = jobAnalytics.most_common_modifications[0]
        insights.push(`Most common modification: "${mostCommon.instruction}" - consider using the "${mostCommon.instruction}" template`)
      }
    }
    
    if (userAnalytics) {
      if (userAnalytics.average_iterations_per_clip > 2 && typeof userAnalytics.average_iterations_per_clip === "number") {
        insights.push(`You regenerate clips an average of ${userAnalytics.average_iterations_per_clip.toFixed(1)} times per clip - templates can help speed this up`)
      }
      
      if (userAnalytics.most_used_templates.length > 0) {
        const mostUsed = userAnalytics.most_used_templates[0]
        insights.push(`Your most used template is "${mostUsed.template_id}" - you're already using templates effectively!`)
      }
    }
    
    return insights
  }
  
  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <LoadingSpinner />
      </div>
    )
  }
  
  if (error) {
    return (
      <Alert variant="destructive">
        <AlertDescription>{error}</AlertDescription>
      </Alert>
    )
  }
  
  const insights = generateInsights()
  
  return (
    <div className="space-y-6">
      {/* Header with refresh and export */}
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold">Regeneration Analytics</h2>
        <div className="flex items-center gap-2">
          {jobId && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              disabled={isExporting}
            >
              <Download className="h-4 w-4 mr-2" />
              {isExporting ? "Exporting..." : "Export CSV"}
            </Button>
          )}
          <Button variant="outline" size="sm" onClick={loadAnalytics}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </Button>
        </div>
      </div>
      
      {/* Job Analytics */}
      {jobAnalytics && (
        <Card>
          <CardHeader>
            <CardTitle>This Job</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <div className="text-sm text-gray-500">Total Regenerations</div>
                <div className="text-2xl font-semibold">{jobAnalytics.total_regenerations}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Success Rate</div>
                <div className="text-2xl font-semibold flex items-center gap-1">
                  {typeof jobAnalytics.success_rate === "number" 
                    ? `${(jobAnalytics.success_rate * 100).toFixed(1)}%`
                    : "N/A"}
                  {typeof jobAnalytics.success_rate === "number" && jobAnalytics.success_rate > 0.8 ? (
                    <CheckCircle className="h-5 w-5 text-green-500" />
                  ) : typeof jobAnalytics.success_rate === "number" ? (
                    <XCircle className="h-5 w-5 text-yellow-500" />
                  ) : null}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Average Cost</div>
                <div className="text-2xl font-semibold flex items-center gap-1">
                  <DollarSign className="h-5 w-5" />
                  {typeof jobAnalytics.average_cost === "number" 
                    ? jobAnalytics.average_cost.toFixed(2)
                    : "N/A"}
                </div>
              </div>
              {jobAnalytics.average_time_seconds && (
                <div>
                  <div className="text-sm text-gray-500">Avg Time</div>
                  <div className="text-2xl font-semibold">
                    {Math.round(jobAnalytics.average_time_seconds)}s
                  </div>
                </div>
              )}
            </div>
            
            {jobAnalytics.most_common_modifications.length > 0 && (
              <div>
                <div className="text-sm font-medium mb-2">Most Common Modifications</div>
                <ul className="space-y-1">
                  {jobAnalytics.most_common_modifications.map((mod, idx) => (
                    <li key={idx} className="text-sm text-gray-600">
                      • &quot;{mod.instruction}&quot; ({mod.count} {mod.count === 1 ? "time" : "times"})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
      
      {/* User Analytics */}
      {userAnalytics && (
        <Card>
          <CardHeader>
            <CardTitle>Your Usage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <div className="text-sm text-gray-500">Total Regenerations</div>
                <div className="text-2xl font-semibold">{userAnalytics.total_regenerations}</div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Success Rate</div>
                <div className="text-2xl font-semibold">
                  {typeof userAnalytics.success_rate === "number"
                    ? `${(userAnalytics.success_rate * 100).toFixed(1)}%`
                    : "N/A"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Total Cost</div>
                <div className="text-2xl font-semibold flex items-center gap-1">
                  <DollarSign className="h-5 w-5" />
                  {typeof userAnalytics.total_cost === "number"
                    ? userAnalytics.total_cost.toFixed(2)
                    : "N/A"}
                </div>
              </div>
              <div>
                <div className="text-sm text-gray-500">Avg Iterations/Clip</div>
                <div className="text-2xl font-semibold">
                  {typeof userAnalytics.average_iterations_per_clip === "number"
                    ? userAnalytics.average_iterations_per_clip.toFixed(1)
                    : "N/A"}
                </div>
              </div>
            </div>
            
            {userAnalytics.most_used_templates.length > 0 && (
              <div>
                <div className="text-sm font-medium mb-2">Most Used Templates</div>
                <ul className="space-y-1">
                  {userAnalytics.most_used_templates.map((template, idx) => (
                    <li key={idx} className="text-sm text-gray-600">
                      • {template.template_id} ({template.count} {template.count === 1 ? "time" : "times"})
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
      
      {/* Insights */}
      {insights.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Insights</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {insights.map((insight, idx) => (
                <li key={idx} className="flex items-start gap-2 text-sm">
                  <TrendingUp className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" />
                  <span>{insight}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
      
      {/* Empty state */}
      {!jobAnalytics && !userAnalytics && (
        <Card>
          <CardContent className="py-8 text-center text-gray-500">
            No analytics data available yet. Analytics will appear after you regenerate clips.
          </CardContent>
        </Card>
      )}
    </div>
  )
}

