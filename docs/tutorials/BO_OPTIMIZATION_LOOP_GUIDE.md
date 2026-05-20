# Optimization Loop Guide

This guide explains the new Bayesian Optimization workflow in the Mirai DoE Engine UI: what each control does, what data is used, and the intended end-to-end flow.

## Two Modes

### Batch Explorer

The existing LHS workflow lives here.

Use it to:

- Sample many candidate configurations at once.
- Score them with the ONNX MLP surrogate.
- Compare ranked candidates in the table and visualizations.
- Explore the design space before starting a sequential loop.

Important: Batch Explorer predictions are surrogate predictions only. They are not lab results.

### Optimization Loop

The new BO workflow lives here.

Use it to:

- Start from observed historical experiments.
- Fit a BO model on observed results.
- Suggest the next experiment using uncertainty and acquisition scoring.
- Let a scientist accept, reject, skip, or constrain the search.
- Reveal a hidden historical measurement in replay mode.

Important: replay mode does not treat `MLP(X)` as truth. When a result is revealed, it comes from the hidden replay CSV dataset.

## Optimization Loop Controls

### Objective Weights

These define the scalar objective the BO loop optimizes.

Examples:

- Positive weight for KPIs you want to maximize.
- Negative weight for KPIs you want to minimize.
- Larger magnitude means the KPI matters more.

The BO model fits against observed weighted objective scores. The same weights are also used to show predicted and observed scores in the history.

### Exploration Mode

Controls how aggressively the optimizer searches uncertain regions.

- `Conservative`: favors areas near known good observed experiments.
- `Balanced`: mixes exploitation and exploration.
- `Exploratory`: gives more value to uncertain regions.

This affects acquisition parameters such as expected improvement tolerance or UCB uncertainty weight.

### Acquisition

Controls how the next candidate is selected from the candidate pool.

- `Expected Improvement`: prefers candidates likely to improve over the current best observed score.
- `Upper Confidence Bound`: prefers candidates with high predicted BO mean plus uncertainty.

### Initialize Replay

Seeds the BO experiment log with initial observed experiments.

What it does:

- Loads rows from `train rows from the active training split artifact`.
- Writes them to the project experiment log.
- Marks them as `initial_observed` and `observed`.
- Stores their real measured KPI outputs.

Use this before clicking `Suggest Next`.

### Reset Loop

Clears the current project BO log and initializes replay again.

Use this when:

- You want to restart the demo.
- You want to remove previous suggestions/revealed results.
- You changed the flow and want a clean history.

### Save BO Config

Saves the current BO settings for future suggestions.

It saves:

- Objective weights.
- Exploration mode.
- Acquisition function.
- BO-only input constraints.
- Replay mode setting.

Use this after changing constraints or optimizer settings if you want future suggestions to respect them.

### Suggest Next

Runs the BO suggestion step.

What it does:

- Reads observed experiments from the log.
- Builds weighted objective scores from observed outputs.
- Fits the BO Gaussian process model.
- Samples a candidate pool under the active BO constraints.
- Scores candidates with the selected acquisition function.
- Selects the best next candidate.
- Calls the ONNX MLP only to show predicted KPI values for context.
- Logs the suggestion with status `suggested`.

It does not reveal observed outputs.

## Next Suggested Experiment Card

This card shows the active candidate from the BO loop.

### Suggested Inputs

The actual continuous candidate selected by BO.

### Predicted KPIs

Surrogate model predictions from the ONNX MLP.

These are displayed for scientist context only. They are not treated as lab results.

### Expected Improvement

How much improvement the acquisition model expects over the current best observed score.

### Uncertainty

The BO model's estimated uncertainty for the scalar objective at the suggested candidate.

### Acquisition

The final acquisition score used to rank the candidate.

### Replay Distance

After reveal, this shows how far the suggested continuous BO candidate was from the nearest hidden historical experiment in normalized input space.

## Review Buttons

### Accept

Marks a suggestion as accepted.

What it means:

- The scientist agrees this candidate is worth testing.
- The suggestion can now reveal a replay result.

It still does not reveal the hidden measurement by itself.

### Reject

Opens a review dialog where the scientist can choose a reason and optional notes.

Common reasons:

- Infeasible.
- Unsafe.
- Too expensive.
- Outside protocol.
- Chemically implausible.
- Duplicate.
- Other.

What it does:

- Marks the suggestion as `rejected`.
- Saves the review reason and notes.
- Prevents replay reveal for that suggestion.

### Skip

Marks the suggestion as skipped without a rejection reason.

Use it when:

- The suggestion is not useful right now.
- You want to move on without recording a strong negative review.

Skipped suggestions do not reveal hidden replay measurements.

### Reveal Replay Result

Reveals the replay measurement for an accepted suggestion.

What it does:

- Finds the nearest unused hidden experiment from `train+validation rows from the active training split artifact, excluding already-used replay IDs`.
- Copies that row's real measured KPI outputs into the experiment log.
- Marks the experiment as `observed`.
- Stores replay metadata:
  - matched replay row ID.
  - matched historical inputs.
  - replay distance.
  - prediction error between MLP prediction and observed replay result.

This is the key scientific honesty step: observed outputs come from hidden replay data, not from the MLP.

## Current Best Card

Shows the best observed experiment so far.

Only experiments with real observed outputs count:

- Initial observed replay rows.
- Accepted suggestions with revealed replay results.

Suggested-only, rejected, and skipped candidates do not count.

## Expert Constraints

These constraints apply only to the Optimization Loop.

They do not change the Batch Explorer.

For each input, you can set:

- Active minimum.
- Active maximum.
- Fixed value.

After changing constraints, click `Save BO Config`.

Future BO suggestions will sample candidates inside the active constraints.

## Charts

### Objective Over Iterations

Shows:

- Observed score.
- Predicted score.
- Current best observed score.

Use it to see whether the loop is improving over time.

### Uncertainty and Expected Improvement

Shows:

- Acquisition score.
- Expected improvement.
- Objective uncertainty.

Use it to explain the exploration-vs-exploitation behavior.

### Predicted vs Observed KPIs

Compares the MLP prediction against the revealed replay measurement.

Use it to show where the surrogate is accurate or wrong.

## Experiment History

The history table is backed by a persistent JSONL log.

Each row tracks:

- Iteration.
- Status.
- Source.
- Suggested inputs.
- Predicted score.
- Observed score.
- Uncertainty.
- Scientist decision.

The default log path is:

```text
backend/data/experiment_logs/{project_id}.jsonl
```

In Docker this lives inside the backend container unless a volume is added later.

## Recommended Demo Flow

1. Open `Batch Explorer`.
2. Run a candidate recommendation.
3. Show the ranked table and visualizations.
4. Explain that Batch Explorer scans many possible configurations with the MLP surrogate.
5. Switch to `Optimization Loop`.
6. Click `Initialize Replay`.
7. Show the initial observed count and current best observed experiment.
8. Click `Suggest Next`.
9. Show suggested inputs, predicted KPIs, uncertainty, and expected improvement.
10. Click `Accept`.
11. Click `Reveal Replay Result`.
12. Show observed KPIs, prediction error, and replay distance.
13. Click `Suggest Next` again to continue the loop.
14. Reject one suggestion and provide a reason.
15. Narrow one or more expert constraints.
16. Click `Save BO Config`.
17. Click `Suggest Next` and show that the next candidate respects the constraints.

## Status Meanings

- `observed`: experiment has real observed outputs in the log.
- `suggested`: BO proposed the experiment but it has not been reviewed.
- `accepted`: scientist accepted it; replay result can be revealed.
- `rejected`: scientist rejected it; replay result cannot be revealed.
- `skipped`: scientist skipped it; replay result cannot be revealed.

## Source Meanings

- `initial_observed`: seeded from initial replay data.
- `bo_suggested`: proposed by the BO loop.
- `replay_revealed`: accepted BO suggestion with hidden replay output revealed.
- `manual_observed`: reserved for future manually entered lab results.

## Main Product Message

The feature demonstrates this closed loop:

```text
historical observed experiments
→ uncertainty-aware BO suggestion
→ scientist review and constraints
→ hidden replay measurement revealed
→ experiment log updated
→ next BO suggestion
```

The system helps scientists choose better next experiments faster. It does not execute AI suggestions blindly, and it does not pretend surrogate predictions are lab results.
