package generator

import "context"

// Section represents a parsed document section.
type Section struct {
	Name     string                   `json:"name"`
	Headers  []string                 `json:"headers"`
	Rows     []map[string]interface{} `json:"rows"`
	Text     string                   `json:"text"`
	RowCount int                      `json:"row_count"`
}

// ExtractedData holds all rules/expressions extracted via Claude.
type ExtractedData struct {
	GoNoGoRules            []map[string]interface{} `json:"go_no_go_rules"`
	SurrogateRules         []map[string]interface{} `json:"surrogate_rules"`
	EligibilityExpressions []map[string]interface{} `json:"eligibility_expressions"`
	ScorecardExpressions   []map[string]interface{} `json:"scorecard_expressions"`
	NamedRulesets          []NamedRuleset           `json:"named_rulesets"`
	NamedModelsets         []NamedModelset          `json:"named_modelsets"`
}

// NamedRuleset is a named collection of rules.
type NamedRuleset struct {
	Name  string                   `json:"name"`
	Rules []map[string]interface{} `json:"rules"`
}

// NamedModelset is a named collection of modelSet expressions.
type NamedModelset struct {
	Name        string                   `json:"name"`
	Expressions []map[string]interface{} `json:"expressions"`
}

// ValidationResult is the output of workflow validation.
type ValidationResult struct {
	Valid    bool                   `json:"valid"`
	Errors   []string               `json:"errors"`
	Warnings []string               `json:"warnings"`
	Stats    map[string]interface{} `json:"stats"`
}

// Service is the main interface for the credit policy converter.
type Service interface {
	// ParseDocument converts raw file bytes into a list of named sections.
	ParseDocument(fileBytes []byte, filename string) ([]Section, error)

	// ExtractAllSections calls Claude to classify and extract rules from sections.
	ExtractAllSections(ctx context.Context, sections []Section, userContext, apiKey string) (*ExtractedData, error)

	// AssembleWorkflow builds the complete BRE workflow JSON from extracted data.
	AssembleWorkflow(extracted *ExtractedData, samplePayload string) map[string]interface{}

	// ValidateWorkflow validates the structure of a workflow JSON.
	ValidateWorkflow(workflow map[string]interface{}) ValidationResult
}

// GetService returns a new Service implementation.
func GetService(anthropicURL string) Service {
	if anthropicURL == "" {
		anthropicURL = "https://api.anthropic.com/v1"
	}
	return &svc{anthropicURL: anthropicURL}
}
