# FinnWinn / MarketPulse — AI Agent Benchmarks, Thresholds & Evaluation Roadmap

> **Purpose for Coding Agents:** This document defines the industry-standard financial AI benchmarks, production vs. state-of-the-art (SOTA) thresholds, current guardrail/evaluator wiring, and the actionable task backlog (`BENCH-001` to `BENCH-006`) for calibrating and benchmarking all 8 agents in MarketPulse.

---

## 1. Master Benchmark & Threshold Matrix (All 8 Agents)

| Agent | Codebase File | Core Responsibility | Mapped Industry Benchmarks | Primary Evaluation Metrics | Industry Baseline (Avg Production) | Institutional SOTA (Highest Threshold) | Current MarketPulse Thresholds |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| **1. Footprint Agent** | `backend/ingestion/footprint_agent.py` | Autonomous SEC 10-K, Wikipedia & Web supply-chain/hub extraction via MCP | **FinanceBench** (Patronus AI), **DocRED / Re-DocRED**, **ALCE** (Citation Eval), **RAGAS** | Faithfulness, Citation Precision/Recall, Entity-Relation F1, Polarity/Negation Accuracy | **0.70 – 0.78** *(DocRED F1 ~0.68; ALCE Citation ~0.70)* | **0.88 – 0.95+** *(DocRED SOTA F1 ~0.77; ALCE Citation $\ge$ 0.90; 0 hallucinations)* | **Grade A $\ge$ `0.85`** (`0` hallucinations); **Pass $\ge$ `0.70`** (`backend/ingestion/evaluation.py`) |
| **2. Sentiment Agent** | `backend/agents/sentiment_agent.py` | News & aspect-level financial polarity scoring (`-1.0` to `+1.0`) | **Financial PhraseBank (FPB)**, **FiQA-SA (Task 1)**, **SEntFiN 1.1** | Macro-F1 & Sentiment Intensity $R^2$ | **0.78 – 0.84** *(FPB 75%-agree)* | **0.92 – 0.97** *(FinBERT / FinMA on FPB 100%-agree; FiQA $R^2 \ge 0.82$)* | **Grade A $\ge$ `0.85`**; **Pass $\ge$ `0.70`** (`backend/agents/evaluator.py`) |
| **3. News Agent** | `backend/agents/news_agent.py` | Entity-resolved wire & headline retrieval and summarization | **FinBen (IE Suite)**, **ECTSum**, **RAGAS Context Precision** | Entity Alias Relevance, Faithfulness, ROUGE-L | **0.75 – 0.82** | **0.90 – 0.96+** *(Zero off-ticker articles; 100% alias resolution)* | `-0.40` faithfulness penalty if `0` articles match ticker or `COMPANY_ALIASES` |
| **4. Fundamentals Agent** | `backend/agents/fundamentals_agent.py` | Balance sheet, P/E, ROE, Profit Margin, FCF & D/E valuation analysis | **FinQA**, **ConvFinQA**, **TAT-QA**, **DocMath-Eval** | Execution Accuracy & Numeric Match Tolerance ($\pm 5\%$) | **0.65 – 0.75** *(Zero-shot LLM table math)* | **0.85 – 0.98+** *(Deterministic Python math + LLM narrative consistency)* | Deterministic `yfinance` metrics + **Pass $\ge$ `0.70`** |
| **5. Technical Agent** | `backend/agents/technical_agent.py` | Price action, RSI(14), MACD, 50/200-day SMA & Support/Resistance | **FinBen (TA & Forecasting)**, **StockBench** | Regime-to-Indicator Consistency | **0.70 – 0.80** | **0.95 – 1.00** *(Zero contradiction between RSI/SMA levels and trend label)* | **Grade A $\ge$ `0.85`**; **Pass $\ge$ `0.70`** |
| **6. Risk Agent** | `backend/agents/risk_agent.py` & `backend/agents/risk_phase4.py` | Volatility, Beta, 95% VaR, 97.5% ES, Kupiec POF & Ex-Ante/Ex-Post Bias | **Basel III / Kupiec POF Backtest**, **Christoffersen Independence**, **RiskMetrics Vol Bias** | VaR Exception Rate ($p=0.05$), Vol Bias ($\sigma(z_t) \approx 1.0$), Regime Label Consistency | **Bias Band: `[0.75, 1.25]`**; Consistency $\ge$ **0.75** | **Bias Band: `[0.80, 1.20]`** (Unbiased $= 1.00$); Consistency $\ge$ **0.95** | **Bias Band: `[0.80, 1.20]`** (`risk_phase4.py:L542`); Vol ($20\%/40\%$) & Beta ($[0.8, 1.2]$) checks (`evaluator.py:L65-L86`) |
| **7. Equity Research Agent** | `backend/agents/equity_reasearch_agent.py` | Bull/Bear thesis, economic moat, price target & catalysts | **FinanceBench**, **BizBench**, **CFA Level II/III Equity Cases** | Thesis-to-Metric Entailment & Target-to-Recommendation Polarity | **0.70 – 0.78** | **0.88 – 0.94** *(Zero polarity conflicts between BUY/SELL and upside %; grounded moat)* | Wide Moat requires ROE & Margin $\ge 10\%$; BUY/SELL must align with upside/downside (`evaluator.py:L46-L63`) |
| **8. Portfolio Manager (Synthesizer)** | `backend/main.py` (`synthesizer`) | Multi-agent consensus synthesis, conviction rating & model-risk governance | **FinMem**, **TradingAgents**, **FinCon** | Cross-Agent Consensus Alignment & Sub-Agent Degradation Propagation | **0.72 – 0.80** | **0.88 – 0.95** *(Strict grade-capping & conviction haircut when any sub-agent degrades)* | Caps conviction at $\le 6/10$ and propagates worst sub-agent grade (`evaluator.py:L105-L142`) |

---

## 2. Current Guardrail & Evaluation Architecture (Reference for Coding Agents)

### A. Footprint Agent 3-Link Anti-Hallucination Pipeline (`backend/ingestion/guardrails.py`)
1. **Link A (`verify_payload_quote_binding`):**
   * Extracts distinctive entity/location tokens from `hub_name`, `region_name`, or `supplier.name` (filtering out `ENTITY_NOISE_WORDS` and the target company's `subject_stems`).
   * Verifies at least one distinctive token (or its `_stem_token()` stem) appears inside the LLM's `evidence_quote`.
   * **Clause-Scoped Negation & Divestiture Gate (`_detect_entity_negation`):** Splits sentences at clause boundaries (`;`, `.`, `, but`, `, instead`, `, however`) and scans the entity's clause against 10 categories of negation/closure (`NEGATION_AND_CLOSURE_PATTERNS`, e.g., `"no longer"`, `"do not"`, `"closed"`, `"divested"`, `"terminated"`).
2. **Link B (`_split_into_windows` & `evaluate-link-b-sliding-windows`):**
   * Splits `context_corpus` into overlapping **2-sentence sliding windows** to defeat cross-page "Frankenstein / stitched quote" hallucinations.
3. **Link C (`compute-link-c-token-weights` & `evaluate-link-c-proper-noun-gate-and-threshold`):**
   * Weights capitalized proper nouns & numbers at **`1.5x`**, concrete facility/action predicates at **`1.0x`**, and corporate boilerplate stopwords at **`0.25x`**.
   * Forgives first-party coreference (`"We"` / `"Our"` $\leftrightarrow$ `"Tesla"` / `"NVIDIA"`) in official SEC 10-K and Wikipedia corpora.
   * **Proper-Noun Gate:** If a quote contains proper nouns and **zero** of them appear in a 2-sentence window, caps that window's score at **`0.35`**.
   * **Source-Window Polarity Gate:** Even if the LLM omits `"no longer"` from its quote, if the matching 2-sentence source window negates the entity, caps the score at **`0.05`** and blocks semantic fallback rescue.
   * **Hybrid Semantic Fallback (`_hf_embedding_similarity`):** For non-negated borderline paraphrases (`0.20 <= best_window_ratio < 0.70`), queries `sentence-transformers/all-MiniLM-L6-v2` and blends $0.5 \times \text{window\_ratio} + 0.5 \times \text{cosine\_sim}$ when cosine similarity $\ge 0.65$.
4. **Tiered Citation Credibility (`backend/ingestion/evaluation.py`):**
   * Tier 1 (`sec_10k`): **`1.00`**
   * Tier 2 (`wikipedia` / major financial wires): **`0.90`**
   * Tier 3 (`web_search` verified in `retrieved_urls` whitelist): **`0.75`**
   * Tier 4 (`repaired_fallback` / unverified URL): **`0.25`**

### B. Langfuse v4 Observability Integration (`backend/agents/observability.py`)
* All runs emit a nested trace hierarchy (`AGENT` $\rightarrow$ `RETRIEVER` / `GUARDRAIL` / `GENERATION` / `EMBEDDING` / `EVALUATOR`) using Langfuse Python SDK v4 (`start_as_current_observation`, `start_observation`, `propagate_attributes`) and mirror locally to `backend/logs/langfuse_traces.jsonl`.

---

## 2.5. Adapter Protocol: How to Evaluate Our Schema-Bound Agents Against Public Benchmarks

> **Critical Design Note:** Public academic benchmarks (`FinanceBench`, `FinQA`, `DocRED`, `Financial PhraseBank`) are formatted as general Q&A or sentence-level datasets, whereas our 8 MarketPulse agents accept structured inputs (`ticker`, `news`, `metrics`) and return fixed JSON schemas.
> **Never rewrite an agent into a generic Q&A chatbot just to run a benchmark.** Instead, use the **Schema-Projected Adapter Protocol** below so every score measures our actual production functions and JSON schemas:

### 1. `footprint_agent.py` & `guardrails.py` $\leftarrow$ **DocRED + FinanceBench (10-K Item 2) + ALCE Adapter**
* **Why general Q&A doesn't fit:** `footprint_agent` does not answer free-form questions like *"What was FY23 capex?"*; it extracts `{"hubs": [...], "key_suppliers": [...]}` with `evidence_quote` and `source_url`.
* **How the Adapter Evaluates It (Two Levels):**
  1. **End-to-End Agent Extraction Eval (10 Ground-Truth Tickers):**
     * **Input:** Pass `ticker` (e.g., `NVDA`, `AAPL`, `TSLA`, `MSFT`, `TSM`, `VALE`, `ACN`, `CRM`, `JPM`, `PFE`) into `run_autonomous_tool_loop()`.
     * **Ground-Truth Label Set:** For each ticker, maintain a human-verified ground-truth set from its actual SEC 10-K & Wikipedia page:
       ```json
       {
         "ticker": "NVDA",
         "ground_truth_hubs": ["Santa Clara", "Hsinchu", "Taiwan"],
         "ground_truth_suppliers": ["TSMC", "Taiwan Semiconductor", "SK Hynix", "Samsung", "Micron", "Foxconn"],
         "forbidden_negated_traps": ["own wafer fabrication", "Shinjuan"]
       }
       ```
     * **Real Computed Metrics:**
       * $\text{Entity Precision} = \frac{|\text{Extracted Entities} \cap \text{Ground Truth}|}{|\text{Extracted Entities}|}$
       * $\text{Entity Recall} = \frac{|\text{Extracted Entities} \cap \text{Ground Truth}|}{|\text{Ground Truth Core Entities}|}$
       * $\text{ALCE Citation Precision} = \frac{\text{Extracted Entities with Link A=True and Link B/C} \ge 0.70}{|\text{Extracted Entities}|}$
  2. **Guardrail Red-Team Classifier Eval (`apply_footprint_guardrails` on HaluBench / DocRED pairs):**
     * **Input:** Feed `(context_corpus, candidate_hub_or_supplier, expected_is_grounded: bool)` pairs directly into `apply_footprint_guardrails()` (testing verbatim quotes, `"We" -> "Company"` coreference, cross-page stitched quotes, negated `"no longer operate in Shinjuan"` quotes, and unwhitelisted URLs).
     * **Real Computed Metrics:** Binary classification **Precision, Recall, F1, and False-Positive Rate (FPR)** comparing `(final_item_score >= 0.70 and link_a_bound)` against `expected_is_grounded`.

### 2. `sentiment_agent.py` $\leftarrow$ **Financial PhraseBank (FPB) & FiQA-SA Adapter**
* **Agent Signature:** `await sentiment_agent(ticker: str, news: dict, consensus: str)` takes a `news` dict containing `{"articles": [{"title": "...", "summary": "..."}]}` and outputs `{"sentiment": "bullish|neutral|bearish", "score": float}`.
* **How the Adapter Evaluates It:**
  * Group real labeled sentences from **Financial PhraseBank (`sentences_allagree`)** and **FiQA-SA** into batches of 3 homogeneous-polarity headlines (`positive` $\rightarrow$ expected `"bullish"`, `negative` $\rightarrow$ expected `"bearish"`, `neutral` $\rightarrow$ expected `"neutral"`).
  * Pass `news={"articles": batch}` directly into `sentiment_agent("BENCH", news)` and compute the real **3-class Macro-F1** and **Sign Accuracy** against the FPB ground-truth labels.

### 3. `fundamentals_agent.py`, `technical_agent.py`, `risk_agent.py`, `equity_reasearch_agent.py` $\leftarrow$ **FinQA / TAT-QA / StockBench Snapshot Adapter**
* **Agent Signatures:** Each agent takes deterministic financial/technical metrics (from `yfinance` or a benchmark fixture snapshot) and outputs a structured analyst JSON (`moat`, `recommendation`, `price_target`, `volatility_assessment`, `beta_assessment`, `summary`).
* **How the Adapter Evaluates It:**
  * Construct **Golden Financial Snapshot Fixtures** from real FinQA / TAT-QA / StockBench company profiles (e.g., *Case 1: High-Margin Compounder* with `ROE=0.42, Margin=0.31, D/E=0.3, RSI=55`; *Case 2: Distressed Value Trap* with `ROE=0.03, Margin=0.04, D/E=3.8, Vol=0.48, RSI=76`; *Case 3: Negative-Upside Overvalued Stock* with `current_price=250, target_median=190`).
  * Run the specialist agents + `evaluate_agent_output()` on each fixture and score:
    1. **Structural Constraint Accuracy:** Did `equity_research_agent` refrain from assigning `"wide"` moat when `ROE < 10%`? Did it refrain from assigning `"BUY"` when `price_target < current_price`? Did `risk_agent` label `vol=0.48` as `"high"`?
    2. **FinQA Numeric Entailment Accuracy:** Extract every number/percentage mentioned in the LLM's `summary` string and verify it matches the input snapshot metrics within $\pm 5\%$.


---

## 3. Actionable Benchmark Implementation Backlog (For Coding Agents to Pick Up)

| Task ID | Target Files | Benchmark Standard | Specification | Acceptance Criteria | Priority | Status |
| :--- | :--- | :--- | :--- | :--- | :---: | :---: |
| **BENCH-001** | `backend/agents/risk_phase4.py` | **FinBen / FinQA Differentiated Thresholds** | Replace the flat `min_quality_threshold = 0.70` across all 7 agents in `_ensure_model_risk_seeded()` with task-calibrated institutional thresholds:<ul><li>`fundamentals`, `technical`, `risk`: **`0.82`** (deterministic-math inputs require higher fidelity)</li><li>`equity`, `portfolio_manager`: **`0.78`**</li><li>`sentiment`, `news`: **`0.75`**</li></ul> | `agent_model_risk_controls` seeds differentiated thresholds per agent; `GET /risk/model-risk` displays each agent's calibrated threshold and flags degradation when breached. | **P0** | Pending |
| **BENCH-002** | `backend/agents/evaluator.py` | **FinQA / TAT-QA Numeric Fidelity Check** | Add a deterministic numeric-grounding check `_verify_numeric_claims_in_text(summary_text, raw_metrics)` inside `evaluate_agent_output()` for `fundamentals`, `technical`, `equity_research`, and `risk`. Extract numbers/percentages from the LLM narrative and verify they match `raw_metrics` within $\pm 5\%$ relative tolerance (or $\pm 0.5$ percentage points). | Quoting a $35\%$ profit margin when `raw_metrics["profit_margins"] == 0.18` increments `hallucinations_detected`, reduces `faithfulness_score` by `0.30`, and logs a specific numeric-mismatch warning. | **P0** | Pending |
| **BENCH-003** | `backend/agents/evaluator.py` | **StockBench Technical Regime Check** | Add RSI & Moving-Average regime consistency rules for `technical_agent` in `evaluate_agent_output()`:<ul><li>If `rsi_14 > 70` and narrative claims `"oversold"`, or `rsi_14 < 30` and narrative claims `"overbought"` $\rightarrow$ flag hallucination (`-0.35` consistency).</li><li>If `current_price < ma_50 < ma_200` (death cross / downtrend) and `trend == "bullish"` $\rightarrow$ flag contradiction (`-0.30` consistency).</li></ul> | Unit tests confirm overbought/oversold inversion and price-vs-SMA trend inversion are caught and downgraded to Grade C/FAIL. | **P1** | Pending |
| **BENCH-004** | `backend/scripts/run_benchmark_suite.py` (New) | **FinanceBench + DocRED + ALCE Golden Suite** | Create an automated benchmark runner script that seeds/loads a **20-case Golden Dataset** (`backend/logs/golden_footprint_benchmark.json` + Langfuse Dataset `marketpulse-footprint-bench-v1`) covering:<ul><li>5 Verbatim SEC 10-K Item 2 claims (Expected: `1.00`, PASS)</li><li>4 First-party coreference claims (`"We operate..."` $\leftrightarrow$ `"Tesla operates..."`, Expected: $\ge 0.90$, PASS)</li><li>4 Cross-page stitched / Frankenstein claims (Expected: $< 0.50$, FAIL Link B)</li><li>4 Negated / closed facility claims (`"We no longer operate in Shinjuan, China"`, Expected: $\le 0.15$, FAIL Polarity Gate)</li><li>3 Hallucinated supplier / unwhitelisted URL claims (Expected: FAIL Link A & URL Whitelist)</li></ul> | Running `python backend/scripts/run_benchmark_suite.py` executes all 20 cases in $< 2$ seconds ($0$ LLM cost), reports Precision, Recall, F1, and False-Positive Rate (target: **F1 $\ge 0.95$**, **FPR $= 0.00$**), and uploads the experiment run to Langfuse. | **P0** | Pending |
| **BENCH-005** | `backend/agents/sentiment_agent.py` & `backend/scripts/run_sentiment_bench.py` | **Financial PhraseBank (FPB) & FiQA Calibration** | Create a 15-sentence Financial PhraseBank / FiQA benchmark fixture (`sentences_allagree` positive, negative, and neutral investor statements) to evaluate `sentiment_agent` polarity accuracy and Macro-F1. Enforce in `evaluator.py` that `sentiment_score > 0.25` cannot be labeled `"bearish"` and `sentiment_score < -0.25` cannot be labeled `"bullish"`. | Polarity-vs-score sign mismatch is caught deterministically in `evaluator.py`; FPB benchmark runner logs Macro-F1 (target $\ge 0.88$) to Langfuse. | **P1** | Pending |
| **BENCH-006** | `backend/agents/contradiction_agent.py` (New) | **FinBen Multi-Perspective Epistemic Arbitration** | Build the live Epistemic Arbiter (`contradiction_agent.py`) connecting `fetch_tri_perspective_mesh(ticker)` (`geo_feed_adapter.py`) to `ContradictionRadar.jsx`, scoring narrative divergence between Tier-1 Western Wires, Tier-2 Local On-Ground Hub Press, Tier-3 Corporate PR, and Tier-4 Supplier Feeds with Link A/B/C citation grounding. | Every contradiction card emitted has verified source URLs from at least 2 distinct perspective tiers and passes `apply_footprint_guardrails` with faithfulness $\ge 0.75$. | **P2** | Pending |

---

## 4. Quick Commands for Agents Picking Up This Work

```powershell
# 1. Compile-check all guardrail, evaluator, and observability modules
.\backend\venv\Scripts\python.exe -m py_compile backend\ingestion\guardrails.py backend\ingestion\evaluation.py backend\agents\evaluator.py backend\agents\observability.py backend\agents\risk_phase4.py

# 2. Run Footprint Agent & Guardrails with live Langfuse v4 tracing
.\backend\venv\Scripts\python.exe backend\ingestion\guardrails.py

# 3. Query recent evaluations & model-risk thresholds from PostgreSQL
& "D:\Programs\PostgreSql\17\bin\pg_ctl.exe" -D "D:\Programs\PostgreSql\17\data" status
```
