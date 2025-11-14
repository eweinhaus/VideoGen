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
  isLoading: false,
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
      console.log("Login successful, token:", accessToken ? `${accessToken.substring(0, 20)}...` : "null")
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
        console.log("Registration successful, token:", accessToken ? `${accessToken.substring(0, 20)}...` : "null")
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
    try {
      const { data: { session } } = await supabase.auth.getSession()
      if (session) {
        const accessToken = session.access_token
        console.log("Session found, token:", accessToken ? `${accessToken.substring(0, 20)}...` : "null")
        set({
          user: session.user,
          token: accessToken,
        })
      } else {
        console.log("No session found")
        set({
          user: null,
          token: null,
        })
      }
    } catch (error: any) {
      console.error("Auth check failed:", error)
      set({
        user: null,
        token: null,
      })
    }
  },
}))

