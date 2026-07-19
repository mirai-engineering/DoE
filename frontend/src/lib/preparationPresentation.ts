export type PreparationTab = 'overview' | 'variables' | 'preprocessing' | 'training' | 'ask-mirai'
export type PreparationTone = 'neutral' | 'active' | 'success' | 'warning' | 'error'

export type PreparationActionKind =
  | 'select_session'
  | 'review_variables'
  | 'run_preprocessing'
  | 'review_preprocessing'
  | 'draft_ml_plan'
  | 'review_ml_plan'
  | 'create_training_request'
  | 'start_training'
  | 'load_champion'
  | 'open_model_quality'

export type PreparationFacts = {
  hasSchema: boolean
  hasSession: boolean
  metadataApproved: boolean
  preprocessingStatus: string
  preprocessingComplete: boolean
  preprocessingApproved: boolean
  mlPreprocessingStatus: string
  mlPreprocessingStarted: boolean
  mlPreprocessingReady: boolean
  hasTrainingRequest: boolean
  trainingStatus: string
  trainingCompleted: boolean
  candidateReady: boolean
  championActive: boolean
}

export type PreparationViewModel = {
  displayStatus: string
  explanation: string
  tone: PreparationTone
  blocker: string | null
  action: {
    kind: PreparationActionKind
    label: string
    destination: PreparationTab
    enabled: boolean
  }
}

const STATUS_LABELS: Record<string, string> = {
  approved: 'Approved',
  approved_for_training: 'Approved for training',
  approved_champion_active: 'Champion model active',
  available: 'Available',
  candidate_ready_for_review: 'Candidate ready for review',
  completed: 'Complete',
  contract_loaded_needs_admin_approval: 'Contract ready for review',
  draft: 'Draft',
  eda_complete_needs_mirai_admin_review: 'Analysis ready for review',
  failed: 'Failed',
  failed_retryable_artifact_upload: 'Artifact upload needs retry',
  failed_validation: 'Validation failed',
  inferred_needs_admin_approval: 'Metadata needs review',
  locked: 'Locked',
  ml_preprocessing_contract_defined: 'Preprocessing contract defined',
  ml_preprocessing_not_ready: 'Preprocessing plan blocked',
  ml_preprocessing_plan_approved: 'Preprocessing plan approved',
  ml_preprocessing_ready_for_training: 'Training-ready dataset complete',
  needs_admin_approval: 'Needs approval',
  not_started: 'Not started',
  preprocessing_complete_needs_approval: 'Dataset analysis needs approval',
  preprocessing_plan_needs_approval: 'Preprocessing plan needs approval',
  preprocessing_plan_needs_input: 'Preprocessing plan needs input',
  queued: 'Queued',
  running: 'In progress',
  staged_for_mirai_execution: 'Training request ready',
  waiting: 'Waiting for prerequisite',
}

const ARTIFACT_LABELS: Record<string, string> = {
  'model_table.csv': 'Validated dataset',
  'model_table_preprocessed.csv': 'Training-ready dataset',
  'ml_preprocessing_report.md': 'Preprocessing report',
  'preprocessing_fitted.json': 'Fitted preprocessing parameters',
  'feature_map.json': 'Feature map',
  'target_map.json': 'Target map',
  'model_table_preprocessed_manifest.json': 'Training-ready dataset manifest',
  'training_manifest.json': 'Training package manifest',
}

export function preparationStatusLabel(value?: string | null): string {
  const normalized = String(value ?? '').trim()
  if (!normalized) return 'Not started'
  const known = STATUS_LABELS[normalized.toLowerCase()]
  if (known) return known
  const readable = normalized.replace(/[_-]+/g, ' ').replace(/\s+/g, ' ').trim()
  return readable ? readable.charAt(0).toUpperCase() + readable.slice(1) : 'Not started'
}

export function preparationStatusTone(value?: string | null): PreparationTone {
  const status = String(value ?? '').toLowerCase()
  if (status.includes('fail') || status.includes('error')) return 'error'
  if (status.includes('needs_input') || status.includes('blocked') || status.includes('retry')) return 'warning'
  if (status.includes('approved') || status.includes('complete') || status.includes('ready_for_training') || status.includes('active')) return 'success'
  if (status.includes('running') || status.includes('queued') || status.includes('ready') || status.includes('available')) return 'active'
  return 'neutral'
}

export function artifactDisplayName(filename: string): string {
  const basename = filename.split('/').pop() ?? filename
  return ARTIFACT_LABELS[basename] ?? preparationStatusLabel(basename.replace(/\.[^.]+$/, ''))
}

export function derivePreparationViewModel(facts: PreparationFacts): PreparationViewModel {
  const preprocessingFailed = facts.preprocessingStatus.includes('failed')
  const mlFailed = facts.mlPreprocessingStatus.includes('needs_input') || facts.mlPreprocessingStatus.includes('not_ready')
  const trainingFailed = facts.trainingStatus.includes('failed')

  if (!facts.hasSession) {
    if (facts.hasSchema) {
      return {
        displayStatus: 'Preparation session unavailable',
        explanation: 'This deployment has no local preparation session, but an already-promoted MLflow champion can still be loaded for the project.',
        tone: 'warning',
        blocker: 'Dataset preparation details are unavailable in this deployment.',
        action: { kind: 'load_champion', label: 'Load promoted champion', destination: 'training', enabled: true },
      }
    }
    return {
      displayStatus: 'Preparation session required',
      explanation: 'Select a dataset session to review its variables, evidence, and preparation decisions.',
      tone: 'warning',
      blocker: 'No dataset session is selected.',
      action: { kind: 'select_session', label: 'Select a session', destination: 'overview', enabled: false },
    }
  }
  if (!facts.metadataApproved) {
    return {
      displayStatus: 'Variable review required',
      explanation: 'Review variable roles, labels, and units before preprocessing begins.',
      tone: 'warning',
      blocker: 'Variable metadata has not been approved.',
      action: { kind: 'review_variables', label: 'Review variables', destination: 'variables', enabled: true },
    }
  }
  if (preprocessingFailed) {
    return {
      displayStatus: preparationStatusLabel(facts.preprocessingStatus),
      explanation: 'The dataset could not complete canonical preprocessing. Review validation details before retrying.',
      tone: 'error',
      blocker: 'Canonical preprocessing requires attention.',
      action: { kind: 'run_preprocessing', label: 'Review preprocessing', destination: 'preprocessing', enabled: true },
    }
  }
  if (!facts.preprocessingComplete) {
    const active = ['queued', 'running'].includes(facts.preprocessingStatus)
    return {
      displayStatus: active ? preparationStatusLabel(facts.preprocessingStatus) : 'Ready for dataset preparation',
      explanation: active ? 'Mirai is creating the validated dataset and analysis artifacts.' : 'Variable metadata is approved. The dataset can now be validated and prepared.',
      tone: active ? 'active' : 'neutral',
      blocker: active ? 'Dataset preparation is still running.' : null,
      action: { kind: 'run_preprocessing', label: active ? 'View progress' : 'Run preprocessing', destination: 'preprocessing', enabled: !active },
    }
  }
  if (!facts.preprocessingApproved) {
    return {
      displayStatus: 'Dataset analysis ready for review',
      explanation: 'Review usable and rejected rows, split safeguards, and analysis evidence before approval.',
      tone: 'warning',
      blocker: 'Canonical preprocessing has not been approved for training.',
      action: { kind: 'review_preprocessing', label: 'Review preprocessing results', destination: 'preprocessing', enabled: true },
    }
  }
  if (!facts.mlPreprocessingStarted) {
    return {
      displayStatus: 'Preprocessing plan required',
      explanation: 'The validated dataset is approved. Mirai can now recommend reproducible model-preparation steps.',
      tone: 'active',
      blocker: null,
      action: { kind: 'draft_ml_plan', label: 'Draft preprocessing plan', destination: 'preprocessing', enabled: true },
    }
  }
  if (!facts.mlPreprocessingReady) {
    return {
      displayStatus: preparationStatusLabel(facts.mlPreprocessingStatus),
      explanation: mlFailed ? 'The proposed plan needs attention before it can produce a training-ready dataset.' : 'Review the proposed steps and safeguards before applying the plan.',
      tone: mlFailed ? 'warning' : 'active',
      blocker: mlFailed ? 'The preprocessing plan has unresolved requirements.' : 'The preprocessing plan has not been applied.',
      action: { kind: 'review_ml_plan', label: 'Review preprocessing plan', destination: 'preprocessing', enabled: true },
    }
  }
  if (!facts.hasTrainingRequest) {
    return {
      displayStatus: 'Ready to create training request',
      explanation: 'The approved, training-ready dataset can now be locked into a versioned training request.',
      tone: 'success',
      blocker: null,
      action: { kind: 'create_training_request', label: 'Create training request', destination: 'training', enabled: true },
    }
  }
  if (trainingFailed) {
    return {
      displayStatus: preparationStatusLabel(facts.trainingStatus),
      explanation: 'The current training run needs attention. The versioned request and package remain available.',
      tone: 'error',
      blocker: 'Training did not complete successfully.',
      action: { kind: 'start_training', label: 'Review training status', destination: 'training', enabled: true },
    }
  }
  if (!facts.trainingCompleted) {
    return {
      displayStatus: preparationStatusLabel(facts.trainingStatus || 'staged_for_mirai_execution'),
      explanation: 'Choose managed training or download the same approved package for local/on-premises training.',
      tone: facts.trainingStatus === 'running' ? 'active' : 'neutral',
      blocker: facts.trainingStatus === 'running' ? 'Managed training is still running.' : null,
      action: { kind: 'start_training', label: facts.trainingStatus === 'running' ? 'View training progress' : 'Choose training path', destination: 'training', enabled: true },
    }
  }
  if (!facts.championActive) {
    return {
      displayStatus: facts.candidateReady ? 'Model candidate ready' : 'Training complete',
      explanation: 'Review the trained candidate, promote the intended version in MLflow, then load the champion into Mirai.',
      tone: 'success',
      blocker: 'A promoted champion has not been activated in Mirai.',
      action: { kind: 'load_champion', label: 'Load promoted champion', destination: 'training', enabled: true },
    }
  }
  return {
    displayStatus: 'Ready for model review',
    explanation: 'The approved champion is active and the project is ready for model-quality review.',
    tone: 'success',
    blocker: null,
    action: { kind: 'open_model_quality', label: 'Open model quality', destination: 'training', enabled: true },
  }
}

export function nextPreparationTab(current: PreparationTab, key: 'ArrowLeft' | 'ArrowRight' | 'Home' | 'End'): PreparationTab {
  const tabs: PreparationTab[] = ['overview', 'variables', 'preprocessing', 'training', 'ask-mirai']
  const index = Math.max(0, tabs.indexOf(current))
  if (key === 'Home') return tabs[0]
  if (key === 'End') return tabs[tabs.length - 1]
  if (key === 'ArrowLeft') return tabs[(index - 1 + tabs.length) % tabs.length]
  return tabs[(index + 1) % tabs.length]
}

export function suggestedPreparationQuestions(facts: PreparationFacts, variableLabels: string[] = []): string[] {
  const suggestions: string[] = []
  if (!facts.metadataApproved) {
    suggestions.push('Which variables need my attention before preprocessing?')
    if (variableLabels[0]) suggestions.push(`Explain the current role of ${variableLabels[0]}.`)
  }
  if (facts.preprocessingComplete) {
    suggestions.push('Summarize the dataset analysis and any rejected rows.')
    suggestions.push('Check the preparation workflow for data leakage risks.')
  }
  if (facts.preprocessingApproved && !facts.mlPreprocessingReady) {
    suggestions.push('Summarize the proposed preprocessing plan.')
    suggestions.push('Why were these preprocessing steps selected?')
  }
  if (facts.mlPreprocessingReady) suggestions.push('Compare the validated and training-ready datasets.')
  if (facts.hasTrainingRequest) suggestions.push('Explain the managed and local training paths for this project.')
  if (facts.championActive) suggestions.push('What should I review before trusting the active champion model?')
  if (!suggestions.length) suggestions.push('What must I review before this project is ready for training?')
  return Array.from(new Set(suggestions)).slice(0, 4)
}
