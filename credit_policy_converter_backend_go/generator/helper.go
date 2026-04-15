package generator

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"regexp"
	"sort"
	"strings"

	"github.com/ledongthuc/pdf"
	"github.com/xuri/excelize/v2"
)

// ─────────────────────────────────────────────────────────────────────────────
// PROMPT FIELD TABLES
// ─────────────────────────────────────────────────────────────────────────────

const bureauFields = `
## Bureau Fields  (prefix: bureau.)

### DPD (Days Past Due) Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Max DPD in last 6 months                      | bureau.max_dpd_last_6_mo                            |
| Max DPD in last 12 months                     | bureau.max_dpd_inlast12months                       |
| Max DPD in last 24 months                     | bureau.max_dpd_inlast24months                       |
| Max DPD (non-CC) in last 3 months             | bureau.max_dpd_non_cc_last_3mo                      |
| Max DPD (CC) in last 3 months                 | bureau.max_dpd_cc_last_3mo                          |
| Count of 0+ DPD accounts in last 12 months   | bureau.cnt_0plus_dpd_12mo                           |
| Count of 30+ DPD accounts in last 12 months  | bureau.cnt_30plus_dpd_last12months                  |
| Count of 60+ DPD accounts in last 12 months  | bureau.cnt_60plus_dpd_last12months                  |
| Count of 90+ DPD accounts in last 12 months  | bureau.cnt_90plus_dpd_last12months                  |
| Count of 30+ DPD accounts in last 24 months  | bureau.cnt_30plus_dpd_last24months                  |
| Count of 60+ DPD accounts in last 24 months  | bureau.cnt_60plus_dpd_last24months                  |
| Count of 90+ DPD accounts in last 24 months  | bureau.cnt_90plus_dpd_last24months                  |
| Count of 0+ DPD in last 3 months             | bureau.cnt_0plus_dpd_3mo                            |
| Count of 30+ DPD in last 3 months            | bureau.cnt_30plus_dpd_3mo                           |

### Bureau Score Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| CIBIL Bureau Score / Bureau Score             | bureau.score                                  |
| CIBIL Bureau Score (explicit)                 | bureau.bureau_score_cibil                           |
| Experian Bureau Score                         | bureau.bureau_score_experian                        |
| Equifax Bureau Score                          | bureau.bureau_score_equifax                         |
| CRIF Bureau Score                             | bureau.bureau_score_crif                            |
| Bureau Score Bucket / Band                    | bureau.bureau_score_bucket                          |

### Outstanding Balance Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| All loans outstanding                         | bureau.amt_pos_all_loans                            |
| Unsecured loans outstanding                   | bureau.amt_pos_unsecured_loans                      |
| Total outstanding amount                      | bureau.total_outstanding_amount                     |
| Total outstanding (credit card)               | bureau.total_outstanding_amount_cc                  |
| Active unsecured current balance              | bureau.current_balance_active_unsecured             |
| Max overdue amount                            | bureau.max_overdue                                  |
| Sum overdue                                   | bureau.sum_overdue                                  |

### Settlement / Written-off Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Settlement/Written-off count                  | bureau.settlement_writtenoff                        |
| Total written-off amount                      | bureau.total_writtenoff_amt                         |
| Written-off amounts in last 24 months         | bureau.amts_writtenoff_last24months                 |
| Write-off / Settled / Restructured count (24M)| bureau.cnt_wo_settled_restructured_last24months     |
| DBT/LSS count                                 | bureau.cnt_dbt_lss                                  |
| SMA / SUB count                               | bureau.cnt_sma_sub                                  |
| DBT/LSS/SMA/SUB last 24M                      | bureau.cnt_dbt_lss_sma_sub_last24mo                 |

### Delinquency Flag Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Settlement/Written-off flag (boolean)         | bureau.settlement_writtenoff_flag                   |
| Written-off flag (boolean)                    | bureau.written_off_flag                             |
| Suit filed / Wilful defaulter count           | bureau.cnt_suit_filed_willful_defaul                |
| Suit filed / Wilful default in last 24M       | bureau.cnt_suit_filed_willful_default_in_last24months|
| Suit filed / Wilful default in 24M (flag)     | bureau.is_suitfiled_wilfuldefault_last24months      |

### Credit Card Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Total sanctioned amount (credit card)         | bureau.total_sanctioned_amount_cc                   |
| Max credit card limit in last 2 years         | bureau.max_credit_card_limit_last2year              |
| Credit card utilization percentage            | bureau.cc_utilization_percentage                    |

### Enquiry Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Enquiries in last 30 days                     | bureau.enquiry_last30days                           |
| Enquiries in last 3 months                    | bureau.enquiry_last3months                          |
| Enquiries in last 90 days                     | bureau.enquiry_last90days                           |
| Enquiries in last 6 months                    | bureau.enquiry_last6months                          |
| Unsecured enquiries in last 6 months          | bureau.enquiry_unsecured_last6months                |
| PL/BL enquiries in last 90 days               | bureau.cnt_enquiry_pl_bl_last90days                 |

### Account Opening / Count Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| New accounts opened in last 30 days           | bureau.new_open_acc_last30days                      |
| New accounts opened in last 6 months          | bureau.new_open_acc_last6months                     |
| Total count of all accounts                   | bureau.cnt_all_accounts                             |
| Non-guarantor tradelines (6MOB)               | bureau.cnt_non_guarantor_6mob                       |
| Oldest tradeline (non-guarantor) months       | bureau.months_since_first_opened_non_guarantor      |
| Oldest loan months                            | bureau.months_since_first_opened                    |

### Loan-Type Specific Variables
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Max sanctioned PL active 6MOB                 | bureau.max_sanct_amt_pl_active_6mob                 |
| Max sanctioned BL active 6MOB                 | bureau.max_sanct_amt_bl_active_6mob                 |
| Max sanctioned AL active 6MOB                 | bureau.max_sanct_amt_al_active_6mob                 |
| Max sanctioned HL/LAP active 6MOB             | bureau.max_sanct_amt_hl_lap_active_6mob             |
| PL/BL balance >=1L opened last 3M count       | bureau.cnt_pl_bl_bal_gte_1lac_open_last3months      |
| PL/BL balance >1L opened last 6M count        | bureau.cnt_pl_bl_bal_gt_1lac_open_last6months       |
`

const bankFields = `
## Bank Statement Fields  (prefix: bank.)

### Average Balance & Cash Flow
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Average Bank Balance (ABB)                    | bank.abb                                            |
| Average End-of-Day Balance                    | bank.eod_balance_avg                                |
| Min End-of-Day Balance (last 3M)              | bank.eod_balance_min_3mo                            |
| Average Monthly Credits (income)              | bank.income_avg                                     |
| Average Monthly Debits (expenses)             | bank.expense_avg                                    |

### Bounce Metrics
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Total bounces (last 3M)                       | bank.total_bounce_count_3mo                         |
| Total bounces (last 6M)                       | bank.total_bounce_count_6mo                         |
| Inward cheque bounce count (last 3M)          | bank.inward_bounce_count_3mo                        |
| Outward cheque bounce count (last 3M)         | bank.outward_bounce_count_3mo                       |
| ACH / NACH bounce count (last 3M)             | bank.ach_bounce_count_3mo                           |
| ACH / NACH bounce count (last 6M)             | bank.ach_bounce_count_6mo                           |
| EMI bounce count (last 3M)                    | bank.emi_bounce_count_3mo                           |
| EMI bounce count (last 6M)                    | bank.emi_bounce_count_6mo                           |

### EMI & Obligation
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Total EMI debit amount (last 3M avg)          | bank.emi_debit_avg_3mo                              |
| Total EMI debit amount (last 6M avg)          | bank.emi_debit_avg_6mo                              |
| EMI to income ratio (bank-derived FOIR)       | bank.emi_to_income_ratio                            |
| Number of unique EMI debits (last 3M)         | bank.emi_debit_count_3mo                            |
`

const inputFields = `
## Input Fields  (prefix: input.)
| Policy Document Term          | JSON Field                                    | Type   |
|-------------------------------|-----------------------------------------------|--------|
| Industry Type                 | input.industry_type                           | text   |
| Business Vintage (months)     | input.business_vintage                        | number |
| GST Registered                | input.gst_registered_business                 | text   |
| Age                           | input.age                                     | number |
| Occupation Type               | input.occupation_type                         | text   |
| RBI Defaulter                 | input.rbi_defaulter                           | text   |
| NCLT List                     | input.nclt_list_presence                      | text   |
| Requested Loan Amount         | input.req_loan_amount                         | number |
`

const modelFields = `
## Bureau HIT / NO-HIT
When a bureau pull returns no record (NO-HIT), all bureau fields will be nil.
Handle this using the standard nil-check pattern: bureau.<field> == nil
Do NOT reference model.hit_no_hit — there is no "model" modelSet in this workflow.
`

const expressionRefRules = `
## CRITICAL: How to reference expression values between nodes

### Rule 1 — Within the same modelSet: use the expression name directly
### Rule 2 — Across different nodes: prefix with the SOURCE node name
  <source_node_name>.<expression_name>
  Examples:
    scorecard.bureau_score_woe    → expression in the "scorecard" modelSet
    go_no_go_checks.decision      → the "decision" outcome of the "go_no_go_checks" ruleSet

### Rule 3 — Node execution order matters
  Start → bureau (dataSource) → scorecard → ruleSets → final_decision → eligibility → end
`

const expressionSyntax = `
## Expression Language — Sentinel / Expr

Data Source Prefixes:
  bureau.*   → bureau pull fields
  bank.*     → bank statement fields
  input.*    → everything else

Operators:
  Arithmetic   : +  -  *  /  %  ^  **
  Comparison   : ==  !=  <  >  <=  >=
  Logical      : !  not  &&  and  ||  or
  Ternary      : condition ? valueIfTrue : valueIfFalse
  Nil coalesce : expr ?? fallback
  Optional     : obj?.field
  Membership   : "x" in ["x","y"]

CRITICAL: Converting Policy Rules to approveCondition
Always invert REJECT conditions into APPROVE conditions.
  "Reject if bureau.max_overdue > 2000"
  → "bureau.max_overdue <= 2000 || bureau.max_overdue == nil"
`

const modelsetExpressionTypes = `
## modelSet Expression Types

Every modelSet expression must be one of three types. Choose the right one:

### 1. expression
A single mathematical formula or conditional computation.
Use when: calculating a value from inputs (e.g. EMI, FOIR, max loan amount).
  {
    "name": "max_emi",
    "type": "expression",
    "condition": "(input.income - MAX(bureau.obligation)) * 0.7"
  }

### 2. decisionTable
A flat lookup table: one or more column conditions matched row-by-row to an output.
Use when: output depends on combinations of variable ranges (e.g. interest rate by score x income).
  {
    "name": "interest_rate",
    "type": "decisionTable",
    "condition": "",
    "decisionTableRules": {
      "default": "22",
      "headers": ["bureau.score", "input.income"],
      "rows": [
        {"columns": [{"name": "bureau.score", "value": "> 800"}, {"name": "input.income", "value": "> 80000"}], "output": "\"12.12\""},
        {"columns": [{"name": "bureau.score", "value": "> 800"}, {"name": "input.income", "value": "60000..80000"}], "output": "\"14\""}
      ]
    }
  }

  decisionTable range syntax:
    "> X"        – greater than X
    "< X"        – less than X
    ">= X"       – greater than or equal
    "<= X"       – less than or equal
    "X..Y"       – between X and Y (inclusive)
    "nil"        – field is absent

### 3. matrix
A 2D grid: one row-variable x one column-variable → cell output value.
Use when: output is a grid lookup (e.g. risk bucket by age x obligation bracket).

Complete example — 3 row conditions x 4 column conditions:
  {
    "name": "risk_bucket",
    "type": "matrix",
    "condition": "",
    "matrix": {
      "globalRowIndex": 3,
      "globalColumnIndex": 4,
      "rows": [
        {
          "header": "input.age",
          "index": 0,
          "conditions": [
            {"index": 0, "condition": "21..30", "child": null},
            {"index": 1, "condition": "30..45", "child": null},
            {"index": 2, "condition": "45..60", "child": null}
          ]
        },
        {
          "header": "No matches",
          "index": 3,
          "isNoMatches": true,
          "conditions": [{"index": 3, "condition": "true", "child": null}]
        }
      ],
      "columns": [
        {
          "header": "bureau.obligation",
          "index": 0,
          "conditions": [
            {"index": 0, "condition": "< 35000", "child": null},
            {"index": 1, "condition": "35000..65000", "child": null},
            {"index": 2, "condition": "65000..100000", "child": null},
            {"index": 3, "condition": "> 100000", "child": null}
          ]
        },
        {
          "header": "No matches",
          "index": 4,
          "isNoMatches": true,
          "conditions": [{"index": 4, "condition": "true", "child": null}]
        }
      ],
      "values": [
        ["A", "B", "C", "D", "F"],
        ["A", "A", "B", "C", "F"],
        ["A", "B", "C", "D", "F"],
        ["F", "F", "F", "F", "F"]
      ]
    }
  }

  matrix rules:
  - R = number of data row conditions; C = number of data col conditions.
  - globalRowIndex = R  (= the index field on the "No matches" row).
  - globalColumnIndex = C  (= the index field on the "No matches" column).
  - The rows array has exactly one data-predictor entry (index 0, all conditions listed)
    plus one "No matches" entry (index R, isNoMatches: true, single condition "true").
  - The columns array mirrors this: one data-predictor entry plus one "No matches" entry (index C).
  - values is a 2D array of size (R+1) x (C+1): values[i][j] is the output for
    data row condition i and data column condition j; the last row and last column hold
    the fallback value (same string, e.g. "F" or "0").
  - All condition indices must be consecutive integers (0, 1, 2 ... R for rows; 0 ... C for columns).
  - Condition syntax: "21..30", "< 35000", "> 100000", "true"
`

// systemPrompt is the master system prompt sent with every Claude call.
var systemPrompt = fmt.Sprintf(`You are a credit policy expert who converts policy documents into structured
workflow JSON for a Business Rule Engine (BRE) platform.

Your responsibilities:
1. Read credit policy rules from document text or tables.
2. Map field names to the correct JSON variable namespaces.
3. Convert natural-language conditions to the expression syntax.
4. ALWAYS invert reject conditions into approve conditions.
5. Identify muted / inactive rules and mark them muted=true.
6. Use the correct cross-node reference syntax.
7. Return ONLY valid JSON — no markdown fences, no explanations.
8. NEVER leave approveCondition blank.

%s%s%s%s%s%s`,
	bureauFields, bankFields, inputFields, modelFields, expressionRefRules, expressionSyntax)

// ─────────────────────────────────────────────────────────────────────────────
// PROMPT BUILDER FUNCTIONS
// ─────────────────────────────────────────────────────────────────────────────

func getClassifySectionsPrompt(sectionsSummary string) string {
	return fmt.Sprintf(`Classify the following document sections by their purpose in a credit policy workflow.

SECTIONS:
%s

Return a single JSON object mapping each section name to a type string.

Valid types:
  "go_no_go"                   – General Go/No-Go eligibility rules (binary pass/fail checks)
  "dpd_checks"                 – DPD (Days Past Due) based rules — max DPD, DPD count thresholds
  "bureau_score_checks"        – Bureau score based rules — CIBIL, Experian, Equifax, CRIF score thresholds
  "outstanding_balance_checks" – Outstanding amount / overdue balance rules
  "enquiry_checks"             – Credit enquiry count rules (last 30/90 days, 6 months, etc.)
  "written_off_settlement_checks" – Written-off / settled / restructured / DBT / LSS account rules
  "delinquency_flag_checks"    – Delinquency flags — suit filed, wilful default, written-off flag
  "credit_card_checks"         – Credit card specific rules — utilization, CC outstanding, CC DPD
  "account_opening_checks"     – New account opening / account count rules
  "surrogate_policy"           – Surrogate/alternative policy rules
  "scorecard"                  – Scorecard model features, WOE coefficients, bureau feature bins
  "modelset"                   – Computed/derived values: offer calculation, interest rate tables,
                                 risk bucket grids, pricing matrices, income derivation, FOIR/EMI limits,
                                 product-category cap tables, program selection tables, tenure/amount caps
                                 — NOT binary pass/fail rules
  "eligibility"                – Loan amount / EMI / FOIR computations
  "exposure"                   – Internal exposure or portfolio limit rules
  "common_rules"               – Shared rules used across programs
  "pre_read"                   – Context, input payload definitions, HIT/NO-HIT definitions — SKIP
  "change_history"             – Changelog / version history — SKIP
  "metadata"                   – Truly unclassifiable content (do NOT use for policy rule sections)

IMPORTANT:
- Prefer specific bureau categories (dpd_checks, bureau_score_checks, etc.) over "go_no_go"
  when the section clearly focuses on a specific bureau variable category.
- If a section contains policy rules, checks, or validations of ANY kind and does not fit a
  more specific type, classify it as "go_no_go" — never as "metadata".
- Sections named after specific checks (e.g. "Location Strategy", "Business Vintage",
  "Age checks", "Negative Databases", "PAN Check", "Bank Statement Checks") are "go_no_go".
- Sections containing lookup tables, cap grids, product/program matrices, or computed value
  derivations are "modelset" — even if they reference pass/fail logic as part of the table.
- "Input Payload" or variable definition tables → "pre_read" (SKIP).

Return ONLY valid JSON, no explanation:
{"<section_name>": "<type>"}
`, sectionsSummary)
}

func getGoNoGoPrompt(sectionContent string) string {
	return fmt.Sprintf(`
%s

Extract every Go/No-Go policy rule from the section below and produce a JSON array.

MUTED RULES: Rules marked "Muted", "M", "Inactive", or "Not in force" get muted=true.

UPSTREAM NODES AVAILABLE (in execution order before this ruleSet):
  bureau.*          → all bureau pull fields (see Bureau Fields table)
  bank.*            → all bank statement fields (see Bank Fields table)
  input.*           → all application input fields (anything not in bureau or bank tables)
  scorecard.<name>  → if a scorecard modelSet exists, its expression outputs

SECTION CONTENT:
%s

For each rule output:
{
  "name": "RULE_CODE: Short description",
  "approveCondition": "expression — use bureau.*, bank.*, input.*, or scorecard.<expr>",
  "cantDecideCondition": "",
  "muted": false
}

MANDATORY:
- INVERT every reject condition into an approve condition.
- NEVER leave approveCondition blank. If a variable is not in the bureau or bank tables,
  declare it as input.<variable_name> and write the rule using it.
- Add "|| field == nil" for bureau and bank numeric fields (data may be absent).
  This also handles bureau NO-HIT — when there is no bureau record all fields will be nil.
- For negative-list input fields use: 'input.field == "negative" || input.field == nil'
- Do NOT use model.hit_no_hit — there is no "model" modelSet. Use nil checks instead.
- Include the rule code (GPR01, PR01, etc.) in the name when present.

Return ONLY a valid JSON array:
[{"name": "...", "approveCondition": "...", "cantDecideCondition": "", "muted": false}]
`, systemPrompt, sectionContent)
}

func getSurrogatePolicyPrompt(sectionContent string) string {
	return fmt.Sprintf(`
%s

Extract every surrogate policy rule from the section below.
Rules marked "Muted", "M", "Inactive", or "Not in force" get muted=true.

UPSTREAM NODES AVAILABLE (in execution order before this ruleSet):
  bureau.*                     → all bureau pull fields (see Bureau Fields table)
  bank.*                       → all bank statement fields (see Bank Fields table)
  input.*                      → all application input fields (anything not in bureau or bank)
  scorecard.<name>             → scorecard expression outputs (if scorecard exists)
  go_no_go_checks.decision     → "pass" / "reject" outcome of the go_no_go ruleSet (if it exists)

SECTION CONTENT:
%s

For each rule output:
{
  "name": "CODE: Description",
  "approveCondition": "expression",
  "cantDecideCondition": "",
  "muted": false
}

MANDATORY:
- INVERT every reject condition into an approve condition.
- NEVER leave approveCondition blank. If a variable is not in the bureau or bank tables,
  declare it as input.<variable_name> and write the rule using it.
- Add "|| field == nil" for bureau and bank numeric fields.
- Do NOT use model.hit_no_hit — there is no "model" modelSet. Use nil checks instead.

Return ONLY a valid JSON array:
[{"name": "...", "approveCondition": "...", "cantDecideCondition": "", "muted": false}]
`, systemPrompt, sectionContent)
}

// bureauCategoryDescriptions maps section types to human-readable descriptions.
var bureauCategoryDescriptions = map[string]string{
	"dpd_checks":                     "DPD (Days Past Due) based rules — max DPD thresholds and DPD count limits",
	"bureau_score_checks":            "Bureau score thresholds — CIBIL, Experian, Equifax, CRIF minimum score rules",
	"outstanding_balance_checks":     "Outstanding balance and overdue amount rules",
	"enquiry_checks":                 "Credit enquiry count rules within specific lookback periods",
	"written_off_settlement_checks":  "Written-off, settled, restructured, DBT and LSS account rules",
	"delinquency_flag_checks":        "Delinquency flags — suit filed, wilful default, written-off indicators",
	"credit_card_checks":             "Credit card specific rules — utilization, CC outstanding, CC DPD",
	"account_opening_checks":         "New account opening and total account count rules",
}

// bureauCategoryTypes is the set of section types handled as bureau rulesets.
var bureauCategoryTypes = func() map[string]bool {
	m := make(map[string]bool)
	for k := range bureauCategoryDescriptions {
		m[k] = true
	}
	return m
}()

func getBureauRulesetPrompt(sectionContent, rulesetName string) string {
	description, ok := bureauCategoryDescriptions[rulesetName]
	if !ok {
		description = fmt.Sprintf("Bureau policy rules for category: %s", rulesetName)
	}
	return fmt.Sprintf(`
%s

Extract every policy rule from the section below. These rules belong to the "%s" ruleset.
Category focus: %s

MUTED RULES: Rules marked "Muted", "M", "Inactive", or "Not in force" get muted=true.

SECTION CONTENT:
%s

For each rule output:
{
  "name": "RULE_CODE: Short description",
  "approveCondition": "expression — use bureau.*, bank.*, input.*, or model.<expr>",
  "cantDecideCondition": "",
  "muted": false
}

MANDATORY:
- INVERT every reject condition into an approve condition.
- NEVER leave approveCondition blank.
- Add "|| field == nil" for bureau and bank numeric fields.
- Use exact bureau variable names from the Bureau Fields table.
- Do NOT use model.hit_no_hit — there is no "model" modelSet. Use "|| bureau.field == nil" for NO-HIT.

Return ONLY a valid JSON array:
[{"name": "...", "approveCondition": "...", "cantDecideCondition": "", "muted": false}]
`, systemPrompt, rulesetName, description, sectionContent)
}

func getModelsetPrompt(sectionContent, modelsetName string) string {
	return fmt.Sprintf(`
%s

Extract computed expressions from the section below.
These become entries in a modelSet node named "%s".

%s

SECTION CONTENT:
%s

Rules:
- Arithmetic / conditional formulas → type "expression"
- Lookup tables (flat rows, one condition per row) → type "decisionTable"
- 2D grids (one row-variable x one column-variable) → type "matrix"

Return ONLY a valid JSON array of expression objects. Every object must include:
- name, type, condition (empty string for decisionTable/matrix)
- For type "decisionTable": include the full "decisionTableRules" object
  (default, headers, rows with all columns and outputs).
- For type "matrix": include the full "matrix" object
  (globalRowIndex, globalColumnIndex, rows, columns, values).
Do NOT return shells or placeholders — include all rows, columns, and cell values extracted
from the section content.
`, systemPrompt, modelsetName, modelsetExpressionTypes, sectionContent)
}

func getEligibilityPrompt(sectionContent string) string {
	return fmt.Sprintf(`
%s

Extract eligibility computation formulas from the section below.
These become entries in the "eligibility" modelSet node.

%s

UPSTREAM NODES AVAILABLE (all run before the eligibility modelSet):
  bureau.*                          → raw bureau fields
  bank.*                            → bank statement fields (ABB, salary, bounce, EMI, etc.)
  input.*                           → application input fields (anything not in bureau or bank)
  scorecard.<feature>               → scorecard expression outputs (if scorecard exists)
  go_no_go_checks.decision          → "pass"/"reject" (if go_no_go ruleSet exists)
  surrogate_policy_checks.decision  → "pass"/"reject" (if surrogate ruleSet exists)

WITHIN THE SAME "eligibility" modelSet:
  Reference earlier expressions by bare name (no prefix).
  Example: if "max_emi" is defined at seqNo 0, a later expression at seqNo 1 can use just "max_emi".

SECTION CONTENT:
%s

Common eligibility variables: abb, foir, max_eligible_loan, emi, net_income.

Rules:
- Arithmetic / conditional formulas → type "expression"
- Lookup tables (flat rows, one condition per row) → type "decisionTable"
- 2D grids (one row-variable x one column-variable) → type "matrix"

Return ONLY a valid JSON array of expression objects. Every object must include:
- name, type, condition (empty string for decisionTable/matrix)
- For type "decisionTable": include the full "decisionTableRules" object
  (default, headers, rows with all columns and outputs).
- For type "matrix": include the full "matrix" object
  (globalRowIndex, globalColumnIndex, rows, columns, values).
Do NOT return shells or placeholders — include all rows, columns, and cell values extracted
from the section content.
`, systemPrompt, modelsetExpressionTypes, sectionContent)
}

func getScorecardPrompt(sectionContent string) string {
	return fmt.Sprintf(`
%s

Extract scorecard model features from the section below.
Each feature becomes an expression in the "scorecard" modelSet node.

%s

SECTION CONTENT:
%s

Choose the correct type for each feature:
- Single-variable WOE bins → type "decisionTable" (one header, one column condition per row)
- Two-variable interaction grid → type "matrix"
- Calculated score total → type "expression", use bare feature names

Map all input variable names to the bureau.* namespace using the Bureau Fields table.
Use "0" as the default for decisionTable WOE features.

Return ONLY a valid JSON array of expression objects. Every object must include:
- name, type, condition (empty string for decisionTable/matrix)
- For type "decisionTable": include the full "decisionTableRules" object.
- For type "matrix": include the full "matrix" object with all rows, columns, and values.
Do NOT return shells — include all data extracted from the section.
`, systemPrompt, modelsetExpressionTypes, sectionContent)
}

// ─────────────────────────────────────────────────────────────────────────────
// JSON EXTRACTION HELPER
// ─────────────────────────────────────────────────────────────────────────────

// extractJSON robustly extracts JSON from an LLM response string.
func extractJSON(text string) interface{} {
	text = strings.TrimSpace(text)

	// 1. Direct parse
	var v interface{}
	if err := json.Unmarshal([]byte(text), &v); err == nil {
		return v
	}

	// 2. Markdown code block: ```json ... ``` or ``` ... ```
	for _, pat := range []string{
		"(?s)```json\\s*([\\s\\S]+?)\\s*```",
		"(?s)```\\s*([\\s\\S]+?)\\s*```",
	} {
		re := regexp.MustCompile(pat)
		if m := re.FindStringSubmatch(text); len(m) > 1 {
			if err := json.Unmarshal([]byte(m[1]), &v); err == nil {
				return v
			}
		}
	}

	// 3. First JSON array
	if m := regexp.MustCompile(`(?s)(\[[\s\S]+\])`).FindStringSubmatch(text); len(m) > 1 {
		if err := json.Unmarshal([]byte(m[1]), &v); err == nil {
			return v
		}
	}

	// 4. First JSON object
	if m := regexp.MustCompile(`(?s)(\{[\s\S]+\})`).FindStringSubmatch(text); len(m) > 1 {
		if err := json.Unmarshal([]byte(m[1]), &v); err == nil {
			return v
		}
	}

	return []interface{}{}
}

// ─────────────────────────────────────────────────────────────────────────────
// DOCUMENT PARSERS
// ─────────────────────────────────────────────────────────────────────────────

// ParseDocument routes to the correct parser based on file extension.
func ParseDocument(fileBytes []byte, filename string) ([]Section, error) {
	lower := strings.ToLower(filename)
	switch {
	case strings.HasSuffix(lower, ".xlsx") || strings.HasSuffix(lower, ".xls"):
		return parseExcel(fileBytes)
	case strings.HasSuffix(lower, ".pdf"):
		return parsePDF(fileBytes)
	case strings.HasSuffix(lower, ".docx"):
		return parseDocx(fileBytes)
	case strings.HasSuffix(lower, ".csv"):
		return parseCSV(fileBytes)
	case strings.HasSuffix(lower, ".json"):
		return parseJSONDoc(fileBytes)
	default:
		return nil, fmt.Errorf("unsupported file type: %s", filename)
	}
}

// parseExcel parses an Excel file into sections (one per sheet).
func parseExcel(data []byte) ([]Section, error) {
	f, err := excelize.OpenReader(bytes.NewReader(data))
	if err != nil {
		return nil, fmt.Errorf("open excel: %w", err)
	}
	defer f.Close()

	var sections []Section

	for _, sheetName := range f.GetSheetList() {
		rows, err := f.GetRows(sheetName)
		if err != nil {
			continue
		}

		// Filter empty rows
		var allRows [][]string
		for _, row := range rows {
			hasContent := false
			for _, cell := range row {
				if strings.TrimSpace(cell) != "" {
					hasContent = true
					break
				}
			}
			if hasContent {
				allRows = append(allRows, row)
			}
		}
		if len(allRows) == 0 {
			continue
		}

		// Find header row: first row with 2+ non-empty cells
		headerIdx := 0
		for i, row := range allRows {
			nonEmpty := 0
			for _, cell := range row {
				if strings.TrimSpace(cell) != "" {
					nonEmpty++
				}
			}
			if nonEmpty >= 2 {
				headerIdx = i
				break
			}
		}

		// Build headers, replace blank cells with placeholder names
		rawHeaders := allRows[headerIdx]
		headers := make([]string, len(rawHeaders))
		for j, cell := range rawHeaders {
			if strings.TrimSpace(cell) != "" {
				headers[j] = strings.TrimSpace(cell)
			} else {
				headers[j] = fmt.Sprintf("column_%d", j+1)
			}
		}

		// Extract data rows as maps
		var dataRows []map[string]interface{}
		for _, row := range allRows[headerIdx+1:] {
			hasContent := false
			for _, cell := range row {
				if strings.TrimSpace(cell) != "" {
					hasContent = true
					break
				}
			}
			if !hasContent {
				continue
			}
			rowMap := make(map[string]interface{})
			for j, h := range headers {
				if j < len(row) {
					rowMap[h] = row[j]
				}
			}
			dataRows = append(dataRows, rowMap)
		}

		// Build plain-text for LLM
		var textParts []string
		textParts = append(textParts, fmt.Sprintf("=== Sheet: %s ===", sheetName))
		textParts = append(textParts, strings.Join(headers, " | "))
		textParts = append(textParts, strings.Repeat("-", 80))
		limit := 150
		if len(dataRows) < limit {
			limit = len(dataRows)
		}
		for _, row := range dataRows[:limit] {
			var cells []string
			for _, h := range headers {
				v := ""
				if val, ok := row[h]; ok && val != nil {
					v = fmt.Sprintf("%v", val)
				}
				cells = append(cells, v)
			}
			textParts = append(textParts, strings.Join(cells, " | "))
		}
		if len(dataRows) > 150 {
			textParts = append(textParts, fmt.Sprintf("... (%d more rows omitted)", len(dataRows)-150))
		}

		sections = append(sections, Section{
			Name:     sheetName,
			Headers:  headers,
			Rows:     dataRows,
			Text:     strings.Join(textParts, "\n"),
			RowCount: len(dataRows),
		})
	}

	return sections, nil
}

// parsePDF extracts text from a PDF and splits it into sections.
func parsePDF(data []byte) ([]Section, error) {
	r, err := pdf.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, fmt.Errorf("open pdf: %w", err)
	}

	var sb strings.Builder
	numPages := r.NumPage()
	for i := 1; i <= numPages; i++ {
		page := r.Page(i)
		if page.V.IsNull() {
			continue
		}
		content := page.Content()
		var prevY float64
		var prevFontSize float64
		for _, t := range content.Text {
			// Insert newline when Y position changes significantly (new line in the PDF)
			if prevY != 0 {
				lineHeight := prevFontSize
				if lineHeight <= 0 {
					lineHeight = 10
				}
				if prevY-t.Y > lineHeight*0.4 || t.Y-prevY > lineHeight*0.4 {
					sb.WriteString("\n")
				}
			}
			sb.WriteString(t.S)
			if !strings.HasSuffix(t.S, " ") {
				sb.WriteString(" ")
			}
			prevY = t.Y
			prevFontSize = t.FontSize
		}
		sb.WriteString("\n")
	}
	fullText := sb.String()

	if strings.TrimSpace(fullText) == "" {
		return nil, fmt.Errorf("no text extracted from PDF")
	}

	// Normalize: insert newlines before section markers that may have been
	// concatenated without line breaks by the PDF extraction library.
	fullText = normalizePDFText(fullText)

	// Strategy 1: "Rule set name:" lines
	if secs := splitPDFByRulesetName(fullText); len(secs) > 0 {
		return secs, nil
	}
	// Strategy 2: Numbered headings
	if secs := splitPDFByNumberedHeadings(fullText); len(secs) > 0 {
		return secs, nil
	}
	// Strategy 3: ALL-CAPS lines
	if secs := splitPDFByAllCaps(fullText); len(secs) > 0 {
		return secs, nil
	}
	// Strategy 4: Whole document
	text := fullText
	if len(text) > 24000 {
		text = text[:24000]
	}
	return []Section{{
		Name:     "Policy Document",
		Headers:  []string{"Content"},
		Rows:     []map[string]interface{}{{"Content": fullText}},
		Text:     "=== Policy Document ===\n" + text,
		RowCount: 1,
	}}, nil
}

// normalizePDFText inserts newlines before section markers that may have been
// concatenated without proper line breaks by the ledongthuc/pdf library.
func normalizePDFText(text string) string {
	// Insert \n before "Rule set name:" that doesn't already start on a new line
	re1 := regexp.MustCompile(`([^\n])((?i)Rule\s{0,3}set\s{0,3}name\s{0,3}[:\-])`)
	text = re1.ReplaceAllString(text, "$1\n$2")
	// Insert \n before numbered headings (e.g. "1. Core Policy Checks") when they
	// appear mid-text (preceded by a non-newline character and whitespace).
	re2 := regexp.MustCompile(`([^\n\r])\s{1,4}(\d+\.\s+[A-Z][A-Za-z][A-Za-z ,&\-\/\(\)]{3,60})`)
	text = re2.ReplaceAllString(text, "$1\n$2")
	return text
}

func makePDFSection(name, text string) *Section {
	text = strings.TrimSpace(text)
	if len(text) < 20 {
		return nil
	}
	preview := text
	if len(preview) > 24000 {
		preview = preview[:24000]
	}
	return &Section{
		Name:     name,
		Headers:  []string{"Content"},
		Rows:     []map[string]interface{}{{"Content": text}},
		Text:     fmt.Sprintf("=== %s ===\n%s", name, preview),
		RowCount: 1,
	}
}

func splitPDFByRulesetName(fullText string) []Section {
	// Match "Rule set name:" anywhere — don't require strict line-start since PDF text
	// extraction may not produce proper newlines between all lines.
	// Cap section name at 120 chars to avoid consuming the entire document when
	// no newline follows the name.
	re := regexp.MustCompile(`(?i)Rule\s*set\s*name\s*[:\-]\s*([A-Za-z][^\n*]{0,120})`)
	matches := re.FindAllStringSubmatchIndex(fullText, -1)
	if len(matches) == 0 {
		return nil
	}

	type split struct {
		name  string
		start int
	}
	var splits []split
	for _, m := range matches {
		name := strings.TrimRight(strings.TrimSpace(fullText[m[2]:m[3]]), "*")
		if name != "" {
			splits = append(splits, split{name, m[0]})
		}
	}
	if len(splits) == 0 {
		return nil
	}

	var sections []Section
	if preamble := strings.TrimSpace(fullText[:splits[0].start]); len(preamble) > 80 {
		if s := makePDFSection("Input Payload", preamble); s != nil {
			sections = append(sections, *s)
		}
	}
	for i, sp := range splits {
		end := len(fullText)
		if i+1 < len(splits) {
			end = splits[i+1].start
		}
		if s := makePDFSection(sp.name, fullText[sp.start:end]); s != nil {
			sections = append(sections, *s)
		}
	}
	return sections
}

func splitPDFByNumberedHeadings(fullText string) []Section {
	re := regexp.MustCompile(`(?m)(?:^|[\n\r])((?:\d+\.)+\d*\s+[A-Za-z].{3,60})(?:\n|$)`)
	matches := re.FindAllStringSubmatchIndex(fullText, -1)

	// Lenient fallback: if newline-anchored regex finds fewer than 2 headings,
	// try without anchoring (handles PDFs where line breaks are missing).
	if len(matches) < 2 {
		re = regexp.MustCompile(`\b(\d+\.\s+[A-Z][A-Za-z][A-Za-z ,&\/\-\(\)]{3,50})\b`)
		matches = re.FindAllStringSubmatchIndex(fullText, -1)
	}

	if len(matches) < 2 {
		return nil
	}

	type split struct {
		name  string
		start int
	}
	var splits []split
	for _, m := range matches {
		name := strings.TrimSpace(fullText[m[2]:m[3]])
		splits = append(splits, split{name, m[0]})
	}

	var sections []Section
	for i, sp := range splits {
		end := len(fullText)
		if i+1 < len(splits) {
			end = splits[i+1].start
		}
		if s := makePDFSection(sp.name, fullText[sp.start:end]); s != nil {
			sections = append(sections, *s)
		}
	}
	return sections
}

func splitPDFByAllCaps(fullText string) []Section {
	re := regexp.MustCompile(`\n([A-Z][A-Z &/\-]{3,50})\n`)
	type split struct {
		name  string
		start int
	}
	splits := []split{{"Introduction", 0}}
	for _, m := range re.FindAllStringSubmatchIndex(fullText, -1) {
		name := strings.TrimSpace(fullText[m[2]:m[3]])
		if len(name) >= 5 && len(name) <= 60 {
			splits = append(splits, split{name, m[0]})
		}
	}
	if len(splits) < 2 {
		return nil
	}

	var sections []Section
	for i, sp := range splits {
		end := len(fullText)
		if i+1 < len(splits) {
			end = splits[i+1].start
		}
		text := strings.TrimSpace(fullText[sp.start:end])
		if len(text) > 80 {
			if s := makePDFSection(sp.name, text); s != nil {
				sections = append(sections, *s)
			}
		}
	}
	return sections
}

// ─────────────────────────────────────────────────────────────────────────────
// DOCX PARSER
// ─────────────────────────────────────────────────────────────────────────────

type docxBlock2 struct {
	tag  string
	text string
}

func parseDocx(data []byte) ([]Section, error) {
	zr, err := zip.NewReader(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		return nil, fmt.Errorf("open docx zip: %w", err)
	}

	var docXML []byte
	for _, f := range zr.File {
		if f.Name == "word/document.xml" {
			rc, err := f.Open()
			if err != nil {
				return nil, err
			}
			docXML, err = io.ReadAll(rc)
			rc.Close()
			if err != nil {
				return nil, err
			}
			break
		}
	}
	if docXML == nil {
		return nil, fmt.Errorf("word/document.xml not found in docx")
	}

	// Extract blocks (paragraphs and tables) preserving order
	blocks, err := extractDocxBlocks(docXML)
	if err != nil {
		return nil, err
	}

	// Strategy 1: "Rule set name:" lines
	rulesetPat := regexp.MustCompile(`(?i)Rule\s+set\s+name\s*[:\-]\s*(.+)`)
	type rsSplit struct {
		name string
		idx  int
	}
	var rsSplits []rsSplit
	for i, b := range blocks {
		if b.tag == "p" {
			if m := rulesetPat.FindStringSubmatch(b.text); len(m) > 1 {
				name := strings.TrimRight(strings.TrimSpace(m[1]), "*")
				if name != "" {
					rsSplits = append(rsSplits, rsSplit{name, i})
				}
			}
		}
	}
	if len(rsSplits) > 0 {
		var sections []Section
		preamble := joinBlocks(blocks[:rsSplits[0].idx])
		if len(preamble) > 80 {
			sections = append(sections, makeDocxSection("Input Payload", preamble))
		}
		for i, sp := range rsSplits {
			end := len(blocks)
			if i+1 < len(rsSplits) {
				end = rsSplits[i+1].idx
			}
			text := joinBlocks(blocks[sp.idx:end])
			if len(text) >= 40 {
				sections = append(sections, makeDocxSection(sp.name, text))
			}
		}
		if len(sections) > 0 {
			return sections, nil
		}
	}

	// Strategy 2: Heading paragraphs
	var headingSections []Section
	currentName := "Document"
	var currentLines []string
	headingRe := regexp.MustCompile(`(?i)^Heading`)
	for _, b := range blocks {
		if b.tag == "heading" || headingRe.MatchString(b.tag) {
			if len(currentLines) > 0 {
				headingSections = append(headingSections, makeDocxSection(currentName, strings.Join(currentLines, "\n")))
				currentLines = nil
			}
			currentName = b.text
		} else {
			currentLines = append(currentLines, b.text)
		}
	}
	if len(currentLines) > 0 {
		headingSections = append(headingSections, makeDocxSection(currentName, strings.Join(currentLines, "\n")))
	}
	if len(headingSections) > 1 {
		return headingSections, nil
	}

	// Strategy 3: whole document
	full := joinBlocks(blocks)
	if len(full) > 8000 {
		full = full[:8000]
	}
	return []Section{{
		Name:     "Document",
		Headers:  []string{},
		Rows:     []map[string]interface{}{},
		Text:     full,
		RowCount: 0,
	}}, nil
}

func joinBlocks(blocks []docxBlock2) string {
	var lines []string
	for _, b := range blocks {
		if b.text != "" {
			lines = append(lines, b.text)
		}
	}
	return strings.Join(lines, "\n")
}

func makeDocxSection(name, text string) Section {
	text = strings.TrimSpace(text)
	preview := text
	if len(preview) > 8000 {
		preview = preview[:8000]
	}
	return Section{
		Name:     name,
		Headers:  []string{"Content"},
		Rows:     []map[string]interface{}{{"Content": text}},
		Text:     fmt.Sprintf("=== %s ===\n%s", name, preview),
		RowCount: 1,
	}
}

// extractDocxBlocks parses document.xml via streaming XML into ordered blocks.
// It tracks three element types: <p> (paragraph), <tc> (table cell), <t> (text run).
func extractDocxBlocks(xmlData []byte) ([]docxBlock2, error) {
	var blocks []docxBlock2
	dec := xml.NewDecoder(bytes.NewReader(xmlData))

	var (
		inPara, inCell, inText bool
		currentStyle           string
		currentParaTexts       []string
		currentCellParas       []string
	)

	for {
		tok, err := dec.Token()
		if err == io.EOF {
			break
		}
		if err != nil {
			return blocks, nil // return whatever we collected so far
		}

		switch t := tok.(type) {
		case xml.StartElement:
			switch t.Name.Local {
			case "p":
				inPara = true
				currentStyle = ""
				currentParaTexts = nil
			case "tc":
				inCell = true
				currentCellParas = nil
			case "pStyle":
				if inPara {
					for _, a := range t.Attr {
						if a.Name.Local == "val" {
							currentStyle = a.Value
						}
					}
				}
			case "t":
				inText = true
			}

		case xml.CharData:
			if inText {
				currentParaTexts = append(currentParaTexts, string(t))
			}

		case xml.EndElement:
			switch t.Name.Local {
			case "t":
				inText = false
			case "p":
				if inPara {
					text := strings.TrimSpace(strings.Join(currentParaTexts, ""))
					if text != "" {
						if inCell {
							currentCellParas = append(currentCellParas, text)
						} else {
							tag := "p"
							if strings.HasPrefix(currentStyle, "Heading") {
								tag = "heading"
							}
							blocks = append(blocks, docxBlock2{tag: tag, text: text})
						}
					}
					inPara = false
					currentParaTexts = nil
					currentStyle = ""
				}
			case "tc":
				if inCell {
					text := strings.TrimSpace(strings.Join(currentCellParas, " "))
					if text != "" {
						blocks = append(blocks, docxBlock2{tag: "tbl", text: text})
					}
					inCell = false
					currentCellParas = nil
				}
			}
		}
	}
	return blocks, nil
}

// parseCSV parses CSV bytes into a single section.
func parseCSV(data []byte) ([]Section, error) {
	text := string(data)
	lines := strings.Split(text, "\n")
	if len(lines) == 0 {
		return nil, fmt.Errorf("empty CSV")
	}

	headers := strings.Split(strings.TrimRight(lines[0], "\r"), ",")
	for i := range headers {
		headers[i] = strings.Trim(strings.TrimSpace(headers[i]), `"`)
	}

	var rows []map[string]interface{}
	for _, line := range lines[1:] {
		line = strings.TrimRight(line, "\r")
		if strings.TrimSpace(line) == "" {
			continue
		}
		cells := strings.Split(line, ",")
		row := make(map[string]interface{})
		for i, h := range headers {
			if i < len(cells) {
				row[h] = strings.Trim(strings.TrimSpace(cells[i]), `"`)
			}
		}
		rows = append(rows, row)
		if len(rows) >= 150 {
			break
		}
	}

	var textLines []string
	textLines = append(textLines, strings.Join(headers, "\t"))
	for _, row := range rows {
		var cells []string
		for _, h := range headers {
			v := ""
			if val, ok := row[h]; ok {
				v = fmt.Sprintf("%v", val)
			}
			cells = append(cells, v)
		}
		textLines = append(textLines, strings.Join(cells, "\t"))
	}

	return []Section{{
		Name:     "CSV Data",
		Headers:  headers,
		Rows:     rows,
		Text:     strings.Join(textLines, "\n"),
		RowCount: len(rows),
	}}, nil
}

// parseJSONDoc parses a JSON file as a single section.
func parseJSONDoc(data []byte) ([]Section, error) {
	var parsed interface{}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return nil, fmt.Errorf("invalid JSON: %w", err)
	}
	pretty, _ := json.MarshalIndent(parsed, "", "  ")
	text := string(pretty)
	if len(text) > 6000 {
		text = text[:6000]
	}
	return []Section{{
		Name:     "workflow_json",
		Headers:  []string{},
		Rows:     []map[string]interface{}{},
		Text:     text,
		RowCount: 1,
	}}, nil
}

// ─────────────────────────────────────────────────────────────────────────────
// SECTION NAME CLASSIFIER (fallback)
// ─────────────────────────────────────────────────────────────────────────────

// classifyByName uses name-based heuristics to classify sections.
func classifyByName(sections []Section) map[string]string {
	result := make(map[string]string)
	for _, s := range sections {
		nl := strings.ToLower(s.Name)
		switch {
		case containsAny(nl, "dpd", "days past due"):
			result[s.Name] = "dpd_checks"
		case containsAny(nl, "bureau score", "cibil score", "credit score", "score check",
			"individual bureau", "bureau check"):
			result[s.Name] = "bureau_score_checks"
		case containsAny(nl, "outstanding", "overdue", "balance"):
			result[s.Name] = "outstanding_balance_checks"
		case containsAny(nl, "enquir", "inquiry"):
			result[s.Name] = "enquiry_checks"
		case containsAny(nl, "written off", "write off", "written-off", "settlement", "dbt", "lss"):
			result[s.Name] = "written_off_settlement_checks"
		case containsAny(nl, "suit filed", "wilful", "default flag"):
			result[s.Name] = "delinquency_flag_checks"
		case containsAny(nl, "credit card", "cc check"):
			result[s.Name] = "credit_card_checks"
		case containsAny(nl, "new account", "account opening", "account count"):
			result[s.Name] = "account_opening_checks"
		case containsAny(nl, "go no go", "go/no", "gng", "go_no_go"):
			result[s.Name] = "go_no_go"
		case strings.Contains(nl, "surrogate"):
			result[s.Name] = "surrogate_policy"
		case strings.Contains(nl, "eligib") && !strings.Contains(nl, "surrogate"):
			result[s.Name] = "eligibility"
		case containsAny(nl, "scorecard", "score card"):
			result[s.Name] = "scorecard"
		case containsAny(nl, "change", "history", "log", "version", "revision"):
			result[s.Name] = "change_history"
		case containsAny(nl, "pre-read", "pre_read", "preread", "pre read", "introduction",
			"input payload", "1.1 "):
			result[s.Name] = "pre_read"
		case containsAny(nl, "exposure", "limit"):
			result[s.Name] = "modelset"
		case containsAny(nl, "common", "shared"):
			result[s.Name] = "common_rules"
		default:
			result[s.Name] = "go_no_go"
		}
	}
	return result
}

func containsAny(s string, subs ...string) bool {
	for _, sub := range subs {
		if strings.Contains(s, sub) {
			return true
		}
	}
	return false
}

// ─────────────────────────────────────────────────────────────────────────────
// INPUT BUILDER
// ─────────────────────────────────────────────────────────────────────────────

// numericInputs is the set of input variable names that should be typed "number".
var numericInputs = map[string]bool{
	"age": true, "business_vintage": true, "req_loan_amount": true,
	"loan_amount": true, "income": true, "emi": true, "abb": true,
	"foir": true, "credit_limit": true,
}

// BuildInputs scans workflow nodes for variable references and builds the inputs array.
func BuildInputs(nodes []interface{}, samplePayload string) []map[string]interface{} {
	// Serialise the entire nodes slice so we can regex-scan it
	serialised, _ := json.Marshal(nodes)
	ser := string(serialised)

	// Parse sample payload
	var payload map[string]interface{}
	if samplePayload != "" {
		var raw interface{}
		if err := json.Unmarshal([]byte(samplePayload), &raw); err == nil {
			if m, ok := raw.(map[string]interface{}); ok {
				payload = m
			}
		}
	}

	// BRE expects the actual list/dict value, not a JSON string
	schemaFor := func(name string) interface{} {
		if payload == nil {
			return nil
		}
		val, ok := payload[name]
		if !ok {
			return nil
		}
		return val
	}

	newUUID := func() string {
		return newID()
	}

	// Collect payload-derived object inputs
	payloadNS := make(map[string]bool)
	var payloadObjInputs []map[string]interface{}

	if payload != nil {
		var keys []string
		for k := range payload {
			keys = append(keys, k)
		}
		sort.Strings(keys)

		for _, key := range keys {
			val := payload[key]
			isList := false
			var sample map[string]interface{}

			switch v := val.(type) {
			case []interface{}:
				isList = true
				if len(v) > 0 {
					if m, ok := v[0].(map[string]interface{}); ok {
						sample = m
					}
				}
			case map[string]interface{}:
				sample = v
			default:
				continue
			}

			oid := newUUID()
			var children []map[string]interface{}
			var fkeys []string
			for fk := range sample {
				fkeys = append(fkeys, fk)
			}
			sort.Strings(fkeys)
			for _, fk := range fkeys {
				fv := sample[fk]
				dt := "text"
				switch fv.(type) {
				case float64, int, int64:
					dt = "number"
				}
				children = append(children, map[string]interface{}{
					"id":           newUUID(),
					"name":         fk,
					"dataType":     dt,
					"isNullable":   false,
					"defaultInput": nil,
					"children":     nil,
					"parentID":     oid,
					"isArray":      false,
					"schema":       nil,
					"operation":    "",
				})
			}

			payloadObjInputs = append(payloadObjInputs, map[string]interface{}{
				"id":           oid,
				"name":         key,
				"dataType":     "object",
				"isNullable":   false,
				"defaultInput": nil,
				"is_array":     isList,
				"isArray":      isList,
				"parentID":     "",
				"operation":    "",
				"schema":       schemaFor(key),
				"children":     children,
			})
			payloadNS[key] = true
		}
	}

	// Collect BRE-internal node names to skip
	breNodeNames := make(map[string]bool)
	// We'll just collect from serialised node names via regex
	nodeNameRe := regexp.MustCompile(`"name":"([^"]+)"`)
	for _, m := range nodeNameRe.FindAllStringSubmatch(ser, -1) {
		breNodeNames[m[1]] = true
	}

	skipNS := map[string]bool{"bureau": true, "input": true, "bank": true, "model": true, "scorecard": true}
	for k := range breNodeNames {
		skipNS[k] = true
	}
	for k := range payloadNS {
		skipNS[k] = true
	}

	// Scalar input.* fields
	inputVarRe := regexp.MustCompile(`\binput\.([a-zA-Z_][a-zA-Z0-9_]*)\b`)
	inputVarSet := make(map[string]bool)
	for _, m := range inputVarRe.FindAllStringSubmatch(ser, -1) {
		inputVarSet[m[1]] = true
	}

	var inputVarKeys []string
	for k := range inputVarSet {
		if !payloadNS[k] {
			inputVarKeys = append(inputVarKeys, k)
		}
	}
	sort.Strings(inputVarKeys)

	var scalarInputs []map[string]interface{}
	for _, v := range inputVarKeys {
		dt := "text"
		if numericInputs[v] {
			dt = "number"
		}
		scalarInputs = append(scalarInputs, map[string]interface{}{
			"id":           newUUID(),
			"name":         v,
			"dataType":     dt,
			"isNullable":   true,
			"defaultInput": "",
			"is_array":     false,
			"schema":       nil,
		})
	}

	// Bank object input
	var bankInputs []map[string]interface{}
	if !payloadNS["bank"] {
		bankVarRe := regexp.MustCompile(`\bbank\.([a-zA-Z_][a-zA-Z0-9_]*)\b`)
		bankSet := make(map[string]bool)
		for _, m := range bankVarRe.FindAllStringSubmatch(ser, -1) {
			bankSet[m[1]] = true
		}
		if len(bankSet) > 0 {
			var bankFields []string
			for f := range bankSet {
				bankFields = append(bankFields, f)
			}
			sort.Strings(bankFields)

			oid := newUUID()
			var children []map[string]interface{}
			for _, f := range bankFields {
				children = append(children, map[string]interface{}{
					"id":           newUUID(),
					"name":         f,
					"dataType":     "number",
					"isNullable":   false,
					"defaultInput": nil,
					"children":     nil,
					"parentID":     oid,
					"isArray":      false,
					"schema":       nil,
					"operation":    "",
				})
			}
			bankInputs = append(bankInputs, map[string]interface{}{
				"id":           oid,
				"name":         "bank",
				"dataType":     "object",
				"isNullable":   false,
				"defaultInput": nil,
				"is_array":     true,
				"isArray":      true,
				"parentID":     "",
				"operation":    "",
				"schema":       schemaFor("bank"),
				"children":     children,
			})
		}
	}

	// Other namespace object inputs
	allNSRe := regexp.MustCompile(`\b([a-z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b`)
	nsFields := make(map[string]map[string]bool)
	for _, m := range allNSRe.FindAllStringSubmatch(ser, -1) {
		ns, field := m[1], m[2]
		if !skipNS[ns] {
			if nsFields[ns] == nil {
				nsFields[ns] = make(map[string]bool)
			}
			nsFields[ns][field] = true
		}
	}

	arrayNSRe := regexp.MustCompile(`\b(?:all|any|none|one|filter|map|sum|count|find|findIndex|reduce|groupBy|sortBy)\s*\(\s*([a-z][a-zA-Z0-9_]*)`)
	arrayNS := make(map[string]bool)
	for _, m := range arrayNSRe.FindAllStringSubmatch(ser, -1) {
		arrayNS[m[1]] = true
	}

	var nsKeys []string
	for ns := range nsFields {
		nsKeys = append(nsKeys, ns)
	}
	sort.Strings(nsKeys)

	var otherObjInputs []map[string]interface{}
	for _, ns := range nsKeys {
		fields := nsFields[ns]
		var fkeys []string
		for f := range fields {
			fkeys = append(fkeys, f)
		}
		sort.Strings(fkeys)

		oid := newUUID()
		var children []map[string]interface{}
		for _, f := range fkeys {
			children = append(children, map[string]interface{}{
				"id":           newUUID(),
				"name":         f,
				"dataType":     "text",
				"isNullable":   false,
				"defaultInput": nil,
				"children":     nil,
				"parentID":     oid,
				"isArray":      false,
				"schema":       nil,
				"operation":    "",
			})
		}
		otherObjInputs = append(otherObjInputs, map[string]interface{}{
			"id":           oid,
			"name":         ns,
			"dataType":     "object",
			"isNullable":   false,
			"defaultInput": nil,
			"is_array":     arrayNS[ns],
			"isArray":      arrayNS[ns],
			"parentID":     "",
			"operation":    "",
			"schema":       schemaFor(ns),
			"children":     children,
		})
	}

	// Combine: payload objects + bank + other + scalars
	var result []map[string]interface{}
	result = append(result, payloadObjInputs...)
	result = append(result, bankInputs...)
	result = append(result, otherObjInputs...)
	result = append(result, scalarInputs...)
	return result
}
