"use client"

import { useEffect, useState } from "react"
import { jobStore } from "@/stores/jobStore"
import { authStore } from "@/stores/authStore"

export function useJob(jobId?: string) {
  const { currentJob, isLoading, error, fetchJob, updateJob } = jobStore()
  const { token, isLoading: authLoading } = authStore()
  const [hasAttemptedFetch, setHasAttemptedFetch] = useState(false)

  useEffect(() => {
    // Wait for auth to be ready before fetching job
    if (jobId && !authLoading) {
      // Check if we already have this job cached
      const cachedJob = currentJob?.id === jobId ? currentJob : null
      
      if (!hasAttemptedFetch) {
        setHasAttemptedFetch(true)
        console.log("✅ useJob: Auth ready, fetching job", { jobId, hasToken: !!token, hasCached: !!cachedJob })
        
        // Use longer timeout for initial fetch (30 seconds) to handle slow backend metadata reconstruction
        // Allow partial data so page can render with cached data
        fetchJob(jobId, { timeout: 30000, allowPartial: true }).catch((err) => {
          console.error("❌ useJob: Failed to fetch job", err)
          // Don't throw - allow page to render with cached data if available
        })
      }
    } else if (jobId && authLoading) {
      console.log("⏳ useJob: Waiting for auth to load...", { jobId })
    }
  }, [jobId, fetchJob, token, authLoading, hasAttemptedFetch, currentJob])

  // Reset hasAttemptedFetch when jobId changes
  useEffect(() => {
    setHasAttemptedFetch(false)
  }, [jobId])

  // If we have cached job data, don't block rendering even if isLoading is true
  // This allows the page to render with cached data while fetching updates
  const hasCachedData = currentJob?.id === jobId
  const shouldShowLoading = !hasCachedData && (isLoading || authLoading)

  return {
    job: currentJob,
    isLoading: shouldShowLoading, // Only show loading if we don't have cached data
    error,
    fetchJob,
    updateJob,
  }
}

