package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"

	"creditpolicyconverter/generator"

	"github.com/google/uuid"
)

// ─────────────────────────────────────────────────────────────────────────────
// In-memory stores (swap for Redis / DB in production)
// ─────────────────────────────────────────────────────────────────────────────

var (
	uploadsMu    sync.RWMutex
	uploadsStore = map[string]*uploadEntry{}

	workflowsMu    sync.RWMutex
	workflowsStore = map[string]*workflowEntry{}
)

type uploadEntry struct {
	Filename    string
	Content     []byte
	ContentType string
	Size        int
	Sections    []generator.Section
	ParseID     string
}

type workflowEntry struct {
	Workflow   map[string]interface{}
	Validation generator.ValidationResult
	FileID     string
}

// ─────────────────────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────────────────────

func main() {
	mux := http.NewServeMux()

	mux.HandleFunc("/", handleRoot)
	mux.HandleFunc("/health", handleHealth)
	mux.HandleFunc("/api/verify-key", handleVerifyKey)
	mux.HandleFunc("/api/upload", handleUpload)
	mux.HandleFunc("/api/parse", handleParse)
	mux.HandleFunc("/api/generate", handleGenerate)
	mux.HandleFunc("/api/validate", handleValidate)
	mux.HandleFunc("/api/workflow/", handleWorkflow)
	mux.HandleFunc("/api/export/", handleExport)

	port := os.Getenv("PORT")
	if port == "" {
		port = "3333"
	}

	log.Printf("Credit Policy Converter API listening on :%s", port)
	if err := http.ListenAndServe(":"+port, corsMiddleware(mux)); err != nil {
		log.Fatalf("server error: %v", err)
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// CORS Middleware
// ─────────────────────────────────────────────────────────────────────────────

func corsMiddleware(next http.Handler) http.Handler {
	allowed := map[string]bool{
		"http://localhost:5173": true,
		"http://localhost:5174": true,
		"http://localhost:3000": true,
	}
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		origin := r.Header.Get("Origin")
		if allowed[origin] {
			w.Header().Set("Access-Control-Allow-Origin", origin)
		}
		w.Header().Set("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
		w.Header().Set("Access-Control-Allow-Headers", "Content-Type, X-Anthropic-Key")
		w.Header().Set("Access-Control-Allow-Credentials", "true")
		if r.Method == http.MethodOptions {
			w.WriteHeader(http.StatusNoContent)
			return
		}
		next.ServeHTTP(w, r)
	})
}

// ─────────────────────────────────────────────────────────────────────────────
// Response helpers
// ─────────────────────────────────────────────────────────────────────────────

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"detail": msg})
}

// ─────────────────────────────────────────────────────────────────────────────
// Handlers
// ─────────────────────────────────────────────────────────────────────────────

func handleRoot(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{
		"status":  "ok",
		"message": "Credit Policy Converter API",
	})
}

func handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func handleVerifyKey(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	key := r.Header.Get("X-Anthropic-Key")
	if key == "" {
		writeError(w, http.StatusBadRequest, "No API key provided.")
		return
	}
	if !strings.HasPrefix(key, "sk-ant-") {
		writeError(w, http.StatusBadRequest, "Key does not look like a valid Anthropic API key.")
		return
	}
	masked := key[:12] + "..." + key[len(key)-4:]
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"valid":  true,
		"masked": masked,
	})
}

func handleUpload(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "failed to parse form: "+err.Error())
		return
	}
	file, header, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "missing 'file' field: "+err.Error())
		return
	}
	defer file.Close()

	filename := header.Filename
	ext := strings.ToLower(filepath.Ext(filename))
	allowed := map[string]bool{
		".xlsx": true, ".xls": true, ".pdf": true,
		".docx": true, ".json": true, ".csv": true,
	}
	if !allowed[ext] {
		writeError(w, http.StatusBadRequest, fmt.Sprintf("Unsupported file type '%s'. Allowed: .xlsx, .xls, .pdf, .docx, .json, .csv", ext))
		return
	}

	content, err := io.ReadAll(file)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "failed to read file: "+err.Error())
		return
	}

	fileID := uuid.New().String()
	uploadsMu.Lock()
	uploadsStore[fileID] = &uploadEntry{
		Filename:    filename,
		Content:     content,
		ContentType: header.Header.Get("Content-Type"),
		Size:        len(content),
	}
	uploadsMu.Unlock()

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"file_id":  fileID,
		"filename": filename,
		"size":     len(content),
	})
}

func handleParse(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var req struct {
		FileID string `json:"file_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}

	uploadsMu.RLock()
	entry, ok := uploadsStore[req.FileID]
	uploadsMu.RUnlock()
	if !ok {
		writeError(w, http.StatusNotFound, "File not found. Upload first.")
		return
	}

	svc := generator.GetService(anthropicURL())
	sections, err := svc.ParseDocument(entry.Content, entry.Filename)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "parse failed: "+err.Error())
		return
	}

	parseID := uuid.New().String()
	uploadsMu.Lock()
	entry.Sections = sections
	entry.ParseID = parseID
	uploadsMu.Unlock()

	// Build response summary
	type sectionSummary struct {
		Name     string   `json:"name"`
		RowCount int      `json:"row_count"`
		Headers  []string `json:"headers"`
	}
	var summaries []sectionSummary
	for _, s := range sections {
		h := s.Headers
		if len(h) > 6 {
			h = h[:6]
		}
		summaries = append(summaries, sectionSummary{
			Name:     s.Name,
			RowCount: s.RowCount,
			Headers:  h,
		})
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"parse_id":      parseID,
		"section_count": len(sections),
		"sections":      summaries,
	})
}

func handleGenerate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	// Resolve API key: env var takes precedence over request header
	apiKey := os.Getenv("ANTHROPIC_API_KEY")
	if apiKey == "" {
		apiKey = r.Header.Get("X-Anthropic-Key")
	}
	if apiKey == "" {
		writeError(w, http.StatusBadRequest, "No API key provided. Set ANTHROPIC_API_KEY env var or pass X-Anthropic-Key header.")
		return
	}

	var (
		fileBytes     []byte
		filename      string
		userContext   string
		samplePayload string
		fileID        string
	)

	ct := r.Header.Get("Content-Type")
	if strings.Contains(ct, "multipart/form-data") {
		// Single-step: file uploaded directly in this request
		if err := r.ParseMultipartForm(32 << 20); err != nil {
			writeError(w, http.StatusBadRequest, "failed to parse form: "+err.Error())
			return
		}
		file, header, err := r.FormFile("file")
		if err != nil {
			writeError(w, http.StatusBadRequest, "missing 'file' field: "+err.Error())
			return
		}
		defer file.Close()
		fileBytes, err = io.ReadAll(file)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "failed to read file: "+err.Error())
			return
		}
		filename = header.Filename
		userContext = r.FormValue("context")
		samplePayload = r.FormValue("sample_payload")
	} else {
		// Two-step: file already uploaded, reference by file_id
		var req struct {
			FileID        string `json:"file_id"`
			Context       string `json:"context"`
			SamplePayload string `json:"sample_payload"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
			return
		}
		if req.FileID == "" {
			writeError(w, http.StatusBadRequest, "missing 'file_id' — upload first via /api/upload or send file as multipart/form-data")
			return
		}
		uploadsMu.RLock()
		entry, ok := uploadsStore[req.FileID]
		uploadsMu.RUnlock()
		if !ok {
			writeError(w, http.StatusNotFound, "File not found. Upload first via /api/upload.")
			return
		}
		fileBytes = entry.Content
		filename = entry.Filename
		fileID = req.FileID
		userContext = req.Context
		samplePayload = req.SamplePayload
	}

	svc := generator.GetService(anthropicURL())

	// Reuse pre-parsed sections when available (two-step flow)
	var sections []generator.Section
	if fileID != "" {
		uploadsMu.RLock()
		entry := uploadsStore[fileID]
		uploadsMu.RUnlock()
		sections = entry.Sections
	}
	if len(sections) == 0 {
		var err error
		sections, err = svc.ParseDocument(fileBytes, filename)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "parse failed: "+err.Error())
			return
		}
		if fileID != "" {
			uploadsMu.Lock()
			uploadsStore[fileID].Sections = sections
			uploadsMu.Unlock()
		}
	}
	if len(sections) == 0 {
		writeError(w, http.StatusBadRequest, "No sections found in document.")
		return
	}

	extracted, err := svc.ExtractAllSections(r.Context(), sections, userContext, apiKey)
	if err != nil {
		log.Printf("ExtractAllSections error: %v", err)
		writeError(w, http.StatusInternalServerError, "extraction failed: "+err.Error())
		return
	}

	workflow := svc.AssembleWorkflow(extracted, samplePayload)
	validation := svc.ValidateWorkflow(workflow)

	workflowID := uuid.New().String()
	workflowsMu.Lock()
	workflowsStore[workflowID] = &workflowEntry{
		Workflow:   workflow,
		Validation: validation,
		FileID:     fileID,
	}
	workflowsMu.Unlock()

	writeJSON(w, http.StatusOK, workflow)
}

func handleValidate(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	var body map[string]interface{}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
		return
	}

	wf, ok := body["workflow"].(map[string]interface{})
	if !ok {
		wf = body
	}

	svc := generator.GetService(anthropicURL())
	result := svc.ValidateWorkflow(wf)
	writeJSON(w, http.StatusOK, result)
}

func handleWorkflow(w http.ResponseWriter, r *http.Request) {
	// Extract workflow ID from path: /api/workflow/<id>
	id := strings.TrimPrefix(r.URL.Path, "/api/workflow/")
	if id == "" {
		writeError(w, http.StatusBadRequest, "missing workflow ID")
		return
	}

	switch r.Method {
	case http.MethodGet:
		workflowsMu.RLock()
		entry, ok := workflowsStore[id]
		workflowsMu.RUnlock()
		if !ok {
			writeError(w, http.StatusNotFound, "Workflow not found.")
			return
		}
		writeJSON(w, http.StatusOK, entry.Workflow)

	case http.MethodPut:
		var req struct {
			Workflow map[string]interface{} `json:"workflow"`
		}
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON: "+err.Error())
			return
		}

		workflowsMu.RLock()
		entry, ok := workflowsStore[id]
		workflowsMu.RUnlock()
		if !ok {
			writeError(w, http.StatusNotFound, "Workflow not found.")
			return
		}

		svc := generator.GetService(anthropicURL())
		validation := svc.ValidateWorkflow(req.Workflow)

		workflowsMu.Lock()
		entry.Workflow = req.Workflow
		entry.Validation = validation
		workflowsMu.Unlock()

		writeJSON(w, http.StatusOK, req.Workflow)

	default:
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
	}
}

func handleExport(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeError(w, http.StatusMethodNotAllowed, "method not allowed")
		return
	}

	id := strings.TrimPrefix(r.URL.Path, "/api/export/")
	if id == "" {
		writeError(w, http.StatusBadRequest, "missing workflow ID")
		return
	}

	workflowsMu.RLock()
	entry, ok := workflowsStore[id]
	workflowsMu.RUnlock()
	if !ok {
		writeError(w, http.StatusNotFound, "Workflow not found.")
		return
	}

	data, err := json.MarshalIndent(entry.Workflow, "", "  ")
	if err != nil {
		writeError(w, http.StatusInternalServerError, "serialisation error: "+err.Error())
		return
	}

	shortID := id
	if len(shortID) > 8 {
		shortID = shortID[:8]
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="workflow_%s.workflow"`, shortID))
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

// ─────────────────────────────────────────────────────────────────────────────
// Config helpers
// ─────────────────────────────────────────────────────────────────────────────

func anthropicURL() string {
	if u := os.Getenv("ANTHROPIC_URL"); u != "" {
		return u
	}
	return "https://api.anthropic.com/v1"
}
