import assert from 'node:assert/strict'
import test from 'node:test'
import type { ProjectSchema } from '../src/lib/api.ts'
import { artifactDisplayName, buildOutputTrustData, classifyOutputTrust, diagnosticPoints, filterDiagnosticRows, formatR2, friendlyModelName, friendlyStatus, nextModelQualityView, splitMean, splitPresentation } from '../src/lib/modelQualityPresentation.ts'

const schema: ProjectSchema = {
  project_id: 'quality-test',
  display_name: 'A very long project name used to verify model-quality presentation behavior',
  inputs: [],
  outputs: [
    { name: 'strong_output', label: 'Strong output', direction: 'maximize', unit: 'A' },
    { name: 'weak_output', label: 'Weak output', direction: 'minimize', unit: '%' },
  ],
}

const bestModel = {
  selection_metric: 0.20594696460321135,
  splits: {
    validation: {
      strong_output: { r2: 0.81, mae: 1.2, normalized_rmse: 0.12, n: 24 },
      weak_output: { r2: -0.7151658542490607, mae: 4.3, normalized_rmse: 0.41, n: 24 },
    },
    test: {
      strong_output: { r2: 0.79, mae: 1.4, mae_percent_of_split_mean: 12, baseline_improvement_mae_percent: 35, n: 20 },
      weak_output: { r2: -0.321, mae: 4.8, mae_percent_of_split_mean: 46, baseline_improvement_mae_percent: -8, n: 20 },
    },
  },
}

test('output trust keeps strong and negative-R² results visible', () => {
  const outputs = buildOutputTrustData(schema, bestModel)
  assert.equal(outputs[0].level, 'strong')
  assert.equal(outputs[1].level, 'weak')
  assert.equal(outputs[1].test.r2, -0.321)
  assert.equal(formatR2(outputs[1].test.r2 as number), '-0.321')
})

test('trust thresholds retain existing semantics', () => {
  assert.equal(classifyOutputTrust({ r2: 0.8, mae_percent_of_split_mean: 18 }).level, 'strong')
  assert.equal(classifyOutputTrust({ r2: 0.6, mae_percent_of_split_mean: 28 }).level, 'usable')
  assert.equal(classifyOutputTrust({ r2: 0.01, mae_percent_of_split_mean: 20 }).level, 'weak')
  assert.equal(classifyOutputTrust({}).level, 'needs_review')
})

test('candidate split metrics are read without recalculation changes', () => {
  assert.equal(splitMean(bestModel, 'validation', 'r2'), (0.81 - 0.7151658542490607) / 2)
  assert.equal(bestModel.selection_metric, 0.20594696460321135)
})

test('technical status and artifact mappings remain safe for unknown values', () => {
  assert.equal(friendlyStatus('loaded_champion'), 'Champion loaded')
  assert.equal(friendlyStatus('future_backend_state'), 'Future Backend State')
  assert.equal(friendlyModelName('mean_baseline'), 'Mean baseline')
  assert.equal(friendlyModelName('ridge_alpha_0.01'), 'Ridge Alpha 0.01')
  assert.equal(artifactDisplayName('/runs/123/metrics_summary.json'), 'Model metrics summary')
})

test('Model Quality tabs share keyboard navigation semantics with Preparation', () => {
  assert.equal(nextModelQualityView('overview', 'ArrowLeft'), 'artifacts')
  assert.equal(nextModelQualityView('artifacts', 'ArrowRight'), 'overview')
  assert.equal(nextModelQualityView('outputs', 'Home'), 'overview')
  assert.equal(nextModelQualityView('diagnostics', 'End'), 'artifacts')
})

test('split colors and purposes are centralized and distinct', () => {
  assert.equal(splitPresentation.validation.label, 'Validation')
  assert.equal(splitPresentation.test.label, 'Test')
  assert.notEqual(splitPresentation.validation.color, splitPresentation.test.color)
  assert.match(splitPresentation.test.purpose, /Untouched/)
})

test('diagnostic filtering preserves measured, predicted, and residual values exactly', () => {
  const rows = [
    { model_name: 'mlp', split: 'validation', output_true: 1.25, output_pred: 1.1, output_residual: 0.15 },
    { model_name: 'mlp', split: 'test', output_true: -2, output_pred: -1.5, output_residual: -0.5 },
    { model_name: 'ridge', split: 'test', output_true: 8, output_pred: 9, output_residual: -1 },
  ]
  const filtered = filterDiagnosticRows(rows, 'mlp', 'validation,test')
  assert.equal(filtered.length, 2)
  assert.deepEqual(diagnosticPoints(filtered, 'output').map(({ measured, predicted, residual }) => ({ measured, predicted, residual })), [
    { measured: 1.25, predicted: 1.1, residual: 0.15 },
    { measured: -2, predicted: -1.5, residual: -0.5 },
  ])
})
