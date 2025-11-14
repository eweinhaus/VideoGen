# Module 1: Frontend

**Tech Stack:** Next.js 14 + TypeScript

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


