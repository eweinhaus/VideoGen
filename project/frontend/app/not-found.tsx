import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Home } from "lucide-react"

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center px-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Home className="h-5 w-5 text-muted-foreground" />
            <CardTitle>404 - Page Not Found</CardTitle>
          </div>
          <CardDescription>
            The page you're looking for doesn't exist.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/">
            <Button className="w-full">Go back home</Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}

