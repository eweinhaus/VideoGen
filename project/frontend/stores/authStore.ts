import { create } from "zustand"
import { supabase } from "@/lib/supabase"
import type { User } from "@supabase/supabase-js"

interface AuthState {
  user: User | null
  token: string | null
  isLoading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
  resetPassword: (email: string) => Promise<void>
  checkAuth: () => Promise<void>
}

export const authStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  isLoading: true, // Start as loading to prevent premature redirects
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null })
    try {
      const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password,
      })

      if (error) throw error

      const accessToken = data.session?.access_token || null
      set({
        user: data.user,
        token: accessToken,
        isLoading: false,
        error: null,
      })
    } catch (error: any) {
      set({
        isLoading: false,
        error: error.message || "Login failed",
      })
      throw error
    }
  },

  register: async (email: string, password: string) => {
    set({ isLoading: true, error: null })
    try {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
      })

      if (error) throw error

      // Auto-login after registration
      if (data.user && data.session) {
        const accessToken = data.session.access_token
        set({
          user: data.user,
          token: accessToken,
          isLoading: false,
          error: null,
        })
      } else {
        // Email confirmation required
        set({
          isLoading: false,
          error: "Please check your email to confirm your account",
        })
      }
    } catch (error: any) {
      set({
        isLoading: false,
        error: error.message || "Registration failed",
      })
      throw error
    }
  },

  logout: async () => {
    await supabase.auth.signOut()
    set({
      user: null,
      token: null,
      error: null,
    })
  },

  resetPassword: async (email: string) => {
    set({ isLoading: true, error: null })
    try {
      const { error } = await supabase.auth.resetPasswordForEmail(email)
      if (error) throw error
      set({ isLoading: false, error: null })
    } catch (error: any) {
      set({
        isLoading: false,
        error: error.message || "Failed to send reset email",
      })
      throw error
    }
  },

  checkAuth: async () => {
    set({ isLoading: true })
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (session) {
        const accessToken = session.access_token
        set({
          user: session.user,
          token: accessToken,
          isLoading: false,
        })
      } else {
        set({
          user: null,
          token: null,
          isLoading: false,
        })
      }
    } catch (error: any) {
      console.error("Auth check failed:", error)
      set({
        user: null,
        token: null,
        isLoading: false,
      })
    }
  },
}))

