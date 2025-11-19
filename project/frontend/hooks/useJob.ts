"use client"

import { useEffect } from "react"
import { jobStore } from "@/stores/jobStore"
import { authStore } from "@/stores/authStore"

export function useJob(jobId?: string) {
  const { currentJob, isLoading, error, fetchJob, updateJob } = jobStore()
  const { token, isLoading: authLoading } = authStore()

  useEffect(() => {
    // Wait for auth to be ready before fetching job
    if (jobId && !authLoading) {
      fetchJob(jobId).catch((err) => {
        console.error("❌ useJob: Failed to fetch job", err)
      })
    }
  }, [jobId, fetchJob, token, authLoading])

  return {
    job: currentJob,
    isLoading: isLoading || authLoading, // Show loading if either job or auth is loading
    error,
    fetchJob,
    updateJob,
  }
}

