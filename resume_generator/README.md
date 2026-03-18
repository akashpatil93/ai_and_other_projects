# ResumeAI — Tailored Resumes, Instantly

An AI-powered chatbot that tailors your resume to any job description — ATS-optimized, grounded in your actual experience, with optional cover letter generation.

---

## Features

- **Multi-agent support** — Claude (Anthropic) or Gemini (Google)
- **Profile ingestion** — Upload resume (PDF/DOCX/TXT), LinkedIn profile, GitHub, and free-form notes
- **JD ingestion** — Paste a URL, upload a PDF/DOCX, or paste text directly
- **AI tailoring** — Reframes existing bullets using JD language; never fabricates
- **Missing data prompting** — Asks for quantified metrics only when they'd make a meaningful difference
- **Multi-turn refinement** — Iteratively improve the resume via chat
- **Cover letter generation** — Triggered as a separate step after resume approval
- **ATS-optimized output** — All-caps section headers, action verbs, no tables/columns
- **Export** — Plain text (copy-paste), PDF, and Word (.docx)

---

## Project Structure

```
resume-builder/
├── backend/
│   ├── main.py                   # FastAPI app entry point
│   ├── requirements.txt
│   ├── routers/
│   │   ├── chat.py               # Resume generation, refinement, cover letter
│   │   ├── upload.py             # File/URL ingestion, session creation
│   │   └── export.py             # TXT/PDF/DOCX download endpoints
│   ├── services/
│   │   ├── ai_service.py         # Claude + Gemini abstraction
│   │   ├── parser_service.py     # PDF, DOCX, URL text extraction
│   │   ├── linkedin_service.py   # LinkedIn profile fetching
│   │   └── session_store.py      # In-memory session management
│   └── prompts/
│       └── templates.py          # System + generation prompt templates
│
└── frontend/
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    ├── index.html
    └── src/
        ├── App.jsx               # Root app, step routing, session management
        ├── index.css             # Design system + Tailwind
        ├── main.jsx
        ├── api/
        │   └── client.js         # All API calls
        └── components/
            ├── Sidebar.jsx       # API key, agent selector, step nav
            └── steps/
                ├── StepProfile.jsx   # Resume + LinkedIn + GitHub upload
                ├── StepJD.jsx        # Job description input
                ├── StepChat.jsx      # Chat interface + approval
                └── StepExport.jsx    # Download / copy panel
```

---

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+

### 1. Clone the repo

```bash
git clone <your-repo-url>
cd resume-builder
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Usage

1. **Sidebar** — Select your AI agent (Claude or Gemini) and paste your API key, then click **Connect**
2. **Step 1: Profile** — Upload your resume (required), optionally add LinkedIn URL, GitHub URL, and extra notes
3. **Step 2: Job Description** — Paste a job URL, upload a PDF/DOCX, or paste the JD text
4. **Step 3: Build & Refine** — The AI generates a tailored resume; chat to refine it; click **Approve Resume** when happy
5. **Step 4: Export** — Download as TXT, PDF, or DOCX; optionally generate a cover letter

---

## API Keys

| Agent  | Where to get it |
|--------|----------------|
| Claude | https://console.anthropic.com |
| Gemini | https://aistudio.google.com/apikey |

Keys are only stored in memory for the duration of your session — they are never logged or persisted.

---

## Notes on LinkedIn

LinkedIn actively blocks automated scraping. If the LinkedIn URL import fails, it will prompt you to either:
- Upload your **LinkedIn PDF export** (Profile → More → Save to PDF) as your resume input
- Continue without LinkedIn data — the resume will still be tailored from your uploaded resume

---

## Production Considerations

- Replace `session_store.py` in-memory dict with **Redis** for multi-worker deployments
- Add **rate limiting** (e.g. slowapi) on the `/api/chat/` endpoints
- Use **HTTPS** and store API keys in environment variables or a secrets manager
- For scale, consider streaming responses via Server-Sent Events (SSE)
