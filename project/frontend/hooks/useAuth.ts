"use client"

import { useEffect } from "react"
import { authStore } from "@/stores/authStore"

export function useAuth() {
  const { user, token, isLoading, error, login, logout, register, checkAuth } =
    authStore()

  useEffect(() => {
    // Check auth state on mount
    checkAuth()
  }, [checkAuth])

  return {
    user,
    token,
    isLoading,
    error,
    login,
    logout,
    register,
    isAuthenticated: !!user && !!token,
  }
}

