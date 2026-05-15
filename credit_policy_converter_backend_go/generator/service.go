package generator

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"sync"

	"github.com/google/uuid"
)

// ─────────────────────────────────────────────────────────────────────────────
// UUID helper
// ─────────────────────────────────────────────────────────────────────────────

func newID() string {
	return uuid.New().String()
}

// ─────────────────────────────────────────────────────────────────────────────
// SERVICE IMPLEMENTATION
// ─────────────────────────────────────────────────────────────────────────────

type svc struct {
	anthropicURL string
	httpClient   *http.Client
}

func (s *svc) ParseDocument(fileBytes []byte, filename string) ([]Section, error) {
	return ParseDocument(fileBytes, filename)
}

func (s *svc) ValidateWorkflow(workflow map[string]interface{}) ValidationResult {
	return validateWorkflow(workflow)
}

// ─────────────────────────────────────────────────────────────────────────────
// CLAUDE API CLIENT
// ─────────────────────────────────────────────────────────────────────────────

type claudeRequest struct {
	Model     string           `json:"model"`
	MaxTokens int              `json:"max_tokens"`
	Thinking  *claudeThinking  `json:"thinking,omitempty"`
	Messages  []claudeMessage  `json:"messages"`
}

type claudeThinking struct {
	Type         string `json:"type"`
	BudgetTokens int    `json:"budget_tokens"`
}

type claudeMessage struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

type claudeResponse struct {
	Content []struct {
		Type string `json:"type"`
		Text string `json:"text"`
	} `json:"content"`
	Error *struct {
		Message string `json:"message"`
	} `json:"error"`
}

// callClaude sends a prompt to Claude and returns the text response.
// useThinking=true enables extended thinking (better quality, slower).
func (s *svc) callClaude(ctx context.Context, prompt string, maxTokens int, apiKey string) (string, error) {
	return s.callClaudeOpts(ctx, prompt, maxTokens, apiKey, true)
}

func (s *svc) callClaudeNoThinking(ctx context.Context, prompt string, maxTokens int, apiKey string) (string, error) {
	return s.callClaudeOpts(ctx, prompt, maxTokens, apiKey, false)
}

func (s *svc) callClaudeOpts(ctx context.Context, prompt string, maxTokens int, apiKey string, useThinking bool) (string, error) {
	const model = "claude-opus-4-6"

	var reqBody claudeRequest
	if useThinking {
		thinkingBudget := maxTokens * 4 / 10
		if thinkingBudget < 1024 {
			thinkingBudget = 1024
		}
		reqBody = claudeRequest{
			Model:     model,
			MaxTokens: thinkingBudget + maxTokens,
			Thinking:  &claudeThinking{Type: "enabled", BudgetTokens: thinkingBudget},
			Messages:  []claudeMessage{{Role: "user", Content: prompt}},
		}
	} else {
		reqBody = claudeRequest{
			Model:     model,
			MaxTokens: maxTokens,
			Messages:  []claudeMessage{{Role: "user", Content: prompt}},
		}
	}

	text, err := s.doClaudeRequest(ctx, s.httpClient, reqBody, apiKey)
	if err != nil && useThinking {
		// Fallback: retry without extended thinking
		reqBody.Thinking = nil
		reqBody.MaxTokens = maxTokens
		var err2 error
		text, err2 = s.doClaudeRequest(ctx, s.httpClient, reqBody, apiKey)
		if err2 != nil {
			return "", fmt.Errorf("claude API error: %w (thinking fallback: %v)", err, err2)
		}
	} else if err != nil {
		return "", fmt.Errorf("claude API error: %w", err)
	}
	return text, nil
}

func (s *svc) doClaudeRequest(ctx context.Context, client *http.Client, req claudeRequest, apiKey string) (string, error) {
	body, err := json.Marshal(req)
	if err != nil {
		return "", err
	}

	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, s.anthropicURL+"/messages", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	httpReq.Header.Set("Content-Type", "application/json")
	httpReq.Header.Set("x-api-key", apiKey)
	httpReq.Header.Set("anthropic-version", "2023-06-01")
	if req.Thinking != nil {
		httpReq.Header.Set("anthropic-beta", "interleaved-thinking-2025-05-14")
	}

	resp, err := client.Do(httpReq)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()

	respBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", err
	}

	var claudeResp claudeResponse
	if err := json.Unmarshal(respBytes, &claudeResp); err != nil {
		return "", fmt.Errorf("decode response: %w", err)
	}
	if claudeResp.Error != nil {
		return "", fmt.Errorf("claude error: %s", claudeResp.Error.Message)
	}

	for _, block := range claudeResp.Content {
		if block.Type == "text" {
			return block.Text, nil
		}
	}
	return "", fmt.Errorf("no text block in Claude response")
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION EXTRACTION PIPELINE
// ─────────────────────────────────────────────────────────────────────────────

// ExtractAllSections classifies sections and calls Claude to extract rules.
func (s *svc) ExtractAllSections(ctx context.Context, sections []Section, userContext, apiKey string) (*ExtractedData, error) {
	result := &ExtractedData{
		GoNoGoRules:            []map[string]interface{}{},
		SurrogateRules:         []map[string]interface{}{},
		EligibilityExpressions: []map[string]interface{}{},
		ScorecardExpressions:   []map[string]interface{}{},
		NamedRulesets:          []NamedRuleset{},
		NamedModelsets:         []NamedModelset{},
	}

	namedRulesetMap := make(map[string][]map[string]interface{})
	namedRulesetOrder := []string{} // tracks insertion order for deterministic output

	namedModelsetMap := make(map[string][]map[string]interface{})
	namedModelsetOrder := []string{} // tracks insertion order for deterministic output

	// Build context prefix
	contextBlock := ""
	if strings.TrimSpace(userContext) != "" {
		contextBlock = "\n\nUSER-PROVIDED CONTEXT (follow these instructions while extracting rules):\n" +
			strings.TrimSpace(userContext) + "\n"
	}

	inject := func(prompt string) string {
		return prompt + contextBlock
	}

	// Step 1: Classify sections
	var summaryLines []string
	for _, s := range sections {
		hPreview := ""
		if len(s.Headers) > 0 {
			limit := 6
			if len(s.Headers) < limit {
				limit = len(s.Headers)
			}
			hPreview = ", headers: " + strings.Join(s.Headers[:limit], ", ")
		}
		summaryLines = append(summaryLines, fmt.Sprintf("- %s: %d rows%s", s.Name, s.RowCount, hPreview))
	}

	// Single-section PDF/DOCX fallback: the parser returned the whole document as one
	// unnamed section. Bypass LLM classification — the section name ("Policy Document"
	// or "Document") looks like metadata to the classifier, causing it to be skipped.
	isSingleFallback := len(sections) == 1 &&
		(sections[0].Name == "Policy Document" || sections[0].Name == "Document")

	var sectionTypes map[string]string
	if isSingleFallback {
		sectionTypes = map[string]string{sections[0].Name: "go_no_go"}
	} else {
		classifyResp, classErr := s.callClaudeNoThinking(ctx, getClassifySectionsPrompt(strings.Join(summaryLines, "\n")), 2048, apiKey)
		if classErr == nil {
			parsed := extractJSON(classifyResp)
			if m, ok := parsed.(map[string]interface{}); ok && len(m) > 0 {
				rawTypes := make(map[string]string)
				rawLower := make(map[string]string)
				for k, v := range m {
					if vs, ok := v.(string); ok {
						rawTypes[k] = vs
						rawLower[strings.ToLower(strings.TrimSpace(k))] = vs
					}
				}
				sectionTypes = make(map[string]string)
				nameFallback := classifyByName(sections)
				for _, sec := range sections {
					if t, ok := rawTypes[sec.Name]; ok {
						sectionTypes[sec.Name] = t
					} else if t, ok := rawLower[strings.ToLower(strings.TrimSpace(sec.Name))]; ok {
						sectionTypes[sec.Name] = t
					} else {
						sectionTypes[sec.Name] = nameFallback[sec.Name]
					}
				}
			}
		}
		if len(sectionTypes) == 0 {
			sectionTypes = classifyByName(sections)
		}
	}
	log.Printf("[debug] section_types: %v", sectionTypes)

	// Step 2: Process each section concurrently
	// NOTE: "exposure" removed — exposure sections contain rules and should be processed as modelset
	skipTypes := map[string]bool{"metadata": true, "pre_read": true, "change_history": true}

	type sectionResult struct {
		idx          int
		rsKey        string
		stype        string
		rules        []map[string]interface{}
		modelExprs   []map[string]interface{}
		eligExprs    []map[string]interface{}
		scorecardExprs []map[string]interface{}
	}

	resultsCh := make(chan sectionResult, len(sections))
	var wg sync.WaitGroup

	for idx, sec := range sections {
		stype, ok := sectionTypes[sec.Name]
		if !ok {
			stype = "go_no_go"
		}
		text := sec.Text
		if text == "" || skipTypes[stype] {
			continue
		}
		if len(text) > 24000 {
			text = text[:24000]
		}
		rsKey := sanitizeName(sec.Name)

		wg.Add(1)
		go func(idx int, sec Section, stype, rsKey, text string) {
			defer wg.Done()
			res := sectionResult{idx: idx, rsKey: rsKey, stype: stype}

			switch {
			case bureauCategoryTypes[stype] || stype == "go_no_go" || stype == "surrogate_policy" || stype == "common_rules":
				var prompt string
				if bureauCategoryTypes[stype] {
					prompt = getBureauRulesetPrompt(text, stype)
				} else if stype == "surrogate_policy" {
					prompt = getSurrogatePolicyPrompt(text)
				} else {
					prompt = getGoNoGoPrompt(text)
				}
				raw, callErr := s.callClaude(ctx, inject(prompt), 4096, apiKey)
				if callErr != nil {
					log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
					break
				}
				if rules, ok := toSliceOfMaps(extractJSON(raw)); ok && len(rules) > 0 {
					res.rules = rules
				}
				// Single-section fallback: also extract eligibility from the same text.
				if isSingleFallback && len(text) > 4000 {
					eligRaw, eligErr := s.callClaude(ctx, inject(getEligibilityPrompt(text)), 16384, apiKey)
					if eligErr == nil {
						if exprs, ok2 := toSliceOfMaps(extractJSON(eligRaw)); ok2 && len(exprs) > 0 {
							res.eligExprs = exprs
						}
					}
				}

			case stype == "modelset":
				raw, callErr := s.callClaude(ctx, inject(getModelsetPrompt(text, rsKey)), 16384, apiKey)
				if callErr != nil {
					log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
					break
				}
				if exprs, ok := toSliceOfMaps(extractJSON(raw)); ok && len(exprs) > 0 {
					res.modelExprs = exprs
				}

			case stype == "eligibility":
				raw, callErr := s.callClaude(ctx, inject(getEligibilityPrompt(text)), 16384, apiKey)
				if callErr != nil {
					log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
					break
				}
				if exprs, ok := toSliceOfMaps(extractJSON(raw)); ok {
					res.eligExprs = exprs
				}

			case stype == "scorecard":
				raw, callErr := s.callClaude(ctx, inject(getScorecardPrompt(text)), 16384, apiKey)
				if callErr != nil {
					log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
					break
				}
				if exprs, ok := toSliceOfMaps(extractJSON(raw)); ok {
					res.scorecardExprs = exprs
				}
			}

			resultsCh <- res
		}(idx, sec, stype, rsKey, text)
	}

	wg.Wait()
	close(resultsCh)

	// Collect results preserving document section order
	type indexedResult struct {
		idx int
		res sectionResult
	}
	collected := make([]indexedResult, 0, len(sections))
	for res := range resultsCh {
		collected = append(collected, indexedResult{res.idx, res})
	}
	// Sort by original section index to maintain order
	for i := 1; i < len(collected); i++ {
		for j := i; j > 0 && collected[j].idx < collected[j-1].idx; j-- {
			collected[j], collected[j-1] = collected[j-1], collected[j]
		}
	}
	for _, ir := range collected {
		res := ir.res
		if len(res.rules) > 0 {
			if _, exists := namedRulesetMap[res.rsKey]; !exists {
				namedRulesetOrder = append(namedRulesetOrder, res.rsKey)
			}
			namedRulesetMap[res.rsKey] = append(namedRulesetMap[res.rsKey], res.rules...)
		}
		if len(res.modelExprs) > 0 {
			if _, exists := namedModelsetMap[res.rsKey]; !exists {
				namedModelsetOrder = append(namedModelsetOrder, res.rsKey)
			}
			namedModelsetMap[res.rsKey] = append(namedModelsetMap[res.rsKey], res.modelExprs...)
		}
		result.EligibilityExpressions = append(result.EligibilityExpressions, res.eligExprs...)
		result.ScorecardExpressions = append(result.ScorecardExpressions, res.scorecardExprs...)
	}

	// Build ordered named rulesets / modelsets (preserving document section order)
	for _, rsName := range namedRulesetOrder {
		result.NamedRulesets = append(result.NamedRulesets, NamedRuleset{Name: rsName, Rules: namedRulesetMap[rsName]})
	}
	for _, msName := range namedModelsetOrder {
		result.NamedModelsets = append(result.NamedModelsets, NamedModelset{Name: msName, Expressions: namedModelsetMap[msName]})
	}

	return result, nil
}

// toSliceOfMaps asserts a JSON-parsed value as []map[string]interface{}.
func toSliceOfMaps(v interface{}) ([]map[string]interface{}, bool) {
	arr, ok := v.([]interface{})
	if !ok {
		return nil, false
	}
	var result []map[string]interface{}
	for _, item := range arr {
		if m, ok := item.(map[string]interface{}); ok {
			result = append(result, m)
		}
	}
	return result, true
}

// sanitizeName converts a section heading to snake_case for use as a node name.
func sanitizeName(name string) string {
	n := strings.ToLower(strings.TrimSpace(name))
	re := regexp.MustCompile(`[^a-z0-9]+`)
	n = re.ReplaceAllString(n, "_")
	n = strings.Trim(n, "_")
	// Strip leading numeric prefix (e.g. "1_core_..." → "core_...")
	leadingNum := regexp.MustCompile(`^\d+_`)
	n = leadingNum.ReplaceAllString(n, "")
	n = strings.Trim(n, "_")
	if n == "" {
		return "policy_checks"
	}
	return n
}

// ─────────────────────────────────────────────────────────────────────────────
// WORKFLOW ASSEMBLER
// ─────────────────────────────────────────────────────────────────────────────

const (
	hGap          = 120
	baseNarrow    = 200
	baseMedium    = 300
	baseRuleset   = 300
	ruleExtra     = 3
	yMain         = 0
	yApproved     = -320
	yRejected     = 320
	modelSetLimit = 180
)

// AssembleWorkflow builds the complete BRE workflow JSON from extracted data.
func (s *svc) AssembleWorkflow(extracted *ExtractedData, samplePayload string) map[string]interface{} {
	// Build ordered rulesets
	var allRulesets []map[string]interface{}
	for _, rs := range extracted.NamedRulesets {
		if len(rs.Rules) > 0 {
			allRulesets = append(allRulesets, map[string]interface{}{
				"name":  rs.Name,
				"rules": rs.Rules,
			})
		}
	}
	if len(extracted.GoNoGoRules) > 0 {
		allRulesets = append(allRulesets, map[string]interface{}{
			"name":  "go_no_go_checks",
			"rules": extracted.GoNoGoRules,
		})
	}
	if len(extracted.SurrogateRules) > 0 {
		allRulesets = append(allRulesets, map[string]interface{}{
			"name":  "surrogate_policy_checks",
			"rules": extracted.SurrogateRules,
		})
	}

	eligExprs := extracted.EligibilityExpressions
	scorecardExprs := extracted.ScorecardExpressions
	namedModelsets := extracted.NamedModelsets

	// Collect all condition text to detect cross-node references
	condText := collectConditions(extracted)
	hasBankVars := regexp.MustCompile(`\bbank\.`).MatchString(condText)

	// Build a set of input variable names so expression names that clash can be renamed.
	inputVarSet := map[string]bool{}
	for _, m := range regexp.MustCompile(`\binput\.([a-zA-Z_][a-zA-Z0-9_]*)\b`).FindAllStringSubmatch(condText, -1) {
		inputVarSet[m[1]] = true
	}
	// dedupExprs removes duplicate expression names (keeps first) and renames any
	// expression whose name matches an input variable name by appending "_calc".
	// It also updates condition strings in the same batch so intra-modelSet
	// references remain consistent after renaming.
	dedupExprs := func(exprs []map[string]interface{}) []map[string]interface{} {
		// Pass 1: build rename map for names that clash with input variables.
		renameMap := map[string]string{}
		for _, e := range exprs {
			oldName := strVal(e, "name", "")
			if inputVarSet[oldName] {
				renameMap[oldName] = oldName + "_calc"
			}
		}

		// Pass 2: apply renames to names and propagate into condition strings.
		seen := map[string]bool{}
		var out []map[string]interface{}
		for _, e := range exprs {
			name := strVal(e, "name", "")
			if newName, ok := renameMap[name]; ok {
				name = newName
				e = copyMap(e)
				e["name"] = name
			}
			// Update any references to renamed expressions inside condition text.
			if len(renameMap) > 0 {
				cond := strVal(e, "condition", "")
				if cond != "" {
					updated := cond
					for oldName, newName := range renameMap {
						re := regexp.MustCompile(`\b` + regexp.QuoteMeta(oldName) + `\b`)
						updated = re.ReplaceAllString(updated, newName)
					}
					if updated != cond {
						if e["name"] == name && cond == strVal(e, "condition", "") {
							e = copyMap(e)
						}
						e["condition"] = updated
					}
				}
			}
			if name != "" && !seen[name] {
				seen[name] = true
				out = append(out, e)
			}
		}
		return out
	}
	// fixModelSetRefs corrects stale bare-name references inside a modelSet's
	// decision table headers, matrix headers, and expression conditions. When the
	// LLM names an expression "foo_calc" but references it as "foo" in DT headers
	// or sibling conditions, this pass aligns those references to the actual name.
	fixModelSetRefs := func(exprs []map[string]interface{}) []map[string]interface{} {
		nameSet := map[string]bool{}
		for _, e := range exprs {
			if n := strVal(e, "name", ""); n != "" {
				nameSet[n] = true
			}
		}
		aliasMap := map[string]string{}
		for n := range nameSet {
			if strings.HasSuffix(n, "_calc") {
				bare := strings.TrimSuffix(n, "_calc")
				if !nameSet[bare] {
					aliasMap[bare] = n
				}
			}
		}
		if len(aliasMap) == 0 {
			return exprs
		}
		applyAlias := func(s string) string {
			if strings.Contains(s, ".") {
				return s
			}
			if renamed, ok := aliasMap[s]; ok {
				return renamed
			}
			return s
		}
		applyAliasCond := func(s string) string {
			for old, newName := range aliasMap {
				re := regexp.MustCompile(`\b` + regexp.QuoteMeta(old) + `\b`)
				s = re.ReplaceAllString(s, newName)
			}
			return s
		}
		var out []map[string]interface{}
		for _, e := range exprs {
			switch strVal(e, "type", "expression") {
			case "expression":
				if cond := strVal(e, "condition", ""); cond != "" {
					if u := applyAliasCond(cond); u != cond {
						e = copyMap(e)
						e["condition"] = u
					}
				}
			case "decisionTable":
				if dt, ok := e["decisionTableRules"].(map[string]interface{}); ok {
					dtCopy := copyMap(dt)
					dtChanged := false
					if hs := toIfaceSlice(dt["headers"]); hs != nil {
						newHs := make([]interface{}, len(hs))
						for i, h := range hs {
							if s, ok := h.(string); ok {
								newHs[i] = applyAlias(s)
								if newHs[i] != h {
									dtChanged = true
								}
							} else {
								newHs[i] = h
							}
						}
						if dtChanged {
							dtCopy["headers"] = newHs
						}
					}
					if rows := toIfaceSlice(dt["rows"]); rows != nil {
						newRows := make([]interface{}, len(rows))
						rowsChanged := false
						for ri, row := range rows {
							rowMap, ok := row.(map[string]interface{})
							if !ok {
								newRows[ri] = row
								continue
							}
							cols := toIfaceSlice(rowMap["columns"])
							newCols := make([]interface{}, len(cols))
							colsChanged := false
							for ci, col := range cols {
								colMap, ok := col.(map[string]interface{})
								if !ok {
									newCols[ci] = col
									continue
								}
								colName := strVal(colMap, "name", "")
								if newName := applyAlias(colName); newName != colName {
									colCopy := copyMap(colMap)
									colCopy["name"] = newName
									newCols[ci] = colCopy
									colsChanged = true
								} else {
									newCols[ci] = col
								}
							}
							if colsChanged {
								rowCopy := copyMap(rowMap)
								rowCopy["columns"] = newCols
								newRows[ri] = rowCopy
								rowsChanged = true
							} else {
								newRows[ri] = row
							}
						}
						if rowsChanged {
							dtCopy["rows"] = newRows
							dtChanged = true
						}
					}
					if dtChanged {
						e = copyMap(e)
						e["decisionTableRules"] = dtCopy
					}
				}
			case "matrix":
				if mat, ok := e["matrix"].(map[string]interface{}); ok {
					matCopy := copyMap(mat)
					matChanged := false
					if rows := toIfaceSlice(mat["rows"]); rows != nil {
						newRows := make([]interface{}, len(rows))
						rowsChanged := false
						for ri, row := range rows {
							rowMap, ok := row.(map[string]interface{})
							if !ok {
								newRows[ri] = row
								continue
							}
							h := strVal(rowMap, "header", "")
							if nh := applyAlias(h); nh != h {
								rowCopy := copyMap(rowMap)
								rowCopy["header"] = nh
								newRows[ri] = rowCopy
								rowsChanged = true
							} else {
								newRows[ri] = row
							}
						}
						if rowsChanged {
							matCopy["rows"] = newRows
							matChanged = true
						}
					}
					if cols := toIfaceSlice(mat["columns"]); cols != nil {
						newCols := make([]interface{}, len(cols))
						colsChanged := false
						for ci, col := range cols {
							colMap, ok := col.(map[string]interface{})
							if !ok {
								newCols[ci] = col
								continue
							}
							h := strVal(colMap, "header", "")
							if nh := applyAlias(h); nh != h {
								colCopy := copyMap(colMap)
								colCopy["header"] = nh
								newCols[ci] = colCopy
								colsChanged = true
							} else {
								newCols[ci] = col
							}
						}
						if colsChanged {
							matCopy["columns"] = newCols
							matChanged = true
						}
					}
					if matChanged {
						e = copyMap(e)
						e["matrix"] = matCopy
					}
				}
			}
			out = append(out, e)
		}
		return out
	}

	eligExprs = fixModelSetRefs(dedupExprs(eligExprs))
	scorecardExprs = fixModelSetRefs(dedupExprs(scorecardExprs))

	var modelExprs []map[string]interface{}
	if strings.Contains(condText, "model.hit_no_hit") {
		modelExprs = append(modelExprs, map[string]interface{}{
			"name": "hit_no_hit", "condition": "bureau.bureauscore != nil", "type": "expression",
		})
	}
	if strings.Contains(condText, "model.age_at_maturity") {
		modelExprs = append(modelExprs, map[string]interface{}{
			"name": "age_at_maturity", "condition": "input.age + 3", "type": "expression",
		})
	}

	xCursor := 0
	place := func(cardWidth int) int {
		pos := xCursor
		xCursor += cardWidth + hGap
		return pos
	}
	rulesetWidth := func(rules []map[string]interface{}) int {
		return baseRuleset + ruleExtra*len(rules)
	}

	firstRulesetRef := func() map[string]interface{} {
		if len(allRulesets) > 0 {
			return map[string]interface{}{"name": allRulesets[0]["name"], "type": "ruleSet"}
		}
		// No rulesets: skip final_decision, route directly to eligibility or end_approved.
		if len(eligExprs) > 0 {
			return map[string]interface{}{"name": "eligibility", "type": "modelSet"}
		}
		return map[string]interface{}{"name": "end_approved", "type": "end"}
	}

	firstNamedModelsetOrRuleset := func() map[string]interface{} {
		if len(namedModelsets) > 0 {
			return map[string]interface{}{"name": namedModelsets[0].Name, "type": "modelSet"}
		}
		return firstRulesetRef()
	}

	afterDatasource := func() map[string]interface{} {
		if len(scorecardExprs) > 0 {
			return map[string]interface{}{"name": "scorecard", "type": "modelSet"}
		}
		if len(modelExprs) > 0 {
			return map[string]interface{}{"name": "model", "type": "modelSet"}
		}
		return firstNamedModelsetOrRuleset()
	}()

	afterScorecard := func() map[string]interface{} {
		if len(modelExprs) > 0 {
			return map[string]interface{}{"name": "model", "type": "modelSet"}
		}
		return firstNamedModelsetOrRuleset()
	}()

	var nodes []interface{}

	// appendModelSet builds one or more modelSet nodes for the given expressions,
	// splitting into chunks of modelSetLimit. Chunks are named baseName, baseName_2, …
	// The last chunk's nextState is finalNext; each preceding chunk points to the next.
	appendModelSet := func(baseName string, exprs []map[string]interface{}, finalNext map[string]interface{}) {
		if len(exprs) == 0 {
			return
		}
		var chunkNames []string
		var chunkExprs [][]map[string]interface{}
		for i := 0; i < len(exprs); i += modelSetLimit {
			end := i + modelSetLimit
			if end > len(exprs) {
				end = len(exprs)
			}
			name := baseName
			if i > 0 {
				name = fmt.Sprintf("%s_%d", baseName, i/modelSetLimit+1)
			}
			chunkNames = append(chunkNames, name)
			chunkExprs = append(chunkExprs, exprs[i:end])
		}
		for ci := range chunkNames {
			var next map[string]interface{}
			if ci+1 < len(chunkNames) {
				next = map[string]interface{}{"name": chunkNames[ci+1], "type": "modelSet"}
			} else {
				next = finalNext
			}
			nodes = append(nodes, buildModelSet(chunkNames[ci], place(baseMedium), yMain, chunkExprs[ci], next))
		}
	}

	// 1. Start node
	datasourceName := "Source_Node"
	nodes = append(nodes, map[string]interface{}{
		"type": "start",
		"name": "Start",
		"metadata": map[string]interface{}{"x": place(baseNarrow), "y": yMain, "nodeColor": 1},
		"nextState": map[string]interface{}{"name": datasourceName, "type": "dataSource"},
	})

	// 2. DataSource node
	sources := []interface{}{
		map[string]interface{}{"name": "bureau", "id": 41238, "seqNo": 0, "type": "finboxSource", "tag": newID()},
	}
	if hasBankVars {
		sources = append(sources, map[string]interface{}{
			"name": "bank", "id": 41239, "seqNo": 1, "type": "finboxSource", "tag": newID(),
		})
	}
	nodes = append(nodes, map[string]interface{}{
		"type":      "dataSource",
		"name":      datasourceName,
		"tag":       newID(),
		"sources":   sources,
		"metadata":  map[string]interface{}{"x": place(baseNarrow), "y": yMain, "nodeColor": 1},
		"nextState": afterDatasource,
	})

	// 3. Scorecard modelSet
	appendModelSet("scorecard", scorecardExprs, afterScorecard)

	// 4. Model modelSet
	appendModelSet("model", modelExprs, firstNamedModelsetOrRuleset())

	// 5. Named modelsets (between model and first ruleset)
	for i, ms := range namedModelsets {
		var msNext map[string]interface{}
		if i+1 < len(namedModelsets) {
			msNext = map[string]interface{}{"name": namedModelsets[i+1].Name, "type": "modelSet"}
		} else {
			msNext = firstRulesetRef()
		}
		exprs := fixModelSetRefs(dedupExprs(ms.Expressions))
		appendModelSet(ms.Name, exprs, msNext)
	}

	// 6. Rulesets in order
	for i, rs := range allRulesets {
		rsName := rs["name"].(string)
		rules := toMapSlice(rs["rules"])
		sw := rsName + "-switch"

		var nextNode map[string]interface{}
		if i+1 < len(allRulesets) {
			nextNode = map[string]interface{}{"name": allRulesets[i+1]["name"], "type": "ruleSet"}
		} else {
			nextNode = map[string]interface{}{"name": "final_decision", "type": "branch"}
		}

		nodes = append(nodes, buildRuleSet(rsName, place(rulesetWidth(rules)), yMain, rules, sw))

		if hasActiveRules(rules) {
			nodes = append(nodes, buildActiveSwitch(sw, rules, nextNode))
		} else {
			nodes = append(nodes, buildMutedSwitch(sw, rules, nextNode))
		}
	}

	// 7. Final decision branch — only generated when rulesets exist to aggregate.
	// When there are no rulesets the last modelSet routes directly to eligibility
	// or end_approved via firstRulesetRef, so no branch is needed.
	if len(allRulesets) > 0 {
		fdSw := "final_decision-switch"
		var approveParts []string
		for _, rs := range allRulesets {
			if hasActiveRules(toMapSlice(rs["rules"])) {
				approveParts = append(approveParts, fmt.Sprintf(`%s.decision == "pass"`, rs["name"]))
			}
		}
		approveCond := "true"
		if len(approveParts) > 0 {
			approveCond = strings.Join(approveParts, " and ")
		}

		nodes = append(nodes, map[string]interface{}{
			"type": "branch",
			"name": "final_decision",
			"tag":  newID(),
			"expressions": []interface{}{
				map[string]interface{}{"name": "approve", "id": newID(), "seqNo": 0, "condition": approveCond, "tag": newID()},
				map[string]interface{}{"name": "reject", "id": newID(), "seqNo": 1, "condition": "true", "tag": newID()},
			},
			"metadata":  map[string]interface{}{"x": place(baseMedium), "y": yMain, "nodeColor": 1},
			"nextState": map[string]interface{}{"type": "switch", "name": fdSw},
		})

		var approvePath map[string]interface{}
		if len(eligExprs) > 0 {
			approvePath = map[string]interface{}{"name": "eligibility", "type": "modelSet"}
		} else {
			approvePath = map[string]interface{}{"name": "end_approved", "type": "end"}
		}

		nodes = append(nodes, map[string]interface{}{
			"type": "switch",
			"name": fdSw,
			"dataConditions": []interface{}{
				map[string]interface{}{"name": "approve", "nextState": approvePath},
				map[string]interface{}{"name": "reject", "nextState": map[string]interface{}{"name": "end_rejected", "type": "end"}},
			},
		})
	}

	// 8. Eligibility modelSet
	appendModelSet("eligibility", eligExprs, map[string]interface{}{"name": "end_approved", "type": "end"})

	// 9. End nodes
	endX := xCursor
	nodes = append(nodes, map[string]interface{}{
		"type":          "end",
		"name":          "end_approved",
		"endNodeName":   "approved",
		"tag":           newID(),
		"workflowState": map[string]interface{}{"type": "", "outcomeLogic": nil},
		"decisionNode":  map[string]interface{}{},
		"metadata":      map[string]interface{}{"x": endX, "y": yApproved, "nodeColor": 3},
	})
	if len(allRulesets) > 0 {
		nodes = append(nodes, map[string]interface{}{
			"type":          "end",
			"name":          "end_rejected",
			"endNodeName":   "rejected",
			"tag":           newID(),
			"workflowState": map[string]interface{}{"type": "", "outcomeLogic": nil},
			"decisionNode":  map[string]interface{}{},
			"metadata":      map[string]interface{}{"x": endX, "y": yRejected, "nodeColor": 2},
		})
	}

	// Post-process: add placeholder expressions for any undefined cross-node refs
	nodes = fixUndefinedModelRefs(nodes)

	// 10. Build inputs
	inputs := BuildInputs(nodes, samplePayload)
	inputsIface := make([]interface{}, len(inputs))
	for i, inp := range inputs {
		inputsIface[i] = inp
	}

	return map[string]interface{}{
		"nodes":   nodes,
		"inputs":  inputsIface,
		"outputs": []interface{}{},
		"settings": map[string]interface{}{
			"isNullableInputsAllowed":       true,
			"continueEvalWithDataSourceErr": false,
			"isRejectionBasedRulesetEnable": false,
		},
	}
}

// ─────────────────────────────────────────────────────────────────────────────
// NODE BUILDER HELPERS
// ─────────────────────────────────────────────────────────────────────────────

func buildRuleSet(name string, x, y int, rules []map[string]interface{}, switchName string) map[string]interface{} {
	ruleObjs := make([]interface{}, len(rules))
	for i, r := range rules {
		ruleObjs[i] = map[string]interface{}{
			"name":               strVal(r, "name", fmt.Sprintf("Rule_%d", i+1)),
			"id":                 newID(),
			"seqNo":              i,
			"approveCondition":   strVal(r, "approveCondition", "true"),
			"cantDecideCondition": strVal(r, "cantDecideCondition", ""),
			"muted":              isMuted(r),
			"tag":                newID(),
		}
	}
	return map[string]interface{}{
		"type":     "ruleSet",
		"name":     name,
		"tag":      newID(),
		"rules":    ruleObjs,
		"metadata": map[string]interface{}{"x": x, "y": y, "nodeColor": 1},
		"nextState": map[string]interface{}{"type": "switch", "name": switchName},
	}
}

var emptyDT = map[string]interface{}{"default": "", "headers": nil, "rows": nil}
var emptyMatrix = map[string]interface{}{
	"globalRowIndex":    0,
	"globalColumnIndex": 0,
	"rows":              nil,
	"columns":           nil,
	"values":            nil,
}

func buildModelSet(name string, x, y int, expressions []map[string]interface{}, nextState map[string]interface{}) map[string]interface{} {
	exprObjs := make([]interface{}, len(expressions))
	for i, expr := range expressions {
		etype := strVal(expr, "type", "expression")
		obj := map[string]interface{}{
			"name":  strVal(expr, "name", fmt.Sprintf("expr_%d", i)),
			"id":    newID(),
			"seqNo": i,
			"tag":   newID(),
		}

		switch etype {
		case "matrix":
			expr = enforceMatrixLimits(expr)
			m := expr["matrix"]
			if m == nil {
				m = copyMap(emptyMatrix)
			}
			obj["condition"] = ""
			obj["type"] = "matrix"
			obj["decisionTableRules"] = copyMap(emptyDT)
			obj["matrix"] = m

		case "decisionTable":
			dt := expr["decisionTableRules"]
			if dt == nil {
				dt = copyMap(emptyDT)
			} else {
				dt = quoteDTOutputs(dt)
			}
			obj["condition"] = ""
			obj["type"] = "decisionTable"
			obj["decisionTableRules"] = dt
			obj["matrix"] = copyMap(emptyMatrix)

		default: // expression
			obj["condition"] = strVal(expr, "condition", "")
			obj["type"] = "expression"
			obj["decisionTableRules"] = copyMap(emptyDT)
			obj["matrix"] = copyMap(emptyMatrix)
		}

		exprObjs[i] = obj
	}

	return map[string]interface{}{
		"type":        "modelSet",
		"name":        name,
		"tag":         newID(),
		"expressions": exprObjs,
		"metadata":    map[string]interface{}{"x": x, "y": y, "nodeColor": 1},
		"nextState":   nextState,
	}
}

func buildMutedSwitch(swName string, rules []map[string]interface{}, forward map[string]interface{}) map[string]interface{} {
	conds := []interface{}{
		map[string]interface{}{"name": "pass", "nextState": forward},
		map[string]interface{}{"name": "reject", "nextState": forward},
	}
	if hasCantDecide(rules) {
		conds = append(conds, map[string]interface{}{"name": "cant_decide", "nextState": forward})
	}
	return map[string]interface{}{"type": "switch", "name": swName, "dataConditions": conds}
}

func buildActiveSwitch(swName string, rules []map[string]interface{}, next map[string]interface{}) map[string]interface{} {
	conds := []interface{}{
		map[string]interface{}{"name": "pass", "nextState": next},
		map[string]interface{}{"name": "reject", "nextState": next},
	}
	if hasCantDecide(rules) {
		conds = append(conds, map[string]interface{}{"name": "cant_decide", "nextState": next})
	}
	return map[string]interface{}{"type": "switch", "name": swName, "dataConditions": conds}
}

// ─────────────────────────────────────────────────────────────────────────────
// UTILITY FUNCTIONS
// ─────────────────────────────────────────────────────────────────────────────

func isMuted(rule map[string]interface{}) bool {
	val, ok := rule["muted"]
	if !ok {
		return false
	}
	switch v := val.(type) {
	case bool:
		return v
	case string:
		lower := strings.ToLower(strings.TrimSpace(v))
		return lower == "true" || lower == "1" || lower == "yes"
	case float64:
		return v != 0
	}
	return false
}

func hasCantDecide(rules []map[string]interface{}) bool {
	for _, r := range rules {
		if v, ok := r["cantDecideCondition"].(string); ok && strings.TrimSpace(v) != "" {
			return true
		}
	}
	return false
}

func hasActiveRules(rules []map[string]interface{}) bool {
	for _, r := range rules {
		if !isMuted(r) {
			return true
		}
	}
	return false
}

func strVal(m map[string]interface{}, key, fallback string) string {
	if v, ok := m[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return fallback
}

func copyMap(m map[string]interface{}) map[string]interface{} {
	out := make(map[string]interface{}, len(m))
	for k, v := range m {
		out[k] = v
	}
	return out
}

func toMapSlice(v interface{}) []map[string]interface{} {
	if v == nil {
		return nil
	}
	arr, ok := v.([]map[string]interface{})
	if ok {
		return arr
	}
	iArr, ok := v.([]interface{})
	if !ok {
		return nil
	}
	var result []map[string]interface{}
	for _, item := range iArr {
		if m, ok := item.(map[string]interface{}); ok {
			result = append(result, m)
		}
	}
	return result
}

const (
	matrixMaxRows = 19
	matrixMaxCols = 15
)

// enforceMatrixLimits truncates a matrix expression to the BRE platform limits
// (max 19 data row conditions, max 15 data column conditions).
// Conditions beyond the limit are dropped; the values grid is trimmed accordingly.
func enforceMatrixLimits(expr map[string]interface{}) map[string]interface{} {
	matrixRaw, ok := expr["matrix"]
	if !ok {
		return expr
	}
	matrix, ok := matrixRaw.(map[string]interface{})
	if !ok {
		return expr
	}

	rowsArr, _ := matrix["rows"].([]interface{})
	colsArr, _ := matrix["columns"].([]interface{})
	valuesArr, _ := matrix["values"].([]interface{})

	// Locate data row / no-matches row
	dataRowIdx, noMatchRowIdx := -1, -1
	for i, r := range rowsArr {
		rm, ok := r.(map[string]interface{})
		if !ok {
			continue
		}
		if nm, _ := rm["isNoMatches"].(bool); nm {
			noMatchRowIdx = i
		} else if dataRowIdx < 0 {
			dataRowIdx = i
		}
	}
	dataColIdx, noMatchColIdx := -1, -1
	for i, c := range colsArr {
		cm, ok := c.(map[string]interface{})
		if !ok {
			continue
		}
		if nm, _ := cm["isNoMatches"].(bool); nm {
			noMatchColIdx = i
		} else if dataColIdx < 0 {
			dataColIdx = i
		}
	}
	if dataRowIdx < 0 || dataColIdx < 0 {
		return expr
	}

	dataRow := rowsArr[dataRowIdx].(map[string]interface{})
	dataCol := colsArr[dataColIdx].(map[string]interface{})
	rowConds, _ := dataRow["conditions"].([]interface{})
	colConds, _ := dataCol["conditions"].([]interface{})

	R, C := len(rowConds), len(colConds)
	if R <= matrixMaxRows && C <= matrixMaxCols {
		return expr
	}
	newR, newC := R, C
	if newR > matrixMaxRows {
		newR = matrixMaxRows
	}
	if newC > matrixMaxCols {
		newC = matrixMaxCols
	}

	reindexConds := func(conds []interface{}, n int) []interface{} {
		out := make([]interface{}, n)
		for i := 0; i < n; i++ {
			if m, ok := conds[i].(map[string]interface{}); ok {
				nc := copyMap(m)
				nc["index"] = i
				out[i] = nc
			} else {
				out[i] = conds[i]
			}
		}
		return out
	}

	fixNoMatchConds := func(conds []interface{}, idx int) []interface{} {
		out := make([]interface{}, len(conds))
		for i, c := range conds {
			if cm, ok := c.(map[string]interface{}); ok {
				nc := copyMap(cm)
				nc["index"] = idx
				out[i] = nc
			} else {
				out[i] = c
			}
		}
		return out
	}

	// Rebuild rows
	newRowsArr := make([]interface{}, 0, len(rowsArr))
	for i, r := range rowsArr {
		rm, ok := r.(map[string]interface{})
		if !ok {
			newRowsArr = append(newRowsArr, r)
			continue
		}
		switch i {
		case dataRowIdx:
			nr := copyMap(rm)
			nr["conditions"] = reindexConds(rowConds, newR)
			newRowsArr = append(newRowsArr, nr)
		case noMatchRowIdx:
			nr := copyMap(rm)
			nr["index"] = newR
			if nmConds, ok := rm["conditions"].([]interface{}); ok {
				nr["conditions"] = fixNoMatchConds(nmConds, newR)
			}
			newRowsArr = append(newRowsArr, nr)
		default:
			newRowsArr = append(newRowsArr, r)
		}
	}

	// Rebuild columns
	newColsArr := make([]interface{}, 0, len(colsArr))
	for i, c := range colsArr {
		cm, ok := c.(map[string]interface{})
		if !ok {
			newColsArr = append(newColsArr, c)
			continue
		}
		switch i {
		case dataColIdx:
			nc := copyMap(cm)
			nc["conditions"] = reindexConds(colConds, newC)
			newColsArr = append(newColsArr, nc)
		case noMatchColIdx:
			nc := copyMap(cm)
			nc["index"] = newC
			if nmConds, ok := cm["conditions"].([]interface{}); ok {
				nc["conditions"] = fixNoMatchConds(nmConds, newC)
			}
			newColsArr = append(newColsArr, nc)
		default:
			newColsArr = append(newColsArr, c)
		}
	}

	// Rebuild values grid: keep [0..newR-1][0..newC-1] data cells;
	// last row = original no-matches row (last row of valuesArr);
	// last col per row = original no-matches col (last element of each row).
	origR := len(valuesArr)
	newValues := make([]interface{}, newR+1)
	for i := 0; i <= newR; i++ {
		var srcRow []interface{}
		if i == newR {
			// No-matches row: use original last row
			if origR > 0 {
				srcRow, _ = valuesArr[origR-1].([]interface{})
			}
		} else if i < origR {
			srcRow, _ = valuesArr[i].([]interface{})
		} else if origR > 0 {
			srcRow, _ = valuesArr[origR-1].([]interface{})
		}

		origC := len(srcRow)
		newRow := make([]interface{}, newC+1)
		for j := 0; j <= newC; j++ {
			if j == newC {
				// No-matches col: original last element
				if origC > 0 {
					newRow[j] = srcRow[origC-1]
				} else {
					newRow[j] = ""
				}
			} else if j < origC {
				newRow[j] = srcRow[j]
			} else if origC > 0 {
				newRow[j] = srcRow[origC-1]
			} else {
				newRow[j] = ""
			}
		}
		newValues[i] = newRow
	}

	newMatrix := copyMap(matrix)
	newMatrix["rows"] = newRowsArr
	newMatrix["columns"] = newColsArr
	newMatrix["values"] = newValues
	newMatrix["globalRowIndex"] = newR
	newMatrix["globalColumnIndex"] = newC

	newExpr := copyMap(expr)
	newExpr["matrix"] = newMatrix
	return newExpr
}

// fixUndefinedModelRefs scans all condition strings across nodes for <modelset>.<expr>
// cross-node references. If the modelset exists but lacks the referenced expression,
// a placeholder expression (condition "0") is added to the modelset so the workflow
// compiles. If the modelset does not exist at all, the reference is left as-is
// (the workflow validator will flag it).
func fixUndefinedModelRefs(nodes []interface{}) []interface{} {
	type msInfo struct {
		nodeIdx int
		exprs   map[string]bool
	}
	msMap := make(map[string]*msInfo)
	for idx, n := range nodes {
		node, ok := n.(map[string]interface{})
		if !ok {
			continue
		}
		if node["type"] != "modelSet" {
			continue
		}
		name, _ := node["name"].(string)
		info := &msInfo{nodeIdx: idx, exprs: make(map[string]bool)}
		exprs, _ := node["expressions"].([]interface{})
		for _, e := range exprs {
			if em, ok := e.(map[string]interface{}); ok {
				if en, ok := em["name"].(string); ok && en != "" {
					info.exprs[en] = true
				}
			}
		}
		msMap[name] = info
	}
	if len(msMap) == 0 {
		return nodes
	}

	// Collect all condition-like strings from nodes
	skipPfx := map[string]bool{"bureau": true, "bank": true, "input": true}
	var sb strings.Builder
	for _, n := range nodes {
		node, ok := n.(map[string]interface{})
		if !ok {
			continue
		}
		for _, e := range toIfaceSlice(node["expressions"]) {
			em, ok := e.(map[string]interface{})
			if !ok {
				continue
			}
			sb.WriteString(strVal(em, "condition", "") + " ")
			if dt, ok := em["decisionTableRules"].(map[string]interface{}); ok {
				for _, h := range toIfaceSlice(dt["headers"]) {
					if hs, ok := h.(string); ok {
						sb.WriteString(hs + " ")
					}
				}
			}
		}
		for _, r := range toIfaceSlice(node["rules"]) {
			if rm, ok := r.(map[string]interface{}); ok {
				sb.WriteString(strVal(rm, "approveCondition", "") + " ")
				sb.WriteString(strVal(rm, "cantDecideCondition", "") + " ")
			}
		}
	}

	condRe := regexp.MustCompile(`\b([a-z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b`)
	seenMissing := make(map[string]map[string]bool)
	var missingOrder []struct{ ms, expr string }

	for _, m := range condRe.FindAllStringSubmatch(sb.String(), -1) {
		ns, field := m[1], m[2]
		if skipPfx[ns] {
			continue
		}
		info, exists := msMap[ns]
		if !exists {
			continue
		}
		if info.exprs[field] {
			continue
		}
		if seenMissing[ns] == nil {
			seenMissing[ns] = make(map[string]bool)
		}
		if !seenMissing[ns][field] {
			seenMissing[ns][field] = true
			missingOrder = append(missingOrder, struct{ ms, expr string }{ns, field})
		}
	}

	for _, pair := range missingOrder {
		info := msMap[pair.ms]
		node := nodes[info.nodeIdx].(map[string]interface{})
		exprs, _ := node["expressions"].([]interface{})
		log.Printf("[info] adding missing expression '%s' to modelset '%s'", pair.expr, pair.ms)
		exprs = append(exprs, map[string]interface{}{
			"name":               pair.expr,
			"id":                 newID(),
			"seqNo":              len(exprs),
			"condition":          "0",
			"type":               "expression",
			"decisionTableRules": copyMap(emptyDT),
			"matrix":             copyMap(emptyMatrix),
			"tag":                newID(),
		})
		info.exprs[pair.expr] = true
		node["expressions"] = exprs
		nodes[info.nodeIdx] = node
	}

	return nodes
}

// toIfaceSlice casts interface{} to []interface{}, returning nil on failure.
func toIfaceSlice(v interface{}) []interface{} {
	if v == nil {
		return nil
	}
	s, _ := v.([]interface{})
	return s
}

// quoteDTOutputs wraps text output strings in the decisionTableRules with quotes.
func quoteDTOutputs(dt interface{}) interface{} {
	m, ok := dt.(map[string]interface{})
	if !ok {
		return dt
	}
	out := copyMap(m)
	if def, ok := out["default"]; ok {
		out["default"] = wrapIfText(def)
	}
	if rows, ok := out["rows"].([]interface{}); ok {
		newRows := make([]interface{}, len(rows))
		for i, row := range rows {
			if rowMap, ok := row.(map[string]interface{}); ok {
				nr := copyMap(rowMap)
				if op, ok := nr["output"]; ok {
					nr["output"] = wrapIfText(op)
				}
				newRows[i] = nr
			} else {
				newRows[i] = row
			}
		}
		out["rows"] = newRows
	}
	return out
}

func wrapIfText(v interface{}) interface{} {
	s, ok := v.(string)
	if !ok || s == "" {
		return v
	}
	s = strings.TrimSpace(s)
	if strings.HasPrefix(s, `"`) && strings.HasSuffix(s, `"`) {
		return v // already wrapped
	}
	lower := strings.ToLower(s)
	if lower == "true" || lower == "false" {
		return v // boolean
	}
	// Try numeric parse
	var f float64
	if _, err := fmt.Sscanf(s, "%f", &f); err == nil {
		return v // numeric
	}
	return `"` + s + `"`
}

// collectConditions recursively gathers all condition strings from extracted data.
func collectConditions(e *ExtractedData) string {
	var sb strings.Builder
	condFields := []string{"approveCondition", "cantDecideCondition", "condition"}

	var collect func(interface{})
	collect = func(v interface{}) {
		switch val := v.(type) {
		case string:
			sb.WriteString(val)
			sb.WriteString(" ")
		case []interface{}:
			for _, item := range val {
				collect(item)
			}
		case map[string]interface{}:
			for _, f := range condFields {
				if cv, ok := val[f]; ok {
					collect(cv)
				}
			}
		case []map[string]interface{}:
			for _, item := range val {
				collect(item)
			}
		}
	}

	collect(e.GoNoGoRules)
	collect(e.SurrogateRules)
	collect(e.EligibilityExpressions)
	collect(e.ScorecardExpressions)
	for _, rs := range e.NamedRulesets {
		collect(rs.Rules)
	}
	for _, ms := range e.NamedModelsets {
		collect(ms.Expressions)
	}
	return sb.String()
}

// ─────────────────────────────────────────────────────────────────────────────
// WORKFLOW VALIDATOR
// ─────────────────────────────────────────────────────────────────────────────

func validateWorkflow(workflow map[string]interface{}) ValidationResult {
	var errors []string
	var warnings []string

	nodesRaw, _ := workflow["nodes"].([]interface{})
	if len(nodesRaw) == 0 {
		return ValidationResult{
			Valid:    false,
			Errors:   []string{"Workflow has no nodes"},
			Warnings: []string{},
			Stats:    map[string]interface{}{},
		}
	}

	// Index nodes by name
	nodeByName := make(map[string]map[string]interface{})
	for _, n := range nodesRaw {
		if node, ok := n.(map[string]interface{}); ok {
			if name, ok := node["name"].(string); ok && name != "" {
				nodeByName[name] = node
			}
		}
	}

	// Start nodes
	var startNodes []map[string]interface{}
	for _, n := range nodesRaw {
		if node, ok := n.(map[string]interface{}); ok {
			if node["type"] == "start" {
				startNodes = append(startNodes, node)
			}
		}
	}
	if len(startNodes) == 0 {
		errors = append(errors, "Missing required 'start' node")
	} else if len(startNodes) > 1 {
		errors = append(errors, fmt.Sprintf("Multiple start nodes found"))
	}

	// End nodes
	var endCount int
	for _, n := range nodesRaw {
		if node, ok := n.(map[string]interface{}); ok {
			if node["type"] == "end" {
				endCount++
			}
		}
	}
	if endCount == 0 {
		errors = append(errors, "No 'end' nodes found — workflow has no terminal states")
	}

	// nextState reference checks
	for _, n := range nodesRaw {
		node, ok := n.(map[string]interface{})
		if !ok {
			continue
		}
		name, _ := node["name"].(string)
		if name == "" {
			name = "<unnamed>"
		}

		if ns, ok := node["nextState"].(map[string]interface{}); ok {
			if target, ok := ns["name"].(string); ok && target != "" {
				if _, exists := nodeByName[target]; !exists {
					errors = append(errors, fmt.Sprintf("Node '%s' nextState references unknown node '%s'", name, target))
				}
			}
		}

		if conds, ok := node["dataConditions"].([]interface{}); ok {
			for _, c := range conds {
				if cond, ok := c.(map[string]interface{}); ok {
					if ns, ok := cond["nextState"].(map[string]interface{}); ok {
						if target, ok := ns["name"].(string); ok && target != "" {
							if _, exists := nodeByName[target]; !exists {
								condName, _ := cond["name"].(string)
								errors = append(errors, fmt.Sprintf("Switch '%s' condition '%s' references unknown node '%s'", name, condName, target))
							}
						}
					}
				}
			}
		}
	}

	// RuleSet checks
	totalRules := 0
	nodeTypes := make(map[string]int)
	for _, n := range nodesRaw {
		node, ok := n.(map[string]interface{})
		if !ok {
			continue
		}
		t, _ := node["type"].(string)
		nodeTypes[t]++

		if t == "ruleSet" {
			rules, _ := node["rules"].([]interface{})
			totalRules += len(rules)
			nodeName, _ := node["name"].(string)
			if len(rules) == 0 {
				warnings = append(warnings, fmt.Sprintf("RuleSet '%s' has no rules", nodeName))
			}
			for _, r := range rules {
				if rule, ok := r.(map[string]interface{}); ok {
					ac, _ := rule["approveCondition"].(string)
					rName, _ := rule["name"].(string)
					if strings.TrimSpace(ac) == "" {
						warnings = append(warnings, fmt.Sprintf("Rule '%s' in '%s' has an empty approveCondition", rName, nodeName))
					}
				}
			}
		}

		if t == "modelSet" {
			exprs, _ := node["expressions"].([]interface{})
			nodeName, _ := node["name"].(string)
			if len(exprs) == 0 {
				warnings = append(warnings, fmt.Sprintf("ModelSet '%s' has no expressions", nodeName))
			}
		}

		if t == "branch" {
			exprs, _ := node["expressions"].([]interface{})
			nodeName, _ := node["name"].(string)
			if len(exprs) == 0 {
				errors = append(errors, fmt.Sprintf("Branch '%s' has no expressions", nodeName))
			}
		}
	}

	inputsRaw, _ := workflow["inputs"].([]interface{})

	return ValidationResult{
		Valid:    len(errors) == 0,
		Errors:   errors,
		Warnings: warnings,
		Stats: map[string]interface{}{
			"total_nodes": len(nodesRaw),
			"node_types":  nodeTypes,
			"rule_sets":   nodeTypes["ruleSet"],
			"total_rules": totalRules,
			"inputs":      len(inputsRaw),
		},
	}
}
