<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# PostgreSQL Service Rule
Whenever PostgreSQL needs to be started or checked, use:
`pg_ctl -D "D:\Programs\PostgreSql\17\data" start`
PostgreSQL is installed on an external drive at `D:\Programs\PostgreSql\17\`.
To check status: `& "D:\Programs\PostgreSql\17\bin\pg_ctl.exe" -D "D:\Programs\PostgreSql\17\data" status`

# AI Agent Benchmarks & Evaluation Plan
When working on agent guardrails, evaluators, thresholds, or Langfuse datasets/experiments, read `AGENT_BENCHMARKS_AND_EVAL_PLAN.md` at the repository root for the industry benchmark matrix (`FinanceBench`, `FinBen`, `FinQA`, `DocRED`, `ALCE`, `Financial PhraseBank`), SOTA vs. baseline thresholds, and pending tasks (`BENCH-001` through `BENCH-006`).


