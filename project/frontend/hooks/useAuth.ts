"use client"

import { useEffect, useRef } from "react"
import { authStore } from "@/stores/authStore"
import { supabase } from "@/lib/supabase"

export function useAuth() {
  const { user, token, isLoading, error, login, logout, register, checkAuth } =
    authStore()
  const hasInitialized = useRef(false)

  useEffect(() => {
    // Only check auth once on mount
    if (!hasInitialized.current) {
      checkAuth()
      hasInitialized.current = true
    }

    // Listen for auth state changes (e.g., token refresh, sign out)
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((event, session) => {
      console.log("Auth state changed:", event, session?.user?.email)
      if (session) {
        authStore.setState({
          user: session.user,
          token: session.access_token,
          isLoading: false,
        })
      } else {
        authStore.setState({
          user: null,
          token: null,
          isLoading: false,
        })
      }
    })

    return () => {
      subscription.unsubscribe()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []) // Empty deps - only run once on mount

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
