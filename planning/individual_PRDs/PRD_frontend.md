# Frontend Module - Implementation PRD

**Version:** 1.0 | **Date:** November 14, 2025  
**Module:** Module 1 (Frontend)  
**Phase:** Phase 2  
**Status:** Implementation-Ready

---

## Executive Summary

This document provides a complete implementation guide for the Frontend module, a Next.js 14 web application that enables users to upload audio files, enter creative prompts, track video generation progress in real-time via Server-Sent Events (SSE), and view/download completed videos. The frontend integrates with Supabase Auth for authentication and communicates with the API Gateway via REST endpoints and SSE streams.

**Timeline:** 8-10 hours  
**Dependencies:** API Gateway endpoints (can use stubs initially), Supabase Auth, Vercel deployment (post-MVP)  
**Tech Stack:** Next.js 14 App Router, TypeScript, shadcn/ui, Zustand, SSE

---

## Directory Structure

```
frontend/
├── app/
│   ├── layout.tsx                    # Root layout with providers
│   ├── page.tsx                      # Landing/home page
│   ├── (auth)/
│   │   ├── layout.tsx                # Auth layout (centered, minimal)
│   │   ├── login/
│   │   │   └── page.tsx              # Login page
│   │   └── register/
│   │       └── page.tsx              # Registration page
│   ├── upload/
│   │   └── page.tsx                  # Audio upload + prompt input page
│   ├── jobs/
│   │   ├── [jobId]/
│   │   │   └── page.tsx              # Job progress page with SSE
│   │   └── page.tsx                  # Jobs list/history page (optional)
│   └── globals.css                   # Global styles + Tailwind
├── components/
│   ├── ui/                           # shadcn/ui components (auto-generated)
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   ├── card.tsx
│   │   ├── progress.tsx
│   │   ├── alert.tsx
│   │   └── ...                       # Other shadcn components
│   ├── AudioUploader.tsx             # Drag-and-drop audio upload component
│   ├── PromptInput.tsx               # Creative prompt textarea component
│   ├── ProgressTracker.tsx           # Real-time progress display component
│   ├── VideoPlayer.tsx               # Video playback component
│   ├── StageIndicator.tsx            # Stage status indicator component
│   ├── CostDisplay.tsx               # Cost tracking display (post-MVP)
│   ├── ErrorBoundary.tsx              # Error boundary wrapper
│   └── LoadingSpinner.tsx            # Loading state component
├── lib/
│   ├── api.ts                        # API client with TypeScript types
│   ├── sse.ts                        # SSE client hook and utilities
│   ├── supabase.ts                   # Supabase client configuration
│   └── utils.ts                      # Utility functions
├── stores/
│   ├── authStore.ts                  # Zustand auth store
│   ├── jobStore.ts                   # Zustand job store
│   └── uploadStore.ts                # Zustand upload form store
├── hooks/
│   ├── useSSE.ts                     # SSE connection hook
│   ├── useAuth.ts                    # Auth state hook
│   └── useJob.ts                     # Job state hook
├── types/
│   ├── api.ts                        # API request/response types
│   ├── job.ts                        # Job-related types
│   └── sse.ts                        # SSE event types
├── public/
│   └── ...                           # Static assets
├── next.config.js                    # Next.js configuration
├── tailwind.config.js                # Tailwind CSS configuration
├── tsconfig.json                     # TypeScript configuration
├── package.json                      # Dependencies
└── README.md                         # Frontend documentation
```

---

## Page Specifications

### `app/layout.tsx`
Root layout: Global CSS, metadata, optional ErrorBoundary wrapper

### `app/page.tsx`
Landing page: Hero section, CTA button (→ /upload if auth, → /login if not), feature highlights, responsive

### `app/(auth)/layout.tsx`
Auth layout: Centered container (max-width: 400px), minimal navigation

### `app/(auth)/login/page.tsx`
Login: Email/password form, authStore.login(), error handling with Alert, redirect on success, loading state, validation (email format, password min 6 chars)

### `app/(auth)/register/page.tsx`
Register: Email/password/confirm form, authStore.register(), auto-login on success, validation (email, password match, min 6 chars)

### `app/upload/page.tsx`
**Purpose:** Audio upload and prompt input page

**Components:** AudioUploader, PromptInput, Submit button, File preview, Loading spinner

**Logic Flow:**
1. Initialize uploadStore state (audioFile=null, userPrompt="", errors={})
2. Render AudioUploader with onChange handler → update uploadStore.audioFile
3. Render PromptInput with onChange handler → update uploadStore.userPrompt
4. Real-time validation: Check file size/format on file select, check prompt length on input
5. Display validation errors below inputs if invalid
6. Disable submit button if validation fails
7. On submit: Call uploadStore.submit() which:
   - Validates form (audio file ≤10MB MP3/WAV/FLAC, prompt 50-500 chars)
   - Creates FormData with audio_file and user_prompt
   - Calls POST /api/v1/upload-audio with Authorization header
   - On success: Extract job_id from response, redirect to /jobs/[jobId]
   - On error: Display error message in Alert component, allow retry
8. Show loading spinner during submission (isSubmitting state)

**Error Handling:** Network errors → "Connection error" + retry button, 400 → validation error message, 401 → redirect to login, 500 → generic error + retry

### `app/jobs/[jobId]/page.tsx`
**Purpose:** Job progress page with real-time SSE updates

**Components:** ProgressTracker, StageIndicator, VideoPlayer (when ready), LoadingSpinner, Error display, Download button

**Logic Flow:**
1. Extract jobId from URL params using useParams()
2. Initialize jobStore: Fetch job status via GET /api/v1/jobs/[jobId] on mount
3. Initialize SSE connection using useSSE hook:
   - URL: NEXT_PUBLIC_API_URL + /api/v1/jobs/[jobId]/stream
   - Handlers: onStageUpdate, onProgress, onMessage, onCostUpdate, onCompleted, onError
4. Update UI based on SSE events:
   - stage_update → Update StageIndicator, update jobStore.currentJob.currentStage
   - progress → Update ProgressTracker progress bar (0-100%), update jobStore.currentJob.progress
   - message → Display status message in card below progress bar
   - cost_update → Update cost display (post-MVP), update jobStore.currentJob.totalCost
   - completed → Show VideoPlayer with videoUrl, enable download button, hide loading spinner
   - error → Display error message in Alert, show retry button if retryable
5. Handle SSE connection errors:
   - On connection loss: Auto-reconnect with exponential backoff (2s, 4s, 8s, max 5 attempts)
   - Show connection status indicator ("Connecting...", "Connected", "Disconnected")
   - Fallback to polling: If SSE fails after 5 attempts, poll GET /api/v1/jobs/[jobId] every 5s
6. Loading states:
   - Initial load: Show LoadingSpinner, fetch job status
   - SSE connecting: Show "Connecting to server..." message
   - Processing: Show ProgressTracker + StageIndicator, hide spinner
   - Completed: Show VideoPlayer, hide progress components
   - Failed: Show error message + retry button, hide progress components

**State Management:** Use jobStore to manage job state, sync with SSE events, optional localStorage persistence for job state

### `app/jobs/page.tsx` (Optional)
Jobs list: Fetch from API, filter by status, sort by date, link to individual jobs, refresh every 30s

---

## Component Specifications

### `components/AudioUploader.tsx`
**Props:** value: File | null, onChange: (file: File | null) => void, error?: string, disabled?: boolean

**Implementation Logic:**
1. Create drag-and-drop zone div with onDragOver/onDragLeave/onDrop handlers
2. Track drag state: isDragging boolean, highlight border when dragging
3. File input: Hidden <input type="file" accept="audio/*">, trigger on zone click
4. File selection handler:
   - Get file from event.target.files[0]
   - Validate: Check MIME type (audio/mpeg, audio/wav, audio/flac, audio/mp3)
   - Validate: Check file size ≤10MB (10 * 1024 * 1024 bytes)
   - If valid: Call onChange(file), clear error
   - If invalid: Set error message, call onChange(null)
5. File preview: If file selected, display filename, size (format bytes to MB), format
6. Remove button: Clear file, call onChange(null), clear error
7. Error display: Show error prop below component in red text

**Visual States:**
- Empty: Show upload icon (cloud/arrow-up), "Drag and drop audio file" text, "or click to browse" hint
- Dragging: Highlight border (blue), show "Drop here" message, change background color
- Selected: Show file info card (filename, size, format), show remove button (X icon)
- Error: Show error message in red Alert component below zone
- Disabled: Gray opacity, pointer-events: none, show "Upload disabled" message

**Styling:** Use shadcn Card component for container, Tailwind classes for drag states, responsive (full width mobile, max-width desktop)

### `components/PromptInput.tsx`
**Props:** value: string, onChange: (value: string) => void, error?: string, disabled?: boolean

**Implementation Logic:**
1. Create textarea element with controlled value prop
2. Character counter: Calculate length, display "X / 500 characters"
3. Real-time validation: On input change, check length (50-500 chars)
4. Visual feedback:
   - If length < 50: Show error "Prompt must be at least 50 characters", red border
   - If length > 500: Show error "Prompt must be at most 500 characters", red border
   - If 50 <= length <= 500: Green border, no error
5. Placeholder text: "Describe your vision for the music video... (50-500 characters)"
6. Example prompts: Display below textarea (optional, collapsible)
7. Auto-resize: Optional, use CSS or JavaScript to grow textarea with content
8. Error display: Show error prop below textarea in red Alert component

**Visual States:**
- Normal: Default border, no error message
- Valid (50-500 chars): Green border, character counter in green
- Invalid (<50 or >500): Red border, error message below, character counter in red
- Disabled: Gray opacity, pointer-events: none, show "Input disabled" message

**Styling:** Use shadcn Textarea component, Tailwind classes for validation states, responsive width

### `components/ProgressTracker.tsx`
**Props:** jobId: string, onComplete?: (videoUrl: string) => void, onError?: (error: string) => void

**Implementation Logic:**
1. Use useSSE hook to connect to SSE stream: /api/v1/jobs/[jobId]/stream
2. Initialize state: progress (0-100), currentStage, messages (array), estimatedRemaining, cost (post-MVP)
3. SSE event handlers:
   - stage_update: Update currentStage state, update StageIndicator component
   - progress: Update progress state (0-100), update Progress bar value
   - message: Add message to messages array, display in message card
   - cost_update: Update cost state (post-MVP), update cost display
   - completed: Call onComplete(videoUrl), hide progress components, show completion message
   - error: Call onError(error), display error in Alert component
4. Progress bar: Use shadcn Progress component, value={progress}, show percentage text
5. Stage indicator: Render StageIndicator component with stages array and currentStage
6. Status messages: Display messages array in Card component, newest first, limit to 5 messages
7. ETA display: Show "Estimated time remaining: X minutes" if estimatedRemaining available
8. Cost display: Show "Total cost: $X.XX" (post-MVP) if cost available

**Visual Design:**
- Progress bar: Linear horizontal bar, percentage text above, animated transitions
- Stage list: Vertical list on mobile, horizontal on desktop, checkmarks for completed, spinner for current
- Messages: Card with scrollable list, timestamp for each message, color-coded by stage
- Layout: Progress bar at top, stages below, messages at bottom, responsive stacking

### `components/VideoPlayer.tsx`
**Props:** videoUrl: string, jobId: string, autoPlay?: boolean

**Implementation Logic:**
1. Create video element: <video src={videoUrl} controls preload="metadata" />
2. Loading state: Track video loading, show LoadingSpinner while loading
3. Error handling: onError handler, display error message if video fails to load
4. Download button:
   - Call downloadVideo(jobId) from API client
   - Create blob URL, trigger download: Create <a> element with download attribute, click programmatically
   - Show loading state during download
   - Handle errors: Display error message if download fails
5. Auto-play: If autoPlay prop is true, call video.play() on mount
6. Responsive: Maintain 16:9 aspect ratio, max-width 100%, height auto

**Video Element Attributes:**
- controls: Show play/pause/volume/fullscreen controls
- preload: "metadata" (load metadata only, not full video)
- poster: Optional thumbnail image URL (if available)
- playsInline: true (for mobile browsers)

**Styling:** Container with aspect-ratio: 16/9, responsive width, centered layout

### `components/StageIndicator.tsx`
**Props:** stages: Array<{name: string, status: "pending" | "processing" | "completed" | "failed"}>, currentStage: string

**Implementation Logic:**
1. Define stage list: ["audio_analysis", "scene_planning", "reference_generation", "prompt_generation", "video_generation", "composition"]
2. Map stages to display names: Audio Analysis (10%), Scene Planning (20%), Reference Generation (30%), Prompt Generation (40%), Video Generation (85%), Composition (100%)
3. For each stage:
   - Determine status from stages prop or currentStage comparison
   - Render indicator: Checkmark (✓) if completed, Spinner if processing, Circle (○) if pending, X if failed
   - Highlight current stage: Bold text, colored border, animated pulse
4. Responsive layout: Horizontal flex on desktop (lg breakpoint), vertical stack on mobile
5. Progress connection: Show connecting line between stages (optional visual)

**Visual Design:**
- Completed: Green checkmark, grayed out text
- Processing: Animated spinner, highlighted background, bold text
- Pending: Gray circle, normal text
- Failed: Red X icon, red text
- Current: Blue border, animated pulse, bold text

**Styling:** Use shadcn Card for container, flex layout, responsive breakpoints

### `components/ErrorBoundary.tsx`
**Purpose:** React error boundary for graceful error handling

**Implementation:**
1. Create class component extending React.Component
2. Implement getDerivedStateFromError: Set error state, return {hasError: true, error: error}
3. Implement componentDidCatch: Log error to console (or error tracking service)
4. Render logic:
   - If hasError: Display Alert component with error message, "Retry" button
   - If no error: Render children normally
5. Retry mechanism: Reset error state, force re-render
6. Wrap app or specific components in ErrorBoundary

**Error Display:** Use shadcn Alert component with error message, "Retry" button calls window.location.reload() or resetErrorState()

### `components/LoadingSpinner.tsx`
**Props:** size?: "sm" | "md" | "lg", text?: string. Animated spinner (CSS/SVG), optional text, consistent styling

---

## Store Specifications (Zustand)

### `stores/authStore.ts`
**State:** user: User | null, token: string | null, isLoading: boolean, error: string | null

**Implementation Logic:**
1. Create Zustand store using create() function
2. Initial state: user=null, token=null, isLoading=false, error=null
3. **login(email, password):**
   - Set isLoading=true, clear error
   - Call Supabase: client.auth.signInWithPassword({email, password})
   - On success: Extract user and session.access_token, set state, set isLoading=false
   - On error: Set error message, set isLoading=false, throw error
4. **register(email, password):**
   - Set isLoading=true, clear error
   - Call Supabase: client.auth.signUp({email, password})
   - On success: Auto-login (call signInWithPassword), set state, set isLoading=false
   - On error: Set error message, set isLoading=false, throw error
5. **logout():**
   - Call Supabase: client.auth.signOut()
   - Clear state: user=null, token=null, error=null
6. **resetPassword(email):**
   - Call Supabase: client.auth.resetPasswordForEmail(email)
   - Show success message (email sent)
7. **checkAuth():**
   - Call Supabase: client.auth.getSession()
   - If session exists: Extract user and token, set state
   - If no session: Clear state

**Persistence:** Optional localStorage for token (Supabase handles session persistence automatically)

### `stores/jobStore.ts`
**State:** currentJob: Job | null, jobs: Job[], isLoading: boolean, error: string | null

**Actions:** setCurrentJob(job), updateJob(jobId, updates) → from SSE events, fetchJob(jobId) → GET /api/v1/jobs/[jobId], fetchJobs() → GET /api/v1/jobs, clearCurrentJob()

**Job Type:** id, status ("queued"|"processing"|"completed"|"failed"), currentStage, progress (0-100), videoUrl, errorMessage, createdAt, updatedAt

### `stores/uploadStore.ts`
**State:** audioFile: File | null, userPrompt: string, isSubmitting: boolean, errors: {audio?: string, prompt?: string}

**Implementation Logic:**
1. Create Zustand store with initial state: audioFile=null, userPrompt="", isSubmitting=false, errors={}
2. **setAudioFile(file):**
   - Validate file: Check MIME type (audio/mpeg, audio/wav, audio/flac, audio/mp3), check size ≤10MB
   - If valid: Set audioFile=file, clear errors.audio
   - If invalid: Set errors.audio="Invalid file format or size", set audioFile=null
3. **setUserPrompt(prompt):**
   - Set userPrompt=prompt
   - Validate length: If <50 or >500, set errors.prompt="Prompt must be 50-500 characters"
   - If valid: Clear errors.prompt
4. **validate():**
   - Validate audioFile: Check exists, format, size
   - Validate userPrompt: Check length (50-500 chars)
   - Set errors object with any validation failures
   - Return true if all valid, false otherwise
5. **submit():**
   - Call validate(), if invalid return early
   - Set isSubmitting=true, clear errors
   - Create FormData: Append audio_file (audioFile), user_prompt (userPrompt)
   - Call API: uploadAudio(audioFile, userPrompt)
   - On success: Extract job_id, set isSubmitting=false, return job_id
   - On error: Set error message, set isSubmitting=false, throw error
6. **reset():**
   - Clear all state: audioFile=null, userPrompt="", errors={}, isSubmitting=false

---

## Hook Specifications

### `hooks/useSSE.ts`
**Signature:** useSSE(url: string, handlers: SSEHandlers): {isConnected, error, reconnect, close}

**Handlers:** onStageUpdate: (data: StageUpdateEvent) => void, onProgress: (data: ProgressEvent) => void, onMessage: (data: MessageEvent) => void, onCostUpdate: (data: CostUpdateEvent) => void, onCompleted: (data: CompletedEvent) => void, onError: (data: ErrorEvent) => void

**Implementation Logic:**
1. State: isConnected (boolean), error (string | null), eventSource (EventSource | null), reconnectAttempts (number)
2. Create EventSource: new EventSource(url, { withCredentials: true })
3. Event listeners:
   - onopen → set isConnected=true, reset reconnectAttempts
   - onerror → set isConnected=false, increment reconnectAttempts, trigger auto-reconnect if <5 attempts
   - Add custom listeners for each event type: eventSource.addEventListener('stage_update', ...), etc.
4. Parse JSON: For each event, parse event.data as JSON, call corresponding handler
5. Auto-reconnect: On error, wait exponential backoff (2^attempts seconds: 2s, 4s, 8s, 16s, 32s), recreate EventSource, max 5 attempts
6. Cleanup: On unmount or close(), close EventSource, remove listeners
7. Manual reconnect: Expose reconnect() function to manually trigger reconnection
8. Return: {isConnected, error, reconnect, close}

**Error Handling:** Network errors → set error, trigger reconnect; Parse errors → log to console, continue; Max attempts → set error="Connection failed", stop reconnecting

### `hooks/useAuth.ts`
**Purpose:** Convenience hook for accessing auth state and actions

**Implementation:**
- Access authStore using Zustand hook: const {user, token, isLoading, login, logout, register} = authStore()
- Return same values for component use
- Optional: Add useEffect to checkAuth() on mount if not already checked

**Return:** {user: User | null, token: string | null, isLoading: boolean, login: (email: string, password: string) => Promise<void>, logout: () => void, register: (email: string, password: string) => Promise<void>}

### `hooks/useJob.ts`
**Purpose:** Convenience hook for accessing job state and actions

**Implementation:**
- Access jobStore using Zustand hook: const {currentJob, isLoading, error, fetchJob, updateJob} = jobStore()
- Return same values for component use
- Optional: Add useEffect to fetchJob(jobId) on mount if jobId provided

**Return:** {job: Job | null, isLoading: boolean, error: string | null, fetchJob: (jobId: string) => Promise<void>, updateJob: (updates: Partial<Job>) => void}

---

## API Client Specifications

### `lib/api.ts`
**Base Configuration:**
- Base URL: process.env.NEXT_PUBLIC_API_URL
- Default headers: Content-Type: application/json (except multipart)
- Auth header: Get token from authStore, add Authorization: Bearer {token} to all requests

**Function: uploadAudio(audioFile: File, userPrompt: string): Promise<UploadResponse>**
- Create FormData: Append audio_file (file) and user_prompt (string)
- Method: POST, Endpoint: /api/v1/upload-audio
- Headers: Authorization Bearer token (from authStore), no Content-Type (browser sets multipart/form-data)
- Response: {job_id: string, audio_url: string, status: string, estimated_time: number}
- Error handling: Throw APIError with message, handle 400 (validation error), 401 (redirect login), 500 (retry)

**Function: getJob(jobId: string): Promise<JobResponse>**
- Method: GET, Endpoint: /api/v1/jobs/{jobId}
- Headers: Authorization Bearer token
- Response: Job object {id, status, currentStage, progress, videoUrl, errorMessage, ...}
- Error handling: Throw APIError if 404 (job not found), 401 (redirect login)

**Function: downloadVideo(jobId: string): Promise<Blob>**
- Method: GET, Endpoint: /api/v1/jobs/{jobId}/download
- Headers: Authorization Bearer token
- Response: Binary video data (Blob)
- Error handling: Throw APIError if download fails, handle 404 (video not ready), 401 (redirect login)

**Error Handling:**
- Network errors: Catch fetch errors, throw APIError("Connection error")
- Parse errors: Try-catch JSON.parse, throw APIError("Invalid response")
- Status codes: 400 → validation error message, 401 → clear authStore, redirect /login, 429 → extract retry-after header, show message, 500 → generic error message
- APIError class: Extends Error, includes statusCode, message, retryable boolean

**Type Definitions:**
- UploadResponse: {job_id: string, audio_url: string, status: string, estimated_time: number}
- JobResponse: {id: string, status: "queued"|"processing"|"completed"|"failed", currentStage: string | null, progress: number, videoUrl: string | null, errorMessage: string | null, createdAt: string, updatedAt: string}
- APIError: class extends Error {statusCode: number, retryable: boolean}

### `lib/sse.ts`
**Event Types:** StageUpdateEvent {stage, status, duration}, ProgressEvent {progress, estimated_remaining}, MessageEvent {text, stage}, CostUpdateEvent {stage, cost, total}, CompletedEvent {video_url, total_cost}, ErrorEvent {error, code, retryable}

**URL:** NEXT_PUBLIC_API_URL + /api/v1/jobs/{jobId}/stream, include credentials

### `lib/supabase.ts`
**Config:** NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY, create client instance. Usage: client.auth.signInWithPassword(), signUp(), signOut(), client.storage (if needed)

---

## Integration Points

**API Endpoints:** POST /api/v1/upload-audio (uploadStore.submit, FormData, returns job_id), GET /api/v1/jobs/{jobId} (jobStore.fetchJob, polling fallback), GET /api/v1/jobs/{jobId}/stream (useSSE hook, SSE updates), GET /api/v1/jobs/{jobId}/download (VideoPlayer, returns blob)

**Supabase Auth:** signInWithPassword(), signUp(), signOut(), resetPasswordForEmail(), getSession()

---

## Error Handling Patterns

**API Errors:** Network → "Connection error" + retry; 401 → clear auth, redirect login; 429 → "Too many requests" + retry-after; 400 → validation error; 500 → generic error + retry

**SSE Errors:** Connection lost → auto-reconnect (exponential backoff), show status indicator, fallback to polling

**Form Validation:** Real-time validation, error messages below inputs, disable submit if invalid, clear errors on change

**Error Display:** shadcn Alert component, clear message, retry action if applicable, log to console

---

## Responsive Design Considerations

**Breakpoints:** Mobile <640px (sm), Tablet 640-1024px (md), Desktop >1024px (lg)

**Mobile:** Stack inputs vertically, full-width buttons, simplified nav, touch targets (min 44x44px), optimized video player

**Tablet:** Two-column forms, side-by-side components, touch targets

**Desktop:** Multi-column layouts, hover states, keyboard navigation

**Component Responsiveness:** AudioUploader (full width mobile, max-width desktop), ProgressTracker (vertical mobile, horizontal desktop), VideoPlayer (16:9 aspect ratio), Navigation (hamburger mobile, horizontal desktop)

---

## Testing Requirements

### Unit Tests
**Components:** AudioUploader (file selection/validation/errors), PromptInput (char count/validation), ProgressTracker (progress/stages), VideoPlayer (playback/download)

**Hooks:** useSSE (events/reconnection), useAuth (login/logout/session), useJob (state updates)

**Stores:** authStore (auth state), jobStore (job state), uploadStore (form/validation)

**API Client:** Mock responses, error handling, request formatting

### Integration Tests
**User Flows:** Login → Upload → Progress → Download, Register → Auto-login → Upload, SSE connection/updates, error scenarios

**E2E (Manual):** Complete video generation flow, SSE updates, playback/download, error recovery

---

## Success Criteria

✅ Upload works (<2s to submit)  
✅ Real-time progress visible (<1s latency via SSE)  
✅ Video plays and downloads correctly  
✅ Mobile-responsive design  
✅ Handles 5+ concurrent users  
✅ Error handling works gracefully  
✅ Authentication flow complete  
✅ SSE auto-reconnects on failure  
✅ Form validation prevents invalid submissions  
✅ Loading states provide good UX

---

## Implementation Notes

**Next.js 14 App Router:** Server Components by default, Client Components ("use client") for interactivity/hooks, file-based routing (app/), nested layouts

**shadcn/ui:** Install via CLI (npx shadcn-ui@latest init), add components (button/input/card/progress/alert), customize via tailwind.config.js, copy-paste components

**Zustand:** No providers needed, use create() for stores, access directly or via hooks

**SSE:** Native EventSource API, {withCredentials: true}, handle CORS, auto-reconnect

**TypeScript:** Strict mode, type API responses/props, use inference where appropriate

**Env Vars:** NEXT_PUBLIC_API_URL, NEXT_PUBLIC_SUPABASE_URL, NEXT_PUBLIC_SUPABASE_ANON_KEY

**Vercel:** Connect GitHub, auto-deploy on main, set env vars in dashboard, no build config needed

---

**Document Status:** Ready for Implementation  
**Next Action:** Initialize Next.js project, install dependencies, set up shadcn/ui, begin with layout and auth pages

