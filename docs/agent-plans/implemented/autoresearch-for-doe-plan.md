# Autoresearch for DoE Plan

## Context

Karpathy's `autoresearch` is a small autonomous research loop: a coding agent reads a human-authored `program.md`, edits one bounded implementation file, runs a fixed-budget experiment, evaluates one metric, keeps or discards the change, and repeats. Its useful idea for Mirai DoE is not the LLM-training code itself, but the operating pattern: tightly scoped agent experimentation with reproducible runs, explicit metrics, durable logs, and human-authored research instructions.

Mirai DoE already has a Batch Explorer, ONNX surrogate scoring, and an Optimization Loop / Bayesian Optimization workflow. An `autoresearch`-style harness could help improve the DoE engine by letting agents run controlled overnight experiments on candidate generation, BO settings, constraint handling, scoring clarity, and surrogate-model behavior without directly touching the whole application.

## Approach

Add a repo-local autonomous research harness concept for DoE. Keep the first version documentation-first and sandboxed: define a `program.md`-style research brief, a single narrow experiment target, a fixed evaluation budget, and a repeatable scorecard. The agent should propose and test changes only inside an allowlisted experimental area, then produce logs and recommendations for human review before any product code changes are merged.

The recommended first use case is **BO recommendation quality in replay mode**, because this repo already has replay concepts and a clear success condition: suggestions should improve observed weighted objective scores over sequential steps while respecting constraints and preserving scientist-facing interpretability.

## Files to modify

Documentation / planning only for the first phase:

- `docs/agent-plans/implemented/autoresearch-for-doe-plan.md` — this plan.

Future implementation candidates, not part of this first documentation-only step:

- `research/program.md` — human-maintained agent instructions for DoE research loops.
- `research/run_experiment.py` — fixed-budget experiment runner.
- `research/score_experiment.py` — evaluator for replay-mode outcomes.
- `research/logs/*.jsonl` — append-only experiment history.
- `backend/app/services/bayesian_optimization.py` — possible bounded target after the harness exists.

## Reuse

- `docs/tutorials/BO_OPTIMIZATION_LOOP_GUIDE.md` for the current BO/replay workflow and terminology.
- `docs/agent-plans/implemented/add_bo_loop_agent_task.md` for intended BO architecture, candidate suggestion behavior, and acceptance criteria.
- Repo-local skills:
  - `.pi/skills/bayesian-optimization-feature/SKILL.md`
  - `.pi/skills/surrogate-model-debugging/SKILL.md`
  - `.pi/skills/scientific-ui-clarity/SKILL.md`
- Existing Docker/local workflow and `uv` preference from `AGENTS.md`.

## Steps

- [x] Define the research loop boundary: one editable experimental module or config file per run, never the whole app.
- [x] Write a `program.md`-style DoE research brief describing goals, constraints, allowed edits, forbidden edits, and logging requirements.
- [x] Choose the first metric: replay-mode improvement in weighted objective after N suggested experiments, with constraint violations counted as hard failures.
- [x] Create a fixed-budget runner concept: each candidate change gets the same replay dataset, same number of BO steps, same random seeds, and same timeout.
- [x] Define the scorecard: best observed score, average improvement, constraint violations, duplicate suggestions, runtime, and explanation quality.
- [x] Require every autonomous run to append structured evidence to JSONL logs and summarize kept/discarded changes.
- [x] Gate promotion: no autonomous change goes directly into production code; humans review the experiment log, diff, and scorecard first.
- [x] After the documentation is accepted, decide whether to build the harness under `research/` as a separate follow-up plan.

## Executed Documentation Decisions

### 1. Research loop boundary

Each autonomous research run must receive exactly one editable target. The target can be either:

- one experimental module under a future `research/` directory, or
- one isolated configuration file that controls a candidate strategy.

The agent must not edit the whole app. It must not touch production backend/frontend code during the autonomous loop unless a human later promotes a reviewed diff through a separate implementation plan. The preferred first boundary is a sandbox strategy file such as:

```text
research/strategies/bo_candidate_policy.py
```

The runner may import this strategy, but the strategy must not mutate app state, edit files, start services, or change replay data.

### 2. `program.md`-style DoE research brief

A future `research/program.md` should tell the agent:

```markdown
# DoE Autoresearch Program

Goal: improve replay-mode Bayesian Optimization suggestions for Mirai DoE using bounded, reproducible experiments.

Allowed edits:
- Edit only the assigned strategy/config file for this run.
- Add short comments explaining the experimental idea.
- Keep the public strategy interface unchanged.

Forbidden edits:
- Do not edit production backend/frontend files.
- Do not modify replay datasets or observed outputs.
- Do not relax constraints to make scores look better.
- Do not treat surrogate predictions as observed lab truth.
- Do not delete or rewrite previous JSONL logs.

Required loop:
1. State the hypothesis.
2. Modify the assigned target.
3. Run the fixed-budget replay benchmark.
4. Append structured evidence to JSONL.
5. Keep the change only if the scorecard improves without hard failures.
6. Otherwise revert or mark discarded.

Logging requirement: every run must record config, seed, dataset, metric values, violations, duplicate suggestions, runtime, diff summary, and keep/discard decision.
```

### 3. First metric

The first metric is replay-mode improvement in weighted objective after a fixed number of BO suggestions.

Definition:

- Initialize from the same observed replay rows.
- Run `N` suggestion/reveal steps, for example `N = 5`.
- At each step, reveal the hidden replay measurement for the selected candidate.
- Compute the weighted objective from observed outputs using the same objective weights.
- Primary score: `best_observed_after_N - best_observed_initial`.

Hard failures:

- any constraint violation,
- missing output,
- invalid candidate,
- duplicate suggestion where a non-duplicate candidate was available,
- using surrogate prediction as observed truth.

A hard failure makes the candidate strategy ineligible for promotion even if the numeric score improves.

### 4. Fixed-budget runner concept

Every candidate change gets the same evaluation conditions:

- same replay dataset,
- same initial observed rows,
- same hidden candidate pool,
- same objective weights,
- same constraints,
- same number of BO steps,
- same random seeds,
- same wall-clock timeout,
- same baseline strategy for comparison.

A future runner command could look like:

```bash
uv run python research/run_experiment.py \
  --strategy research/strategies/bo_candidate_policy.py \
  --dataset backend/data/replay/pem_fuel_cell_demo_replay.csv \
  --initial backend/data/replay/pem_fuel_cell_demo_initial_observed.csv \
  --steps 5 \
  --seed 2026 \
  --timeout-seconds 300 \
  --log research/logs/autoresearch.jsonl
```

The runner should fail closed: if it cannot evaluate fairly, it should mark the run failed rather than produce a partial success.

### 5. Scorecard

Each run should produce a scorecard with:

| Field | Meaning |
|---|---|
| `best_observed_score` | Best observed weighted objective after the replay budget. |
| `initial_best_score` | Best observed weighted objective before suggestions. |
| `absolute_improvement` | `best_observed_score - initial_best_score`. |
| `average_step_improvement` | Mean per-step improvement across the replay sequence. |
| `constraint_violations` | Count of hard constraint failures. Must be zero. |
| `duplicate_suggestions` | Count of repeated candidates. Lower is better. |
| `invalid_suggestions` | Count of candidates outside schema/domain. Must be zero. |
| `runtime_seconds` | End-to-end benchmark runtime. |
| `explanation_quality` | Human-scored 1–5 rating for hypothesis and rationale clarity. |
| `decision` | `kept`, `discarded`, or `needs_review`. |

Promotion requires improved primary score, zero hard failures, and a readable explanation.

### 6. Structured JSONL evidence

Every autonomous run must append one JSON object per attempt to an append-only log, for example:

```json
{"timestamp":"2026-03-01T09:00:00Z","run_id":"bo-replay-001","strategy":"bo_candidate_policy.py","seed":2026,"steps":5,"initial_best_score":0.42,"best_observed_score":0.51,"absolute_improvement":0.09,"constraint_violations":0,"duplicate_suggestions":0,"runtime_seconds":184.2,"decision":"kept","hypothesis":"Increase exploration early, then exploit after first improvement.","diff_summary":"Adjusted acquisition schedule only."}
```

The log must distinguish:

- kept changes,
- discarded changes,
- failed runs,
- inconclusive runs.

The agent must also write a short human-readable summary of what was kept or discarded, but the JSONL file is the durable evidence source.

### 7. Human promotion gate

Autonomous results are research evidence, not production changes. No autonomous change should go directly into production code.

Promotion process:

1. Human reviews the JSONL evidence.
2. Human reviews the code diff for the experimental target.
3. Human reviews the scorecard and hard-failure fields.
4. Human decides whether the idea deserves a normal product implementation plan.
5. Only then may a separate approved plan touch backend/frontend code.

This preserves the scientist-facing trust model: agents can explore candidate ideas, but humans decide what enters the product.

### 8. Follow-up decision

Decision: do not build the harness in this step. This plan remains documentation-only. If accepted, create a separate follow-up plan for a `research/` harness with explicit files, commands, fixtures, and acceptance checks.

## Verification

For this documentation-only plan:

- Confirm this file exists at `docs/agent-plans/implemented/autoresearch-for-doe-plan.md`.
- Review that it maps `autoresearch` concepts to Mirai DoE without proposing uncontrolled self-modifying product code.
- Confirm no backend/frontend implementation files were changed.

For a future harness implementation:

- Run a smoke replay experiment locally with a fixed seed.
- Confirm JSONL logs include config, diff summary, metrics, and keep/discard decision.
- Compare at least one baseline BO strategy against one agent-proposed variant using the same replay budget.
- Confirm constraints are never violated silently.

## Non-goals

- Do not copy `autoresearch`'s LLM training code into this repo.
- Do not let agents freely edit arbitrary backend/frontend files.
- Do not treat surrogate predictions as lab truth.
- Do not replace scientist review of recommended experiments.

## Expected value for DoE

An `autoresearch`-style loop could help Mirai DoE by turning vague optimizer improvement work into repeatable research cycles: propose a bounded change, run the same replay benchmark, measure whether recommendations improved, keep evidence, and let humans decide whether the change deserves productization.
