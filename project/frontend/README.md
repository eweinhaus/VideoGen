# Module 1: Frontend

**Tech Stack:** Next.js 14 + TypeScript + shadcn/ui + Zustand + SSE

## Purpose
User-facing web interface for uploading audio, entering creative prompts, tracking generation progress in real-time, and viewing/downloading completed videos.

## Key Features
- Audio Upload (drag-and-drop, MP3/WAV/FLAC, max 10MB)
- Creative Prompt input (50-500 characters)
- Real-time Progress tracking via SSE
- Video Player with progressive clip rendering
- Authentication (Supabase Auth)

## User Flow
1. Login → Upload audio + enter prompt → Submit
2. Redirect to progress page with real-time updates
3. Watch clips appear as they generate
4. Play final video when complete
5. Download MP4

## Setup Instructions

### Prerequisites
- Node.js 18+ and npm
- Supabase project with Auth enabled
- API Gateway running (or use stubs/mocks)

### Installation

1. Install dependencies:
```bash
npm install
```

2. Create `.env.local` file:
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=your_supabase_url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key
```

3. Run development server:
```bash
npm run dev
```

4. Open [http://localhost:3000](http://localhost:3000)

### Project Structure

```
frontend/
├── app/                    # Next.js App Router pages
│   ├── (auth)/            # Auth pages (login, register)
│   ├── upload/            # Upload page
│   ├── jobs/              # Job pages
│   └── layout.tsx         # Root layout
├── components/            # React components
│   ├── ui/                # shadcn/ui components
│   ├── AudioUploader.tsx
│   ├── PromptInput.tsx
│   ├── ProgressTracker.tsx
│   └── VideoPlayer.tsx
├── hooks/                 # Custom React hooks
│   ├── useSSE.ts          # SSE connection hook
│   ├── useAuth.ts         # Auth state hook
│   └── useJob.ts          # Job state hook
├── lib/                   # Utilities
│   ├── api.ts             # API client
│   ├── supabase.ts        # Supabase client
│   └── utils.ts           # Helper functions
├── stores/                # Zustand stores
│   ├── authStore.ts
│   ├── jobStore.ts
│   └── uploadStore.ts
└── types/                 # TypeScript types
    ├── api.ts
    ├── job.ts
    └── sse.ts
```

### Key Components

- **AudioUploader**: Drag-and-drop file upload with validation
- **PromptInput**: Textarea with character counter and validation
- **ProgressTracker**: Real-time progress display with SSE integration
- **VideoPlayer**: Video playback with download functionality
- **StageIndicator**: Visual stage progress indicator

### State Management

- **authStore**: Manages authentication state (user, token, login/logout)
- **jobStore**: Manages job state (current job, job list, fetch/update)
- **uploadStore**: Manages upload form state (file, prompt, validation)

### API Integration

The frontend communicates with the API Gateway via:
- REST endpoints for upload, job status, and download
- SSE stream for real-time progress updates

All requests include JWT Bearer token from Supabase Auth.

### Development

- **Build**: `npm run build`
- **Start**: `npm start`
- **Lint**: `npm run lint`

### Environment Variables

- `NEXT_PUBLIC_API_URL`: API Gateway base URL
- `NEXT_PUBLIC_SUPABASE_URL`: Supabase project URL
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`: Supabase anonymous key

### Notes

- SSE connection auto-reconnects with exponential backoff (max 5 attempts)
- Form validation prevents invalid submissions
- Error handling includes network errors, API errors, and SSE failures
- Mobile-responsive design with Tailwind CSS breakpoints

