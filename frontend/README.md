# EY AI Pitch PowerPoint Add-in

Phase 1 Office.js task pane add-in for generating EY AI Pitch PowerPoint decks from inside Microsoft PowerPoint.

## What This Includes

- Office task pane manifest
- Plain HTML, CSS, and JavaScript UI
- Backend `fetch()` integration with `https://localhost:8000/generate`
- Loading, success, and failure states
- Insert generated slides into the current PowerPoint presentation
- Local `.pptx` download fallback if slide insertion is unavailable

## Local Setup

Install frontend dependencies:

```bash
cd frontend
npm install
```

Start the existing FastAPI backend separately on port `8000`.
For PowerPoint on macOS, use HTTPS so the Office task pane WebView can call the backend:

```bash
./scripts/start_backend_https.sh
```

The backend will be available at:

```text
https://localhost:8000
```

Start the add-in frontend:

```bash
npm start
```

This serves the task pane at:

```text
https://localhost:3000/taskpane/taskpane.html
```

## Sideload In PowerPoint

With the frontend server running:

```bash
npm run sideload
```

PowerPoint should open with the EY AI Pitch task pane add-in sideloaded. Open the task pane, enter a prompt, and click **Generate Slide**. The generated slide will be inserted into the current presentation. If the PowerPoint JavaScript insertion API is unavailable, the generated `.pptx` will download locally as a fallback.

## Notes

- The add-in uses PowerPointApi 1.2 to insert generated slides into the current presentation.
- If insertion is not supported by the host, it downloads the generated deck instead.
- It does not add custom ribbon commands.
- It does not change the backend API or renderer.
