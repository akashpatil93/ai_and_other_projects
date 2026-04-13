"""
LLM prompts for credit policy → workflow JSON conversion.
Contains all domain knowledge: field mappings, expression syntax, and per-section prompts.
"""

# ─────────────────────────────────────────────────────────────────────────────
# FIELD MAPPING TABLES
# ─────────────────────────────────────────────────────────────────────────────

BUREAU_FIELDS = """
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
| CIBIL Bureau Score / Bureau Score             | bureau.bureauscore                                  |
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
"""

BANK_FIELDS = """
## Bank Statement Fields  (prefix: bank.)
These come from the Bank Statement data source. Use the exact variable names below.

### Average Balance & Cash Flow
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Average Bank Balance (ABB)                    | bank.abb                                            |
| Average End-of-Day Balance                    | bank.eod_balance_avg                                |
| Min End-of-Day Balance (last 3M)              | bank.eod_balance_min_3mo                            |
| Average Monthly Credits (income)              | bank.income_avg                                     |
| Average Monthly Debits (expenses)             | bank.expense_avg                                    |
| Monthly income M+0 (current month)            | bank.income_0                                       |
| Monthly income M-1                            | bank.income_1                                       |
| Monthly income M-2                            | bank.income_2                                       |
| Monthly income M-3                            | bank.income_3                                       |
| Monthly income M-4                            | bank.income_4                                       |
| Monthly income M-5                            | bank.income_5                                       |
| Monthly income M-6                            | bank.income_6                                       |
| Monthly income M-7 to M-11 (older months)    | bank.income_7 … bank.income_11                      |
| Monthly expense M+0 (current month)           | bank.expense_0                                      |
| Monthly expense M-1 to M-11                   | bank.expense_1 … bank.expense_11                    |

### Salary / Regular Credit
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Salary credit count (last 3M)                 | bank.salary_credit_count_3mo                        |
| Salary credit count (last 6M)                 | bank.salary_credit_count_6mo                        |
| Average salary credit amount                  | bank.salary_credit_avg                              |
| Last salary credit amount                     | bank.salary_credit_last                             |
| Months since last salary credit               | bank.months_since_last_salary                       |

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
| Bounce rate (bounces / total transactions)    | bank.bounce_rate                                    |

### EMI & Obligation
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Total EMI debit amount (last 3M avg)          | bank.emi_debit_avg_3mo                              |
| Total EMI debit amount (last 6M avg)          | bank.emi_debit_avg_6mo                              |
| EMI to income ratio (bank-derived FOIR)       | bank.emi_to_income_ratio                            |
| Number of unique EMI debits (last 3M)         | bank.emi_debit_count_3mo                            |
| Recurring debit count (NACH/SI)               | bank.recurring_debit_count_3mo                      |

### Cash Transactions
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Average cash withdrawal (monthly)             | bank.cash_withdrawal_avg                            |
| Cash withdrawal to income ratio               | bank.cash_to_income_ratio                           |
| Average cash deposit (monthly)                | bank.cash_deposit_avg                               |

### UPI & Digital Transactions
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| UPI credit transaction count (last 3M)        | bank.upi_credit_count_3mo                           |
| UPI debit transaction count (last 3M)         | bank.upi_debit_count_3mo                            |
| UPI credit amount (last 3M)                   | bank.upi_credit_amt_3mo                             |
| UPI debit amount (last 3M)                    | bank.upi_debit_amt_3mo                              |

### Overdraft / OD Utilization
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Overdraft utilization percentage              | bank.od_utilization_pct                             |
| Number of days OD utilized (last 3M)          | bank.od_days_3mo                                    |

### Vintage & Summary
| Policy Document Term                          | JSON Field                                          |
|-----------------------------------------------|-----------------------------------------------------|
| Bank statement vintage (months available)     | bank.vintage_months                                 |
| Number of accounts in statement               | bank.account_count                                  |
| Total transaction count (last 3M)             | bank.total_txn_count_3mo                            |
"""

INPUT_FIELDS = """
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
| Shell Companies SEBI          | input.shell_companies_by_sebi_presence        | text   |
| UNSC Sanctions                | input.unsc_sanctions_list_presence            | text   |
| Watch Out Investors           | input.watch_out_investors_presence            | text   |
| NHB Wilful Defaulter          | input.nhb_wilful_defaulter                    | text   |
| Debarred Entities             | input.debarred_entities                       | text   |
| Arbitral Awards               | input.arbitral_awards                         | text   |
| Defaulting Client             | input.defaulting_client                       | text   |
| EU Sanctions                  | input.european_union_sanctions                | text   |
| Expelled Members              | input.expelled_members                        | text   |
| HM Treasury List              | input.her_majesteys_treasury_list             | text   |
| Interpol Red Notice           | input.interpol_rednotice                      | text   |
| IRDA Blacklisted              | input.irda_blacklisted_agents                 | text   |
| MCA Proclaimed Offenders      | input.mca_proclaimed_offenders                | text   |
| UAPA List                     | input.unlawful_activities_prevention_act_list | text   |
| Profile                       | input.profile                                 | text   |
| Requested Loan Amount         | input.req_loan_amount                         | number |
"""

MODEL_FIELDS = """
## Derived Fields from the "model" modelSet node
These are computed by the "model" modelSet that runs before all rule checks.
Reference them from other nodes as  model.<expression_name>

| Variable           | Expression name  | Description                            |
|--------------------|------------------|----------------------------------------|
| HIT / NO-HIT       | hit_no_hit       | true = bureau record found             |
| Age at maturity    | age_at_maturity  | applicant age at loan end              |

Reference syntax from a ruleSet or another modelSet:
  model.hit_no_hit          → boolean derived in the "model" modelSet
  scorecard.<feature_name>  → numeric output of a scorecard modelSet expression
"""

# ─────────────────────────────────────────────────────────────────────────────
# EXPRESSION REFERENCE RULES
# ─────────────────────────────────────────────────────────────────────────────

EXPRESSION_REF_RULES = """
## CRITICAL: How to reference expression values between nodes

### Rule 1 — Within the same modelSet: use the expression name directly
If expression_B is defined after expression_A inside the SAME modelSet, expression_B
can reference expression_A by its bare name:

  modelSet "offer_calc":
    expression_A: name="max_emi",  condition="(input.income - bureau.obligation) * 0.7"
    expression_B: name="amount",   condition="PV(interest, max_tenure, max_emi, 0, 0)"
                                                            ↑                ↑
                                    bare names — same modelSet, defined earlier in seqNo

### Rule 2 — Across different nodes: prefix with the SOURCE node name
If the value was computed in a different modelSet (or is the outcome of a ruleSet),
prefix with that node's name:

  <source_node_name>.<expression_name>

  Examples:
    model.hit_no_hit              → "hit_no_hit" computed in the "model" modelSet
    scorecard.bureau_score_woe    → expression in the "scorecard" modelSet
    go_no_go_checks.decision      → the "decision" outcome of the "go_no_go_checks" ruleSet
    surrogate_policy_checks.decision → outcome of the surrogate ruleSet

### Rule 3 — Node execution order matters
A node can only reference outputs of nodes that appear EARLIER in the workflow.
The workflow order is:
  Start → bureau (dataSource) → bank (dataSource, if bank vars used)
        → scorecard (optional modelSet) → model (optional modelSet)
        → [muted_<name> ruleSets] → [active ruleSets]
        → final_decision (branch) → eligibility (optional modelSet) → end

So:
  - "model" can reference bureau.*, bank.*, and input.* only
  - ruleSet nodes can reference bureau.*, bank.*, input.*, model.*, scorecard.*
  - "eligibility" can reference all of the above plus ruleSet decisions

### Summary table
| Where you are writing  | To use a value from       | Write                          |
|------------------------|---------------------------|--------------------------------|
| Inside modelSet M      | Earlier expression in M   | expression_name                |
| Inside modelSet M      | Expression in modelSet N  | N.expression_name              |
| Inside ruleSet R       | Expression in modelSet N  | N.expression_name              |
| Inside branch          | RuleSet outcome           | ruleset_name.decision          |
"""

# ─────────────────────────────────────────────────────────────────────────────
# EXPRESSION SYNTAX GUIDE
# ─────────────────────────────────────────────────────────────────────────────

EXPRESSION_SYNTAX = """
## Expression Language Syntax

Data source prefixes (external inputs):
  bureau.*   → bureau pull fields (see Bureau Fields table)
  bank.*     → bank statement fields (see Bank Fields table)
  input.*    → application/request fields (see Input Fields table)
              If a policy variable is not in bureau or bank tables → use input.*

Computed value references (see Expression Reference Rules above):
  <modelset_name>.<expr_name>   → cross-node reference
  <expr_name>                   → within same modelSet (bare name)
  <ruleset_name>.decision       → pass/reject outcome of a ruleSet

Operators:
  Comparison : >=  <=  ==  !=  >  <
  Logical    : &&  ||  and  or  !
  Nil check  : field == nil   (field is missing / null)
  String     : input.field == "value"
  Grouping   : (expr1) && (expr2)

## CRITICAL: Converting Policy Rules

### Always invert REJECT conditions into APPROVE conditions
The workflow engine evaluates approveCondition — it must be TRUE to PASS.

  "Reject if bureau.max_overdue > 2000"
  → approveCondition: "bureau.max_overdue <= 2000 || bureau.max_overdue == nil"

  "Reject if bureau.cnt_dbt_lss >= 1"
  → approveCondition: "bureau.cnt_dbt_lss == 0 || bureau.cnt_dbt_lss == nil"

  "Reject if bureau.max_dpd_inlast12months > 30"
  → approveCondition: "bureau.max_dpd_inlast12months <= 30 || bureau.max_dpd_inlast12months == nil"

### Add nil checks for bureau numeric fields in REJECT conditions
Bureau data can be absent. Always add "|| field == nil" when rejecting on a numeric bureau field.

### Negative list fields use string values
Negative list input fields (NCLT, RBI, UNSC, etc.) store "positive" (found on list = BAD)
or "negative" (not found = GOOD).
  → approveCondition: 'input.nclt_list_presence == "negative" || input.nclt_list_presence == nil'

### Bureau Score with HIT/NO-HIT
HIT/NO-HIT is computed by the "model" modelSet as expression "hit_no_hit".
Reference it from ruleSets or other nodes as  model.hit_no_hit

  "Bureau Score >= 700 and HIT required"
  → approveCondition: "bureau.bureauscore >= 700 && model.hit_no_hit == true"

  "Bureau Score >= 700, NO-HIT also allowed"
  → approveCondition: "(bureau.bureauscore >= 700 && model.hit_no_hit == true) || model.hit_no_hit == false"

### Positive (accept) conditions pass through unchanged
  "Business Vintage >= 12 months"  → approveCondition: "input.business_vintage >= 12"
  "Age between 21 and 65"          → approveCondition: "input.age >= 21 && input.age <= 65"

## Quick-reference Examples
| Policy Text                              | approveCondition                                                           |
|------------------------------------------|----------------------------------------------------------------------------|
| Bureau Score >= 700 – Accept             | bureau.bureauscore >= 700 && model.hit_no_hit == true                      |
| Max Overdue > 2000 – Reject              | bureau.max_overdue <= 2000 \\|\\| bureau.max_overdue == nil                   |
| Write-off count > 0 – Reject            | bureau.cnt_wo_settled_restructured_last24months == 0 \\|\\| ...== nil         |
| NCLT match not found – Accept           | input.nclt_list_presence == "negative" \\|\\| ...== nil                       |
| Suit filed count > 0 – Reject           | bureau.cnt_suit_filed_willful_defaul == 0 \\|\\| ...== nil                    |
| Max DPD last 24M > 30 – Reject          | bureau.max_dpd_inlast24months <= 30 \\|\\| ...== nil                          |
| Business Vintage >= 12 months – Accept  | input.business_vintage >= 12                                               |
| Use scorecard WOE sum in eligibility    | scorecard.total_score + model.age_at_maturity                              |
| EMI using earlier expr in same modelSet | PV(interest, max_tenure, max_emi, 0, 0)   ← bare names, same modelSet     |
"""

# ─────────────────────────────────────────────────────────────────────────────
# MASTER SYSTEM PROMPT
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = f"""You are a credit policy expert who converts policy documents into structured
workflow JSON for a Business Rule Engine (BRE) platform.

Your responsibilities:
1. Read credit policy rules from document text or tables.
2. Map field names to the correct JSON variable namespaces.
3. Convert natural-language conditions to the expression syntax.
4. ALWAYS invert reject conditions into approve conditions.
5. Identify muted / inactive rules and mark them muted=true.
6. Use the correct cross-node reference syntax (see Expression Reference Rules).
7. Return ONLY valid JSON — no markdown fences, no explanations.
8. NEVER leave approveCondition blank. If a variable is not in the bureau or bank
   dictionaries, declare it as input.<variable_name> and write the rule against it.

## Variable Namespace Rules (CRITICAL)
There are exactly three data source namespaces:
  bureau.*  → Credit bureau pull fields (CIBIL, Experian, Equifax, CRIF). See Bureau Fields table.
  bank.*    → Bank statement analysis fields (ABB, bounces, EMI, salary, UPI, etc.). See Bank Fields table.
  input.*   → Everything else — application data, user-provided fields, policy parameters.
              When a policy variable is NOT in the bureau or bank tables, use input.<name>.

{BUREAU_FIELDS}
{BANK_FIELDS}
{INPUT_FIELDS}
{MODEL_FIELDS}
{EXPRESSION_REF_RULES}
{EXPRESSION_SYNTAX}
"""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION CLASSIFICATION PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_classify_sections_prompt(sections_summary: str) -> str:
    return f"""Classify the following document sections by their purpose in a credit policy workflow.

SECTIONS:
{sections_summary}

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
- "Input Payload" or variable definition tables → "pre_read" (SKIP).

Return ONLY valid JSON, no explanation:
{{"<section_name>": "<type>"}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# GO/NO-GO RULES PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_go_no_go_prompt(section_content: str) -> str:
    return f"""
{SYSTEM_PROMPT}

Extract every Go/No-Go policy rule from the section below and produce a JSON array.

MUTED RULES: Rules marked "Muted", "M", "Inactive", or "Not in force" get muted=true.
They are still evaluated but never block approval.

UPSTREAM NODES AVAILABLE (in execution order before this ruleSet):
  bureau.*          → all bureau pull fields (see Bureau Fields table)
  bank.*            → all bank statement fields (see Bank Fields table)
  input.*           → all application input fields (anything not in bureau or bank tables)
  model.hit_no_hit  → true/false, computed in the "model" modelSet
  model.age_at_maturity → number, computed in the "model" modelSet
  scorecard.<name>  → if a scorecard modelSet exists, its expression outputs

SECTION CONTENT:
{section_content}

For each rule output:
{{
  "name": "RULE_CODE: Short description",
  "approveCondition": "expression — use bureau.*, bank.*, input.*, or model.<expr>",
  "cantDecideCondition": "",
  "muted": false
}}

MANDATORY:
- INVERT every reject condition into an approve condition.
- NEVER leave approveCondition blank. If a variable is not in the bureau or bank tables,
  declare it as input.<variable_name> and write the rule using it.
- Add "|| field == nil" for bureau and bank numeric fields (data may be absent).
- For negative-list input fields use: 'input.field == "negative" || input.field == nil'
- Reference HIT/NO-HIT as model.hit_no_hit (NOT as a bureau field).
- Include the rule code (GPR01, PR01, etc.) in the name when present.

Return ONLY a valid JSON array:
[{{"name": "...", "approveCondition": "...", "cantDecideCondition": "", "muted": false}}]
"""


# ─────────────────────────────────────────────────────────────────────────────
# SURROGATE POLICY PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_surrogate_policy_prompt(section_content: str) -> str:
    return f"""
{SYSTEM_PROMPT}

Extract every surrogate policy rule from the section below.
Rules marked "Muted", "M", "Inactive", or "Not in force" get muted=true.

UPSTREAM NODES AVAILABLE (in execution order before this ruleSet):
  bureau.*                     → all bureau pull fields (see Bureau Fields table)
  bank.*                       → all bank statement fields (see Bank Fields table)
  input.*                      → all application input fields (anything not in bureau or bank)
  model.hit_no_hit             → bool, from the "model" modelSet
  model.age_at_maturity        → number, from the "model" modelSet
  scorecard.<name>             → scorecard expression outputs (if scorecard exists)
  go_no_go_checks.decision     → "pass" / "reject" outcome of the go_no_go ruleSet (if it exists)

SECTION CONTENT:
{section_content}

For each rule output:
{{
  "name": "CODE: Description",
  "approveCondition": "expression",
  "cantDecideCondition": "",
  "muted": false
}}

Apply the same inversion and nil-check rules as for Go/No-Go rules.
- NEVER leave approveCondition blank. If a variable is not in the bureau or bank tables,
  declare it as input.<variable_name> and write the rule using it.
- Add "|| field == nil" for bureau and bank numeric fields.
Use model.<expr> to reference derived model values; do NOT invent new model.* names.

Return ONLY a valid JSON array:
[{{"name": "...", "approveCondition": "...", "cantDecideCondition": "", "muted": false}}]
"""


# ─────────────────────────────────────────────────────────────────────────────
# BUREAU CATEGORY RULESET PROMPT
# ─────────────────────────────────────────────────────────────────────────────

# Human-readable descriptions for each bureau ruleset category
BUREAU_CATEGORY_DESCRIPTIONS = {
    "dpd_checks": "DPD (Days Past Due) based rules — max DPD thresholds and DPD count limits",
    "bureau_score_checks": "Bureau score thresholds — CIBIL, Experian, Equifax, CRIF minimum score rules",
    "outstanding_balance_checks": "Outstanding balance and overdue amount rules",
    "enquiry_checks": "Credit enquiry count rules within specific lookback periods",
    "written_off_settlement_checks": "Written-off, settled, restructured, DBT and LSS account rules",
    "delinquency_flag_checks": "Delinquency flags — suit filed, wilful default, written-off indicators",
    "credit_card_checks": "Credit card specific rules — utilization, CC outstanding, CC DPD",
    "account_opening_checks": "New account opening and total account count rules",
}


def get_bureau_ruleset_prompt(section_content: str, ruleset_name: str) -> str:
    description = BUREAU_CATEGORY_DESCRIPTIONS.get(
        ruleset_name,
        f"Bureau policy rules for category: {ruleset_name}"
    )
    return f"""
{SYSTEM_PROMPT}

Extract every policy rule from the section below. These rules belong to the "{ruleset_name}" ruleset.
Category focus: {description}

MUTED RULES: Rules marked "Muted", "M", "Inactive", or "Not in force" get muted=true.

UPSTREAM NODES AVAILABLE (in execution order before this ruleSet):
  bureau.*          → all bureau pull fields (use exact variable names from the Bureau Fields table)
  bank.*            → all bank statement fields (see Bank Fields table)
  input.*           → all application input fields (anything not in bureau or bank tables)
  model.hit_no_hit  → true/false, computed in the "model" modelSet
  model.age_at_maturity → number, computed in the "model" modelSet
  scorecard.<name>  → if a scorecard modelSet exists, its expression outputs

SECTION CONTENT:
{section_content}

For each rule output:
{{
  "name": "RULE_CODE: Short description",
  "approveCondition": "expression — use bureau.*, bank.*, input.*, or model.<expr>",
  "cantDecideCondition": "",
  "muted": false
}}

MANDATORY:
- INVERT every reject condition into an approve condition.
- NEVER leave approveCondition blank. If a variable is not in the bureau or bank tables,
  declare it as input.<variable_name> and write the rule using it.
- Add "|| field == nil" for bureau and bank numeric fields (data may be absent).
- Use exact bureau variable names from the Bureau Fields table (e.g. bureau.max_dpd_inlast12months).
- Use exact bank variable names from the Bank Fields table (e.g. bank.abb, bank.ach_bounce_count_3mo).
- Reference HIT/NO-HIT as model.hit_no_hit (NOT as a bureau field).
- Include the rule code (e.g. GPR01, PR01, BR01) in the name when present.

Return ONLY a valid JSON array:
[{{"name": "...", "approveCondition": "...", "cantDecideCondition": "", "muted": false}}]
"""


MODELSET_EXPRESSION_TYPES = """
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
Use when: output depends on combinations of variable ranges (e.g. interest rate by score × income).
  {
    "name": "interest_rate",
    "type": "decisionTable",
    "condition": "",
    "decisionTableRules": {
      "default": "22",
      "headers": ["bureau.score", "input.income"],
      "rows": [
        {"columns": [{"name": "bureau.score", "value": "> 800"}, {"name": "input.income", "value": "> 80000"}], "output": "12.12"},
        {"columns": [{"name": "bureau.score", "value": "> 800"}, {"name": "input.income", "value": "60000..80000"}], "output": "14"}
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
A 2D grid: one row-variable × one column-variable → cell output value.
Use when: output is a grid lookup (e.g. risk bucket by age × obligation bracket).
  {
    "name": "risk_bucket",
    "type": "matrix",
    "condition": "",
    "matrix": {
      "globalRowIndex": <total_row_conditions_count>,
      "globalColumnIndex": <total_col_conditions_count>,
      "rows": [
        {
          "header": "input.age",
          "index": 0,
          "conditions": [
            {"index": 0, "condition": "21..30", "child": null},
            {"index": 1, "condition": "30..45", "child": null}
          ]
        },
        {"header": "No matches", "index": <N>, "isNoMatches": true,
         "conditions": [{"index": <N>, "condition": "true", "child": null}]}
      ],
      "columns": [
        {
          "header": "bureau.obligation",
          "index": 0,
          "conditions": [
            {"index": 0, "condition": "< 35000", "child": null},
            {"index": 1, "condition": "35000..65000", "child": null}
          ]
        },
        {"header": "No matches", "index": <M>, "isNoMatches": true,
         "conditions": [{"index": <M>, "condition": "true", "child": null}]}
      ],
      "values": [
        ["A", "B", "F"],
        ["A", "A", "F"],
        ["F", "F", "F"]
      ]
    }
  }

  matrix rules:
  - Always add a "No matches" row (isNoMatches: true) at the end of rows array.
  - Always add a "No matches" column (isNoMatches: true) at the end of columns array.
  - globalRowIndex = index value of the "No matches" row.
  - globalColumnIndex = index value of the "No matches" column.
  - values is a 2D array: rows[i] × columns[j] → values[i][j].
    The "No matches" row and column must also have entries (usually a fallback like "F" or "0").
  - Condition syntax: "21..30", "< 35000", "> 100000", "true"
"""


# ─────────────────────────────────────────────────────────────────────────────
# ELIGIBILITY COMPUTATIONS PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_eligibility_prompt(section_content: str) -> str:
    return f"""
{SYSTEM_PROMPT}

Extract eligibility computation formulas from the section below.
These become entries in the "eligibility" modelSet node.
Choose the correct type for each expression.

{MODELSET_EXPRESSION_TYPES}

UPSTREAM NODES AVAILABLE (all run before the eligibility modelSet):
  bureau.*                          → raw bureau fields
  bank.*                            → bank statement fields (ABB, salary, bounce, EMI, etc.)
  input.*                           → application input fields (anything not in bureau or bank)
  model.<expr>                      → e.g. model.hit_no_hit, model.age_at_maturity
  scorecard.<feature>               → scorecard expression outputs (if scorecard exists)
  go_no_go_checks.decision          → "pass"/"reject" (if go_no_go ruleSet exists)
  surrogate_policy_checks.decision  → "pass"/"reject" (if surrogate ruleSet exists)

WITHIN THE SAME "eligibility" modelSet:
  Reference earlier expressions by bare name (no prefix).
  Example: if "max_emi" is defined at seqNo 0, a later expression at seqNo 1 can use just "max_emi".

SECTION CONTENT:
{section_content}

Common eligibility variables: abb, foir, max_eligible_loan, emi, net_income.

Rules:
- Simple formulas → type "expression"  (use bare name for same-modelSet refs, node.name for cross-node)
- Lookup tables with flat row/column conditions → type "decisionTable"
- 2D grid (one row-variable × one column-variable) → type "matrix"

Return ONLY a valid JSON array of expression objects.
Each object must have at minimum: name, type, condition (empty string if decisionTable/matrix).
Include decisionTableRules for decisionTable type, matrix object for matrix type.
"""


# ─────────────────────────────────────────────────────────────────────────────
# SCORECARD FEATURES PROMPT
# ─────────────────────────────────────────────────────────────────────────────

def get_scorecard_prompt(section_content: str) -> str:
    return f"""
{SYSTEM_PROMPT}

Extract scorecard model features from the section below.
Each feature becomes an expression in the "scorecard" modelSet node.

{MODELSET_EXPRESSION_TYPES}

UPSTREAM NODES AVAILABLE (all run before the scorecard modelSet):
  bureau.*   → raw bureau fields (use these as decisionTable/matrix input variables)
  bank.*     → bank statement fields
  input.*    → application input fields (anything not in bureau or bank tables)

WITHIN THE SAME "scorecard" modelSet:
  Reference earlier expressions by bare name (no prefix).
  Example: a "total_score" expression at seqNo N can sum earlier feature expressions
  by bare name: feature_1 + feature_2 + feature_3

SECTION CONTENT:
{section_content}

Choose the correct type for each feature:
- Single-variable WOE bins → type "decisionTable" (one header, one column condition per row)
- Two-variable interaction grid → type "matrix"
- Calculated score total (sum of WOE features) → type "expression", use bare feature names

Map all input variable names to the bureau.* namespace using the Bureau Fields table.
Use "0" as the default for decisionTable WOE features.

Return ONLY a valid JSON array of expression objects.
"""
