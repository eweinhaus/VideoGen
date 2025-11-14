"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/hooks/useAuth"
import { Music, Video, Zap, Sparkles } from "lucide-react"

export default function LandingPage() {
  const router = useRouter()
  const { isAuthenticated, isLoading } = useAuth()

  useEffect(() => {
    if (!isLoading && isAuthenticated) {
      router.push("/upload")
    }
  }, [isAuthenticated, isLoading, router])

  const handleGetStarted = () => {
    if (isAuthenticated) {
      router.push("/upload")
    } else {
      router.push("/login")
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <main className="flex flex-1 flex-col items-center justify-center px-4 py-12">
        <div className="container mx-auto max-w-4xl space-y-12">
          {/* Hero Section */}
          <div className="space-y-6 text-center">
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
              AI Music Video Generator
            </h1>
            <p className="mx-auto max-w-2xl text-lg text-muted-foreground sm:text-xl">
              Transform your music into professional, beat-synchronized videos
              powered by AI. Upload your audio, describe your vision, and watch
              the magic happen.
            </p>
            <div className="flex justify-center gap-4">
              <Button size="lg" onClick={handleGetStarted}>
                Get Started
              </Button>
              {!isAuthenticated && (
                <Button size="lg" variant="outline" onClick={() => router.push("/register")}>
                  Sign Up
                </Button>
              )}
            </div>
          </div>

          {/* Features */}
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader>
                <Music className="mb-2 h-8 w-8 text-primary" />
                <CardTitle>Audio Analysis</CardTitle>
                <CardDescription>
                  Advanced beat detection and structure analysis
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <Video className="mb-2 h-8 w-8 text-primary" />
                <CardTitle>AI Generation</CardTitle>
                <CardDescription>
                  High-quality video clips generated with AI
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <Zap className="mb-2 h-8 w-8 text-primary" />
                <CardTitle>Fast Processing</CardTitle>
                <CardDescription>
                  Generate videos in minutes, not hours
                </CardDescription>
              </CardHeader>
            </Card>

            <Card>
              <CardHeader>
                <Sparkles className="mb-2 h-8 w-8 text-primary" />
                <CardTitle>Creative Control</CardTitle>
                <CardDescription>
                  Describe your vision and watch it come to life
                </CardDescription>
              </CardHeader>
            </Card>
          </div>
        </div>
      </main>
    </div>
  )
}

