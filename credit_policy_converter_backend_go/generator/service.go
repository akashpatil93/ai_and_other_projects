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
	"time"

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
func (s *svc) callClaude(ctx context.Context, prompt string, maxTokens int, apiKey string) (string, error) {
	const model = "claude-opus-4-6"

	httpClient := &http.Client{Timeout: 300 * time.Second}

	// Attempt with extended thinking first
	thinkingBudget := maxTokens * 4 / 10
	if thinkingBudget < 1024 {
		thinkingBudget = 1024
	}
	effectiveMax := thinkingBudget + maxTokens

	reqBody := claudeRequest{
		Model:     model,
		MaxTokens: effectiveMax,
		Thinking:  &claudeThinking{Type: "enabled", BudgetTokens: thinkingBudget},
		Messages:  []claudeMessage{{Role: "user", Content: prompt}},
	}

	text, err := s.doClaudeRequest(ctx, httpClient, reqBody, apiKey)
	if err != nil {
		// Fallback: no extended thinking
		reqBody.Thinking = nil
		reqBody.MaxTokens = maxTokens
		var err2 error
		text, err2 = s.doClaudeRequest(ctx, httpClient, reqBody, apiKey)
		if err2 != nil {
			return "", fmt.Errorf("claude API error: %w (thinking fallback: %v)", err, err2)
		}
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

	var sectionTypes map[string]string
	classifyResp, err := s.callClaude(ctx, getClassifySectionsPrompt(strings.Join(summaryLines, "\n")), 2048, apiKey)
	if err == nil {
		parsed := extractJSON(classifyResp)
		if m, ok := parsed.(map[string]interface{}); ok && len(m) > 0 {
			// Build case-insensitive lookup so LLM key variants (snake_case etc.) still match
			rawTypes := make(map[string]string)
			rawLower := make(map[string]string) // lowercase key → type
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
					// LLM didn't classify this section — use name-based fallback
					sectionTypes[sec.Name] = nameFallback[sec.Name]
				}
			}
		}
	}
	if len(sectionTypes) == 0 {
		sectionTypes = classifyByName(sections)
	}
	log.Printf("[debug] section_types: %v", sectionTypes)

	// Step 2: Process each section
	// NOTE: "exposure" removed — exposure sections contain rules and should be processed as modelset
	skipTypes := map[string]bool{"metadata": true, "pre_read": true, "change_history": true}

	for _, sec := range sections {
		stype, ok := sectionTypes[sec.Name]
		if !ok {
			// Default to go_no_go (not metadata) so policy sections are never silently dropped
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

		var raw string
		var callErr error

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

			raw, callErr = s.callClaude(ctx, inject(prompt), 4096, apiKey)
			if callErr != nil {
				log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
				continue
			}
			parsed := extractJSON(raw)
			if rules, ok := toSliceOfMaps(parsed); ok && len(rules) > 0 {
				if _, exists := namedRulesetMap[rsKey]; !exists {
					namedRulesetOrder = append(namedRulesetOrder, rsKey)
				}
				namedRulesetMap[rsKey] = append(namedRulesetMap[rsKey], rules...)
			}

		case stype == "modelset":
			raw, callErr = s.callClaude(ctx, inject(getModelsetPrompt(text, rsKey)), 16384, apiKey)
			if callErr != nil {
				log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
				continue
			}
			parsed := extractJSON(raw)
			if exprs, ok := toSliceOfMaps(parsed); ok && len(exprs) > 0 {
				if _, exists := namedModelsetMap[rsKey]; !exists {
					namedModelsetOrder = append(namedModelsetOrder, rsKey)
				}
				namedModelsetMap[rsKey] = append(namedModelsetMap[rsKey], exprs...)
			}

		case stype == "eligibility":
			raw, callErr = s.callClaude(ctx, inject(getEligibilityPrompt(text)), 16384, apiKey)
			if callErr != nil {
				log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
				continue
			}
			parsed := extractJSON(raw)
			if exprs, ok := toSliceOfMaps(parsed); ok {
				result.EligibilityExpressions = append(result.EligibilityExpressions, exprs...)
			}

		case stype == "scorecard":
			raw, callErr = s.callClaude(ctx, inject(getScorecardPrompt(text)), 16384, apiKey)
			if callErr != nil {
				log.Printf("[warn] error processing section '%s': %v", sec.Name, callErr)
				continue
			}
			parsed := extractJSON(raw)
			if exprs, ok := toSliceOfMaps(parsed); ok {
				result.ScorecardExpressions = append(result.ScorecardExpressions, exprs...)
			}
		}
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
	hGap       = 120
	baseNarrow = 200
	baseMedium = 300
	baseRuleset = 300
	ruleExtra  = 3
	yMain      = 0
	yApproved  = -320
	yRejected  = 320
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
		return map[string]interface{}{"name": "final_decision", "type": "branch"}
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
	if len(scorecardExprs) > 0 {
		nodes = append(nodes, buildModelSet("scorecard", place(baseMedium), yMain, scorecardExprs, afterScorecard))
	}

	// 4. Model modelSet
	if len(modelExprs) > 0 {
		nodes = append(nodes, buildModelSet("model", place(baseMedium), yMain, modelExprs, firstNamedModelsetOrRuleset()))
	}

	// 5. Named modelsets (between model and first ruleset)
	for i, ms := range namedModelsets {
		var msNext map[string]interface{}
		if i+1 < len(namedModelsets) {
			msNext = map[string]interface{}{"name": namedModelsets[i+1].Name, "type": "modelSet"}
		} else {
			msNext = firstRulesetRef()
		}
		exprs := make([]map[string]interface{}, len(ms.Expressions))
		copy(exprs, ms.Expressions)
		nodes = append(nodes, buildModelSet(ms.Name, place(baseMedium), yMain, exprs, msNext))
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

	// 7. Final decision branch
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

	// 8. Eligibility modelSet
	if len(eligExprs) > 0 {
		nodes = append(nodes, buildModelSet(
			"eligibility", place(baseMedium), yMain, eligExprs,
			map[string]interface{}{"name": "end_approved", "type": "end"},
		))
	}

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
	nodes = append(nodes, map[string]interface{}{
		"type":          "end",
		"name":          "end_rejected",
		"endNodeName":   "rejected",
		"tag":           newID(),
		"workflowState": map[string]interface{}{"type": "", "outcomeLogic": nil},
		"decisionNode":  map[string]interface{}{},
		"metadata":      map[string]interface{}{"x": endX, "y": yRejected, "nodeColor": 2},
	})

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
		conds = append(conds, map[string]interface{}{"name": "cantDecide", "nextState": forward})
	}
	return map[string]interface{}{"type": "switch", "name": swName, "dataConditions": conds}
}

func buildActiveSwitch(swName string, rules []map[string]interface{}, next map[string]interface{}) map[string]interface{} {
	conds := []interface{}{
		map[string]interface{}{"name": "pass", "nextState": next},
		map[string]interface{}{"name": "reject", "nextState": next},
	}
	if hasCantDecide(rules) {
		conds = append(conds, map[string]interface{}{"name": "cantDecide", "nextState": next})
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
