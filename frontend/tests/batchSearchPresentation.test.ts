import assert from 'node:assert/strict'
import test from 'node:test'
import type { ProjectSchema } from '../src/lib/api.ts'
import { buildBatchSearchRequest, buildHeatmapRequestRows, fixedInputSummary, heatmapRequestFingerprint, isRecommendationRunStale, nextBatchSearchView, objectiveRows, recommendationRunSummary } from '../src/lib/batchSearchPresentation.ts'
import { normalizeForComparison } from '../src/lib/doeUtils.ts'

const schema: ProjectSchema = {
  project_id: 'batch-test',
  display_name: 'Batch test',
  inputs: [
    { name: 'x', label: 'Long material formulation variable', unit: '%', min: -2, max: 2 },
    { name: 'y', label: 'Operating condition', unit: 'V', min: 10, max: 20 },
    { name: 'fixed', label: 'Fixed condition', unit: '°C', min: 30, max: 50 },
  ],
  outputs: [
    { name: 'gain', label: 'Gain', unit: 'A', direction: 'maximize' },
    { name: 'loss', label: 'Loss', unit: '%', direction: 'minimize' },
  ],
}

test('recommendation payload preserves signed weights, enabled fixed values, and exact caps', () => {
  const result = buildBatchSearchRequest({
    objectiveWeights: { gain: '0.4', loss: '-0.2', ignored: '0' },
    fixedInputs: { x: { enabled: false, value: '1.5' }, y: { enabled: true, value: '12.5' } },
    nCandidates: '2000',
    tableTopK: '5',
    visualizationTopK: '75',
  })
  assert.deepEqual(result.request, { objective_weights: { gain: 0.4, loss: -0.2, ignored: 0 }, fixed_inputs: { y: 12.5 }, n_candidates: 2000, top_k: 75 })
  assert.deepEqual(result.run, { nCandidates: 2000, tableTopK: 5, visualizationTopK: 75, requestedTopK: 75, objectiveWeights: { gain: 0.4, loss: -0.2, ignored: 0 }, fixedInputs: { y: 12.5 } })
})

test('candidate, table, and visualization clamps retain current behavior', () => {
  const capped = buildBatchSearchRequest({ objectiveWeights: {}, fixedInputs: {}, nCandidates: '200000', tableTopK: '99', visualizationTopK: '999' })
  assert.equal(capped.run.nCandidates, 100000)
  assert.equal(capped.run.tableTopK, 25)
  assert.equal(capped.run.visualizationTopK, 100)
  assert.equal(capped.request.top_k, 100)

  const small = buildBatchSearchRequest({ objectiveWeights: {}, fixedInputs: {}, nCandidates: '3', tableTopK: '5', visualizationTopK: '75' })
  assert.equal(small.request.top_k, 3)
})

test('objective and search-space summaries are presentation-only', () => {
  assert.deepEqual(objectiveRows(schema, { gain: '0.4', loss: '-0.2' }).map(({ value, included, influence }) => ({ value, included, influence })), [
    { value: 0.4, included: true, influence: 'Reward larger predictions' },
    { value: -0.2, included: true, influence: 'Reward smaller predictions' },
  ])
  assert.equal(objectiveRows(schema, { gain: '0', loss: '0' })[0].included, false)
  assert.deepEqual(fixedInputSummary(schema, { x: { enabled: true, value: '0' }, y: { enabled: false, value: '15' }, fixed: { enabled: true, value: '40' } }), { fixed: 2, sampled: 1, label: '2 fixed conditions · 1 variable sampled' })
})

test('heatmap request keeps y-major row order, full schema bounds, and reference fixed inputs', () => {
  const grid = buildHeatmapRequestRows(schema, 'x', 'y', '8', { x: '0', y: '15', fixed: '42' })
  assert.ok(grid)
  assert.equal(grid.rows.length, 64)
  assert.deepEqual(grid.rows[0], { x: -2, y: 10, fixed: 42 })
  assert.deepEqual(grid.rows[7], { x: 2, y: 10, fixed: 42 })
  assert.deepEqual(grid.rows[8], { x: -2, y: 10 + 10 / 7, fixed: 42 })
  assert.deepEqual(grid.rows[63], { x: 2, y: 20, fixed: 42 })
  assert.equal(buildHeatmapRequestRows(schema, 'x', 'x', '24', {}), null)
})

test('heatmap freshness changes for setup, reference values, or objective weights', () => {
  const base = { xAxis: 'x', yAxis: 'y', colorMetric: 'score', gridSize: '24', inputValues: { fixed: '40' }, objectiveWeights: { gain: 0.4 } }
  const fingerprint = heatmapRequestFingerprint(base)
  assert.notEqual(fingerprint, heatmapRequestFingerprint({ ...base, inputValues: { fixed: '41' } }))
  assert.notEqual(fingerprint, heatmapRequestFingerprint({ ...base, objectiveWeights: { gain: 0.5 } }))
  assert.notEqual(fingerprint, heatmapRequestFingerprint({ ...base, colorMetric: 'gain' }))
})

test('result summary uses actual returned candidates without changing rank order', () => {
  const recommendations = [{ inputs: { x: 1 }, predictions: { gain: 5 }, score: 0.4 }, { inputs: { x: 0 }, predictions: { gain: 4 }, score: -0.1 }]
  const summary = recommendationRunSummary({ projectId: 'batch-test', projectDisplayName: 'Batch test', nCandidates: 2000, tableTopK: 5, visualizationTopK: 75, requestedTopK: 75, objectiveWeights: { gain: 1 }, fixedInputs: {}, recommendations })
  assert.deepEqual(summary, { sampled: 2000, returned: 2, shortlist: 2, visualized: 2, bestScore: 0.4 })
  assert.equal(recommendations[0].score, 0.4)
})

test('existing results become stale only when request-shaping configuration changes', () => {
  const current = buildBatchSearchRequest({ objectiveWeights: { gain: '1' }, fixedInputs: {}, nCandidates: '2000', tableTopK: '5', visualizationTopK: '75' }).run
  const run = { projectId: 'batch-test', projectDisplayName: 'Batch test', ...current, recommendations: [{ inputs: {}, predictions: {}, score: 1 }] }
  assert.equal(isRecommendationRunStale(run, current), false)
  assert.equal(isRecommendationRunStale(run, { ...current, nCandidates: 2001 }), true)
  assert.equal(isRecommendationRunStale(run, { ...current, objectiveWeights: { gain: -1 } }), true)
  assert.equal(isRecommendationRunStale(run, { ...current, fixedInputs: { x: 0 } }), true)
})

test('minimize comparison remains reversed with a zero-to-one baseline', () => {
  assert.deepEqual(normalizeForComparison([-2, 0, 2], 'maximize'), [0, 0.5, 1])
  assert.deepEqual(normalizeForComparison([-2, 0, 2], 'minimize'), [1, 0.5, 0])
})

test('Batch Search tabs wrap and support Home and End', () => {
  assert.equal(nextBatchSearchView('configure', 'ArrowLeft'), 'visuals')
  assert.equal(nextBatchSearchView('visuals', 'ArrowRight'), 'configure')
  assert.equal(nextBatchSearchView('results', 'Home'), 'configure')
  assert.equal(nextBatchSearchView('configure', 'End'), 'visuals')
})
