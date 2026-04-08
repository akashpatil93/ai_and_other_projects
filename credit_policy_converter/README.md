# Credit Policy → Workflow JSON Converter

A web application that converts credit policy documents (Excel, PDF, DOCX, CSV) into workflow JSON files accepted by the BRE (Business Rule Engine) platform. It uses Claude AI to parse and interpret policy rules and produces a validated, ready-to-import `.workflow` file.

---

## Features

- **Multi-format upload** — XLSX, XLS, PDF, DOCX, CSV, JSON
- **AI-powered extraction** — Claude claude-opus-4-6 with extended thinking classifies sections and extracts rules, expressions, decision tables, and matrices
- **Full workflow schema** — Generates all BRE node types: `start`, `dataSource`, `modelSet`, `ruleSet`, `branch`, `switch`, `end`
- **Three expression types** — `expression` (formula), `decisionTable` (flat lookup), `matrix` (2D grid)
- **Muted rule support** — Inactive rules are placed in separate `muted_*` ruleSet nodes that never block approval
- **Correct node layout** — Positions are calculated per-node based on content width; no overlapping cards on import
- **Review & edit UI** — Inline rule editor with JSON viewer before export
- **Export as `.workflow`** — Direct download in the format the BRE expects
- **API key management** — Enter and verify your Anthropic key from the UI; stored in browser localStorage only

---

## Architecture

```
credit_policy_converter/
├── backend/                  Python FastAPI
│   ├── main.py               API routes
│   ├── parsers/
│   │   ├── excel_parser.py   openpyxl — XLSX/XLS
│   │   ├── pdf_parser.py     PyMuPDF — PDF
│   │   └── docx_parser.py    python-docx — DOCX
│   ├── llm/
│   │   ├── claude_client.py  Anthropic async client + JSON extraction
│   │   ├── prompts.py        All domain prompts with field mappings
│   │   └── assembler.py      Builds workflow DAG from extracted data
│   ├── validators/
│   │   └── workflow_validator.py  Structural validation
│   └── requirements.txt
├── frontend/                 React 18 + TypeScript + Vite + Tailwind
│   └── src/
│       ├── App.tsx           3-step wizard (upload → processing → review)
│       ├── api/client.ts     Axios client with API key injection
│       ├── types/workflow.ts Full TypeScript interfaces for workflow schema
│       └── components/
│           ├── FileUpload.tsx
│           ├── ProcessingStatus.tsx
│           ├── WorkflowViewer.tsx  Syntax-highlighted JSON viewer
│           ├── RuleEditor.tsx      Inline rule/expression editor
│           └── ApiKeyModal.tsx     API key entry and verification
└── start.sh                  One-command launcher
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10+ |
| Node.js | 18+ |
| Anthropic API key | `sk-ant-...` |

---

## Setup & Run

### Option 1 — One command (recommended)

```bash
cd credit_policy_converter

# First run: copy the env template
cp backend/.env.example backend/.env
# Edit backend/.env and paste your ANTHROPIC_API_KEY

chmod +x start.sh
./start.sh
```

The script will:
1. Create a Python virtual environment inside `backend/`
2. Install Python dependencies
3. Install npm dependencies (if not already installed)
4. Start the FastAPI backend on port **8000**
5. Start the Vite dev server on port **5173**
6. Open `http://localhost:5173` in your browser

Press `Ctrl+C` to stop both servers.

---

### Option 2 — Manual

**Backend**

```bash
cd credit_policy_converter/backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # add your ANTHROPIC_API_KEY
uvicorn main:app --reload --port 8000
```

**Frontend**

```bash
cd credit_policy_converter/frontend
npm install
npm run dev
# → http://localhost:5173
```

---

## API Key

The Anthropic API key can be provided in two ways (the UI key takes priority):

| Method | How |
|---|---|
| **UI (recommended)** | Click **"Add API key"** in the top-right of the app, paste your key, click **Save & verify** |
| **Environment variable** | Set `ANTHROPIC_API_KEY` in `backend/.env` |

The UI key is stored in browser `localStorage` and sent as an `X-Anthropic-Key` request header. It is never logged or persisted server-side.

---

## Workflow Schema

The generated workflow is a DAG with the following node sequence:

```
Start
 └─► Source_Node_Bureau (dataSource)
      └─► scorecard (modelSet, optional)
           └─► model (modelSet)
                └─► muted_go_no_go_checks (ruleSet, optional)
                     └─► go_no_go_checks (ruleSet, optional)
                          └─► muted_surrogate_policy_checks (ruleSet, optional)
                               └─► surrogate_policy_checks (ruleSet, optional)
                                    └─► final_decision (branch)
                                         ├─► eligibility (modelSet, optional)
                                         │    └─► end_approved
                                         └─► end_rejected
```

Switch nodes (`<name>-switch`) sit between every ruleSet/branch and the next node. They are invisible routing connectors with no position metadata.

### Node types

| Type | Purpose |
|---|---|
| `start` | Entry point |
| `dataSource` | Bureau credit pull |
| `modelSet` | Computed expressions — formula, decisionTable, or matrix |
| `ruleSet` | Policy rules with `approveCondition` / `cantDecideCondition` |
| `branch` | Conditional split (evaluate expressions, route via switch) |
| `switch` | Routes outcomes from the preceding ruleSet or branch |
| `end` | Terminal state with a decision output |

### Expression types inside a modelSet

| Type | When to use | Key fields |
|---|---|---|
| `expression` | Single formula or condition | `condition` |
| `decisionTable` | Flat lookup: N column conditions → output | `decisionTableRules` |
| `matrix` | 2D grid: row-variable × column-variable → cell | `matrix` |

---

## Expression Reference Rules

### Within the same modelSet — use the bare expression name

If `max_emi` is defined at seqNo 0 inside `offer_calc`, a later expression at seqNo 1 can write:

```
ROUNDOFF(PV(interest, max_tenure, max_emi, 0, 0), 1000)
```

### Across nodes — prefix with the source node name

```
model.hit_no_hit               # expression in the "model" modelSet
scorecard.bureau_score_woe     # expression in the "scorecard" modelSet
go_no_go_checks.decision       # outcome of the go_no_go_checks ruleSet
```

### Execution order (what's available where)

| Node | Can reference |
|---|---|
| `scorecard` | `bureau.*`, `input.*` |
| `model` | `bureau.*`, `input.*`, `scorecard.<expr>` |
| `go_no_go_checks` | + `model.<expr>` |
| `surrogate_policy_checks` | + `go_no_go_checks.decision` |
| `eligibility` | all of the above |

---

## Muted Rules

Rules marked **"Muted"**, **"M"**, **"Inactive"**, or **"Not in force"** in the source document are placed in `muted_*` prefixed ruleSet nodes. Their switch routes both `pass` and `reject` outcomes to the same next node — they are evaluated but never block the application.

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/api/verify-key` | Validate Anthropic API key |
| `POST` | `/api/upload` | Upload a policy document |
| `POST` | `/api/parse` | Parse document into sections |
| `POST` | `/api/generate` | Run Claude + assemble + validate |
| `GET` | `/api/workflow/{id}` | Retrieve stored workflow |
| `PUT` | `/api/workflow/{id}` | Update and re-validate |
| `GET` | `/api/export/{id}` | Download `.workflow` file |
| `POST` | `/api/validate` | Validate any workflow JSON body |

All requests that trigger Claude must include either `X-Anthropic-Key: sk-ant-...` header or have `ANTHROPIC_API_KEY` set in the backend environment.

---

## Supported Input Formats

| Format | Parser | Notes |
|---|---|---|
| `.xlsx` / `.xls` | openpyxl | All sheets extracted; header row auto-detected |
| `.pdf` | PyMuPDF | Section boundaries detected by ALL-CAPS headings |
| `.docx` | python-docx | Heading styles start new sections; tables extracted |
| `.csv` | stdlib `csv` | Single section; first row treated as headers |
| `.json` | stdlib `json` | Passed as-is to Claude for re-structuring |
