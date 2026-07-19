import assert from 'node:assert/strict'
import test from 'node:test'
import { DESIGN_STUDIO_TABS, designResultPresentation, designResultState, isChampionReady, nextDesignStudioView, schemaBoundsSummary } from '../src/lib/designStudioPresentation.ts'

test('Design Studio uses the shared five-stage navigation order', () => {
  assert.deepEqual(DESIGN_STUDIO_TABS.map((tab) => tab.id), ['single_result', 'plot', 'optimize', 'compare', 'model_map'])
  assert.equal(nextDesignStudioView('single_result', 'ArrowLeft'), 'model_map')
  assert.equal(nextDesignStudioView('model_map', 'ArrowRight'), 'single_result')
  assert.equal(nextDesignStudioView('optimize', 'Home'), 'single_result')
  assert.equal(nextDesignStudioView('plot', 'End'), 'model_map')
})

test('single-result freshness states prioritize loading and errors before stale data', () => {
  assert.equal(designResultState({ loading: true, error: true, stale: true, hasPrediction: true }), 'loading')
  assert.equal(designResultState({ loading: false, error: true, stale: true, hasPrediction: true }), 'error')
  assert.equal(designResultState({ loading: false, error: false, stale: true, hasPrediction: true }), 'stale')
  assert.equal(designResultState({ loading: false, error: false, stale: false, hasPrediction: true }), 'current')
  assert.equal(designResultState({ loading: false, error: false, stale: false, hasPrediction: false }), 'empty')
  assert.equal(designResultPresentation.current.label, 'Estimate current')
})

test('schema bounds metadata is concise and pluralized', () => {
  assert.equal(schemaBoundsSummary(1), '1 bounded input')
  assert.equal(schemaBoundsSummary(8), '8 bounded inputs')
})

test('workspace readiness requires the actually loaded champion source', () => {
  assert.equal(isChampionReady('loaded_champion'), true)
  assert.equal(isChampionReady('candidate_review'), false)
  assert.equal(isChampionReady('champion_not_loaded'), false)
  assert.equal(isChampionReady('packaged artifact'), false)
  assert.equal(isChampionReady(undefined), false)
})
