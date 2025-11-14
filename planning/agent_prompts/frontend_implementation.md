# Frontend Module Implementation Prompt

Implement Module 1 (Frontend) for the AI Music Video Generation Pipeline. Follow the detailed implementation PRD located at `planning/individual_PRDs/PRD_frontend.md`.

**Context:** This is a Next.js 14 web application that enables users to upload audio files, enter creative prompts, track video generation progress in real-time via Server-Sent Events (SSE), and view/download completed videos. The frontend integrates with Supabase Auth for authentication and communicates with the API Gateway via REST endpoints and SSE streams.

**Requirements:**
- Implement all pages, components, stores, and hooks according to the PRD directory structure
- Use Next.js 14 App Router with TypeScript
- Implement shadcn/ui components (button, input, card, progress, alert, textarea)
- Set up Zustand stores (authStore, jobStore, uploadStore) with detailed logic flows
- Implement SSE connection hook (useSSE) with auto-reconnect and exponential backoff
- Create AudioUploader component with drag-and-drop, file validation (MP3/WAV/FLAC, ≤10MB)
- Create PromptInput component with character counter and validation (50-500 chars)
- Implement ProgressTracker component with real-time SSE updates
- Create VideoPlayer component with download functionality
- Integrate Supabase Auth for login, registration, and session management
- Implement API client with TypeScript types for all endpoints
- Make the UI mobile-responsive with proper breakpoints

**Key Implementation Details:**
- Pages: Landing, login, register, upload, jobs/[jobId] (progress page), jobs (list, optional)
- SSE Integration: Connect to `/api/v1/jobs/{jobId}/stream`, handle all event types (stage_update, progress, message, completed, error)
- Form Validation: Real-time validation for audio file and prompt input
- Error Handling: Handle network errors, API errors (400, 401, 429, 500), SSE connection failures
- State Management: Use Zustand stores for auth, job state, and upload form state

**Dependencies:** API Gateway endpoints can use stubs/mocks initially. Supabase Auth must be configured. Vercel deployment is post-MVP (not needed yet). Can be built in parallel with backend modules.

**Deliverables:** Complete Next.js application with all components, pages, stores, hooks, and API integration. Ensure responsive design and proper error handling. Follow PRD logic specifications without making architectural decisions.

