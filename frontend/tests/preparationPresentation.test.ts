import assert from 'node:assert/strict'
import test from 'node:test'
import {
  artifactDisplayName,
  derivePreparationViewModel,
  nextPreparationTab,
  preparationStatusLabel,
  suggestedPreparationQuestions,
  type PreparationFacts,
} from '../src/lib/preparationPresentation.ts'

const base: PreparationFacts = {
  hasSchema: true,
  hasSession: true,
  metadataApproved: false,
  preprocessingStatus: 'not_started',
  preprocessingComplete: false,
  preprocessingApproved: false,
  mlPreprocessingStatus: 'not_started',
  mlPreprocessingStarted: false,
  mlPreprocessingReady: false,
  hasTrainingRequest: false,
  trainingStatus: '',
  trainingCompleted: false,
  candidateReady: false,
  championActive: false,
}

test('unknown backend statuses fall back to readable copy', () => {
  assert.equal(preparationStatusLabel('new_backend-state'), 'New backend state')
})

test('sub-tab keyboard navigation wraps and supports Home and End', () => {
  assert.equal(nextPreparationTab('overview', 'ArrowLeft'), 'ask-mirai')
  assert.equal(nextPreparationTab('ask-mirai', 'ArrowRight'), 'overview')
  assert.equal(nextPreparationTab('preprocessing', 'Home'), 'overview')
  assert.equal(nextPreparationTab('variables', 'End'), 'ask-mirai')
})

test('artifact filenames receive professional display names', () => {
  assert.equal(artifactDisplayName('runs/current/model_table_preprocessed.csv'), 'Training-ready dataset')
  assert.equal(artifactDisplayName('custom_evidence.json'), 'Custom evidence')
})

test('incomplete metadata routes the user to Variables', () => {
  const model = derivePreparationViewModel(base)
  assert.equal(model.action.kind, 'review_variables')
  assert.equal(model.action.destination, 'variables')
  assert.equal(model.blocker, 'Variable metadata has not been approved.')
})

test('canonical preprocessing failure is presented as an error', () => {
  const model = derivePreparationViewModel({ ...base, metadataApproved: true, preprocessingStatus: 'failed_validation' })
  assert.equal(model.tone, 'error')
  assert.equal(model.action.destination, 'preprocessing')
})

test('approved canonical data selects preprocessing-plan drafting', () => {
  const model = derivePreparationViewModel({
    ...base,
    metadataApproved: true,
    preprocessingStatus: 'approved_for_training',
    preprocessingComplete: true,
    preprocessingApproved: true,
  })
  assert.equal(model.action.kind, 'draft_ml_plan')
  assert.equal(model.action.label, 'Draft preprocessing plan')
})

test('training-ready data selects a versioned training request', () => {
  const model = derivePreparationViewModel({
    ...base,
    metadataApproved: true,
    preprocessingComplete: true,
    preprocessingApproved: true,
    mlPreprocessingStatus: 'ml_preprocessing_ready_for_training',
    mlPreprocessingStarted: true,
    mlPreprocessingReady: true,
  })
  assert.equal(model.action.kind, 'create_training_request')
  assert.equal(model.action.destination, 'training')
})

test('active champion selects model-quality review', () => {
  const model = derivePreparationViewModel({
    ...base,
    metadataApproved: true,
    preprocessingComplete: true,
    preprocessingApproved: true,
    mlPreprocessingStarted: true,
    mlPreprocessingReady: true,
    hasTrainingRequest: true,
    trainingStatus: 'approved_champion_active',
    trainingCompleted: true,
    championActive: true,
  })
  assert.equal(model.displayStatus, 'Ready for model review')
  assert.equal(model.action.kind, 'open_model_quality')
})

test('Ask Mirai suggestions reflect available lifecycle evidence', () => {
  const questions = suggestedPreparationQuestions({
    ...base,
    metadataApproved: true,
    preprocessingComplete: true,
    preprocessingApproved: true,
    mlPreprocessingStarted: true,
    mlPreprocessingReady: true,
    hasTrainingRequest: true,
  })
  assert.ok(questions.includes('Compare the validated and training-ready datasets.'))
  assert.ok(questions.includes('Explain the managed and local training paths for this project.'))
  assert.ok(questions.length <= 4)
})
