"use client"

import { useEffect } from "react"
import { jobStore } from "@/stores/jobStore"

export function useJob(jobId?: string) {
  const { currentJob, isLoading, error, fetchJob, updateJob } = jobStore()

  useEffect(() => {
    if (jobId) {
      fetchJob(jobId)
    }
  }, [jobId, fetchJob])

  return {
    job: currentJob,
    isLoading,
    error,
    fetchJob,
    updateJob,
  }
}

