import axios from 'axios'

const DEFAULT_API_URL = typeof window !== 'undefined' && window.location.port === '3000' ? 'http://localhost:8000' : ''
const API_URL = import.meta.env.VITE_API_URL ?? DEFAULT_API_URL

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

type AuthTokenProvider = () => Promise<string | null>

let authTokenProvider: AuthTokenProvider | null = null

export function setAuthTokenProvider(provider: AuthTokenProvider | null) {
  authTokenProvider = provider
}

api.interceptors.request.use(async (config) => {
  if (!authTokenProvider) return config

  const token = await authTokenProvider()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export interface WorkspaceSummary {
  workspace_id: string
  display_name: string
  client_type?: string
  status?: string
  default_template_ids?: string[]
  allowed_extractors?: string[]
  lifecycle_contract?: string
  storage?: Record<string, unknown>
  storage_provisioned?: boolean
}

export interface ProjectSummary {
  id: string
  display_name: string
  workspace_id?: string
  workspace_name?: string
  storage?: Record<string, unknown>
}

export interface AccountStatus {
  status: 'active_single_workspace' | 'no_workspace_membership' | 'workspace_selection_required' | string
  message?: string
  can_create_project: boolean
  can_upload: boolean
  can_train: boolean
  can_predict: boolean
}

export interface ProjectsResponse {
  projects: ProjectSummary[]
  workspaces: WorkspaceSummary[]
  account?: AccountStatus
}

export interface SchemaInput {
  name: string
  variable_id?: string
  label: string
  ui_label?: string
  type: 'continuous'
  dtype?: string
  min: number
  max: number
  unit: string
  role?: VariableRole
  source_table?: string
  source_name?: string
  description?: string
}

export interface SchemaOutput {
  name: string
  variable_id?: string
  label: string
  ui_label?: string
  direction: 'maximize' | 'minimize'
  unit: string
  role?: VariableRole
  source_table?: string
  source_name?: string
  description?: string
}

export type VariableRole = 'id' | 'input' | 'output' | 'group' | 'sweep' | 'time' | 'metadata' | 'context' | 'cycle' | 'sequence' | 'curve_axis' | 'ignore'
export type TemplateId = 'fuel_cell' | 'generic_tabular_doe'

export interface VariableMetadata {
  name: string
  variable_id?: string
  label: string
  ui_label?: string
  unit?: string
  dtype?: string
  role: VariableRole
  source_table?: string
  source_name?: string
  description?: string
  semantic_type?: string
  direction?: 'maximize' | 'minimize' | 'target' | null
  min?: number | null
  max?: number | null
  approved?: boolean
  recommended_plot_roles?: string[]
}

export interface PlotRecipeAxis {
  source: string
  variable?: string
  variables?: string[]
  label?: string
  unit?: string
}

export interface PlotRecipe {
  id: string
  label: string
  description?: string
  kind: string
  template_id?: TemplateId | string
  safe?: boolean
  recommended?: boolean
  x?: PlotRecipeAxis
  y?: PlotRecipeAxis
  series?: Array<Record<string, unknown>>
  group_by?: string | null
  filters?: string[]
}

export interface UiConfig {
  selected_plot_recipe_id?: string
  plot_recipes?: PlotRecipe[]
  model_quality?: Record<string, unknown>
  design_studio?: Record<string, unknown>
  business_impact?: Record<string, unknown>
}

export interface ProjectDomainMetadata {
  template_id: TemplateId | string
  label: string
  test_article_label?: string
  inferred?: boolean
  approval_status?: string
  approved_by?: string | null
  variables?: VariableMetadata[]
  all_variables?: VariableMetadata[]
  split_hints?: Record<string, unknown>
  joins?: Array<Record<string, unknown>>
  ui_config?: UiConfig
}

export interface ProjectSchemaMetadata {
  domain?: string
  template_id?: TemplateId | string
  variables?: VariableMetadata[]
  all_variables?: VariableMetadata[]
  split_hints?: Record<string, unknown>
  joins?: Array<Record<string, unknown>>
  dictionary_fields?: string[]
}

export interface ProjectSchema {
  project_id: string
  display_name: string
  workspace_id?: string
  workspace_name?: string
  description?: string
  schema_version?: string
  allow_unknown_inputs?: boolean
  inputs: SchemaInput[]
  outputs: SchemaOutput[]
  metadata?: ProjectSchemaMetadata
  domain_metadata?: ProjectDomainMetadata
}

export interface ArtifactPointer {
  project_id?: string
  workspace_id?: string
  artifact_kind?: string
  bucket?: string
  object_key?: string
  object_uri?: string
  runtime_status?: string
  status?: string
  detail?: string
}

export interface ProjectArtifactStatus {
  project_id: string
  display_name: string
  workspace_id?: string
  workspace_name?: string
  artifact_pointers: Record<string, ArtifactPointer>
  model_quality: {
    available: boolean
    message: string
    detail?: string
    prediction_diagnostics_available?: boolean
  }
  durability_note: string
}

export type ExperimentInputs = Record<string, number>
export type PredictionMap = Record<string, number>

export interface PredictResponse {
  project_id: string
  predictions: PredictionMap
  model_version: string
  warnings: string[]
}

export interface BatchPredictResponse {
  project_id: string
  predictions: PredictionMap[]
  model_version: string
  warnings: string[]
}

export interface RecommendRequest {
  objective_weights: Record<string, number>
  fixed_inputs?: Record<string, number>
  constraints?: Record<string, unknown>
  n_candidates: number
  top_k: number
}

export interface Recommendation {
  inputs: ExperimentInputs
  predictions: PredictionMap
  score: number
}

export interface RecommendResponse {
  project_id: string
  recommendations: Recommendation[]
  model_version: string
  warnings: string[]
}

export interface IntakeFileInventoryItem {
  filename: string
  original_filename?: string | null
  relative_path: string
  content_type: string
  size_bytes: number
  sha256: string
  suffix: string
  bucket?: string
  object_key?: string
  object_uri?: string
  storage_provider?: string
}

export interface IngestionSessionResponse {
  project_id: string
  project_name: string
  workspace_id?: string | null
  workspace_name?: string | null
  dataset_id: string
  ingestion_session_id: string
  status: string
  approval_status: string
  created_at: string
  updated_at: string
  storage: Record<string, unknown>
  files: IntakeFileInventoryItem[]
  notes: string
  ingestion_path?: 'generic_tabular_doe' | string
  lifecycle_contract?: 'generic_tabular_doe' | string
  mapping: Record<string, unknown>
  manifest_assistant: Record<string, unknown>
}

export interface IntakeSessionsResponse {
  sessions: IngestionSessionResponse[]
}

export interface MiraiContractValidation {
  valid: boolean
  errors: string[]
  template_id?: string | null
  table_count?: number
  column_count?: number
  input_count?: number
  output_count?: number
  package_type?: string
  deprecated_endpoint?: boolean
  message: string
}

export interface PreprocessingStatus {
  status: string
  updated_at?: string
  stage?: string
  row_counts?: Record<string, number>
  cell_ids?: string[]
  report_path?: string
  canonical_dir?: string
  training_artifact_dir?: string
  validation?: MiraiContractValidation
  [key: string]: unknown
}

export interface MLPreprocessingStatus {
  status: string
  updated_at?: string
  plan_id?: string
  run_id?: string
  action_count?: number
  summary?: string
  exports?: string[]
  model_table_preprocessed?: Record<string, unknown>
  [key: string]: unknown
}

export interface MLPreprocessingReport {
  status: string
  summary: string
  plan_id?: string | null
  run_id?: string | null
  risks?: string[]
  warnings?: string[]
  export_files?: string[]
  [key: string]: unknown
}

export interface DomainMetadataStatus {
  status: string
  approval_status: string
  template_id?: string
  domain_metadata: ProjectDomainMetadata
  updated_at?: string
  updated_by?: string
  approved_at?: string
  approved_by?: string
  notes?: string
}

export interface LinearTrainingConfig {
  include_mvlr: boolean
  fit_intercept: boolean
  include_ridge: boolean
  ridge_alphas: number[]
}

export interface MLPTrainingConfig {
  include: boolean
  architecture_family: string
  hidden_layers: number[]
  trunk_layers: number[]
  head_layers: number[]
  secondary_head_layers: number[]
  activation: string
  normalization: string
  dropout: number
  optimizer: string
  learning_rate: number
  weight_decay: number
  batch_size: number | string
  max_epochs: number
  early_stopping_patience: number
  loss: string
  output_weights: Record<string, number>
  seeds: number[]
}

export interface TrainingSearchConfig {
  mode: string
  wall_clock_budget_minutes: number
  rerun_top_k: number
}

export interface TrainingConfiguration {
  linear: LinearTrainingConfig
  mlp: MLPTrainingConfig
  search: TrainingSearchConfig
  selection_metric: string
}

export interface TrainingRequestResponse {
  training_request_id: string
  project_id: string
  dataset_id: string
  ingestion_session_id: string
  status: string
  preset: string
  model_families: string[]
  training_config?: TrainingConfiguration
  training_plan?: Record<string, unknown>
  route_after_completion?: string
  [key: string]: unknown
}

export interface ExternalMlflowRunImportRequest {
  mlflow_run_id: string
  registered_model_name?: string
  model_version?: string
  alias: string
  notes?: string
}

export interface ChampionLoadRequest {
  mlflow_run_id?: string
  registered_model_name?: string
  model_version?: string
  notes?: string
}

export interface PreprocessingEdaSummary {
  status: PreprocessingStatus
  summary: {
    cell_archive_count?: number
    extracted_file_count?: number
    cells_succeeded?: number
    cells_failed?: number
    model_rows?: number
    canonical_tables?: Record<string, number>
    missingness?: Record<string, number>
    duplicate_feature_target_rows?: number
    duplicate_input_rows?: number
    rejected_rows?: { count?: number; reasons?: Record<string, number> }
    split_counts?: Record<string, number>
    split_strategy?: string
    bo_policy?: string
    input_distributions?: Record<string, Record<string, number>>
    output_distributions?: Record<string, Record<string, number>>
    leakage_warnings?: string[]
  }
  artifacts: {
    canonical_dir?: string
    training_artifact_dir?: string
    ydata_html_endpoint?: string
    ydata_html_exists?: boolean
    eda_report_json?: string
    split_report_json?: string
    preprocessing_report_json?: string
    canonical_files?: string[]
    plots?: string[]
  }
  approval: Record<string, unknown>
}

export type PreprocessingReport = Record<string, unknown>
export type TrainingStatus = Record<string, unknown>

export type BOExperimentStatus =
  | 'suggested'
  | 'accepted'
  | 'rejected'
  | 'skipped'
  | 'tested'
  | 'observed'

export type BOExperimentSource =
  | 'initial_observed'
  | 'bo_suggested'
  | 'replay_revealed'
  | 'manual_observed'

export type BOReviewDecision = 'none' | 'accepted' | 'rejected' | 'skipped'
export type BOReviewReason =
  | 'infeasible'
  | 'unsafe'
  | 'too_expensive'
  | 'outside_protocol'
  | 'chemically_implausible'
  | 'duplicate'
  | 'other'

export type BOExplorationLevel = 'conservative' | 'balanced' | 'exploratory'
export type BOAcquisitionFunction = 'ei' | 'ucb'

export interface BOInputConstraint {
  min?: number | null
  max?: number | null
  fixed?: number | null
}

export interface BOConfig {
  objective_weights: Record<string, number>
  strategy?: BOExplorationLevel
  acquisition_function?: BOAcquisitionFunction
  exploration_level?: BOExplorationLevel
  n_suggestions?: number
  input_constraints?: Record<string, BOInputConstraint>
  random_seed?: number
  replay_mode?: boolean
}

export interface BOConfigUpdate {
  objective_weights?: Record<string, number>
  strategy?: BOExplorationLevel
  acquisition_function?: BOAcquisitionFunction
  exploration_level?: BOExplorationLevel
  n_suggestions?: number
  input_constraints?: Record<string, BOInputConstraint>
  random_seed?: number
  replay_mode?: boolean
}

export interface BOReview {
  decision: BOReviewDecision
  reason?: BOReviewReason | null
  notes?: string | null
}

export interface LoggedExperiment {
  experiment_id: string
  project_id: string
  iteration: number
  source: BOExperimentSource
  status: BOExperimentStatus
  inputs: ExperimentInputs
  predicted_outputs?: PredictionMap | null
  observed_outputs?: PredictionMap | null
  uncertainty?: Record<string, unknown> | null
  objective?: Record<string, number | null> | null
  review?: BOReview | null
  metadata: Record<string, unknown>
}

export interface BOCurrentBest {
  experiment_id: string
  inputs: ExperimentInputs
  observed_outputs: PredictionMap
  observed_score: number
}

export interface BOStateResponse {
  project_id: string
  observed_count: number
  suggested_count: number
  rejected_count: number
  current_best?: BOCurrentBest | null
  latest_suggestion?: LoggedExperiment | null
  history: LoggedExperiment[]
  config: Required<BOConfig>
}

export interface BOInitializeReplayRequest {
  reset: boolean
  n_initial: number
  selection: 'diverse' | 'random' | 'first_n'
}

export interface BOSuggestResponse {
  suggestion: LoggedExperiment
  state: BOStateResponse
}

export interface BOReviewRequest {
  decision: Exclude<BOReviewDecision, 'none'>
  reason?: BOReviewReason | null
  notes?: string | null
}

export interface BOReviewResponse {
  experiment: LoggedExperiment
  state: BOStateResponse
}

export interface BORevealReplayExperiment {
  suggested_inputs: ExperimentInputs
  matched_replay_inputs: ExperimentInputs
  observed_outputs: PredictionMap
  predicted_outputs?: PredictionMap | null
  prediction_error?: PredictionMap | null
  replay_distance: number
}

export interface BORevealReplayResponse {
  experiment: BORevealReplayExperiment
  logged_experiment: LoggedExperiment
  state: BOStateResponse
}

export interface BOFantasyRolloutRequest {
  steps: number
  config?: BOConfig
}

export interface BOFantasyStep {
  iteration: number
  inputs: ExperimentInputs
  predicted_outputs: PredictionMap
  predicted_score: number
  acquisition_score: number
  expected_improvement: number
  uncertainty: Record<string, unknown>
  distance_to_nearest_real: number
  low_confidence_region: boolean
  source: 'mlp_fantasy'
}

export interface BOFantasyRolloutResponse {
  project_id: string
  fantasy_trajectory: BOFantasyStep[]
  metadata: Record<string, unknown>
}

export interface ModelQualityPredictionsResponse {
  project_id: string
  source: string
  columns: string[]
  rows: Array<Record<string, unknown>>
  row_count: number
  total_row_count: number
  truncated: boolean
}

export interface ModelQualitySummary {
  project_id: string
  quality_label: string
  warning?: string | null
  metrics: Record<string, unknown>
  preprocessing_report: Record<string, unknown>
  artifact_summary: Record<string, unknown>
  active_model: Record<string, unknown>
  latest_runs: Array<Record<string, unknown>>
  candidate_comparison?: Array<Record<string, unknown>>
  ai_preprocessing_assistant: Record<string, unknown>
}

export interface DesignStudioOverlayColumn {
  name: string
  label: string
  role?: string
  dtype?: string
  unit?: string
  filter_kind: 'exact' | 'range' | string
  distinct_count?: number
  values?: Array<string | number | boolean | null>
  min?: number
  max?: number
  searchable?: boolean
  recommended?: boolean
}

export interface DesignStudioOverlayOptions {
  source: string
  available: boolean
  columns: DesignStudioOverlayColumn[]
  row_count: number
}

export interface DesignStudioState {
  project_id: string
  workspace_id?: string | null
  active_model: Record<string, unknown>
  inputs: SchemaInput[]
  outputs: SchemaOutput[]
  default_inputs: Record<string, number>
  default_objective_weights: Record<string, number>
  plot_recipes?: PlotRecipe[]
  selected_plot_recipe_id?: string
  presets: Record<string, unknown>
  real_cell_options: Array<Record<string, unknown>>
  training_overlay_options?: DesignStudioOverlayOptions
}

export interface DesignStudioParetoCandidate {
  rank: number
  label: string
  inputs: Record<string, number>
  predictions: Record<string, number>
  score: number
  tradeoff_summary: string
}

export interface DesignStudioParetoResponse {
  project_id: string
  source: string
  model_version: string
  objective_weights: Record<string, number>
  objectives: Array<Record<string, unknown>>
  n_candidates: number
  pareto_count: number
  returned_count: number
  candidates: DesignStudioParetoCandidate[]
  warnings: string[]
}

export interface DesignStudioPrediction {
  project_id: string
  source: string
  model_version: string
  inputs: Record<string, number>
  predictions_at_selected_point: Record<string, number>
  curve?: Record<string, unknown> | null
  warnings: string[]
  comparison_real_cell?: Record<string, unknown> | null
  training_overlay?: Record<string, unknown> | null
  seed?: Record<string, unknown>
}

export interface BusinessImpactSummary {
  project_id: string
  title: string
  headline: Record<string, string>
  case_study: Record<string, number | string>
  scenario: Record<string, unknown>
  visuals: {
    funnel: Array<Record<string, unknown>>
    time_comparison: Array<Record<string, unknown>>
    cost_comparison: Array<Record<string, unknown>>
  }
  takeaways: Array<{ title: string; body: string }>
  sources: Array<{ label: string; claim: string; url: string }>
  caveats: string[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function assertString(value: unknown, label: string): string {
  if (typeof value !== 'string') throw new ApiError(`Invalid API response: ${label} must be a string`)
  return value
}

function assertNumber(value: unknown, label: string): number {
  if (typeof value !== 'number') throw new ApiError(`Invalid API response: ${label} must be a number`)
  return value
}

function assertStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new ApiError(`Invalid API response: ${label} must be an array of strings`)
  }
  return value
}

function assertNumberRecord(value: unknown, label: string): Record<string, number> {
  if (!isRecord(value)) throw new ApiError(`Invalid API response: ${label} must be an object`)

  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, assertNumber(item, `${label}.${key}`)]),
  )
}

function assertProjectsResponse(value: unknown): ProjectsResponse {
  if (!isRecord(value) || !Array.isArray(value.projects)) {
    throw new ApiError('Invalid API response: projects must be an array')
  }

  return {
    projects: value.projects.map((project, index) => {
      if (!isRecord(project)) {
        throw new ApiError(`Invalid API response: projects.${index} must be an object`)
      }
      return {
        id: assertString(project.id, `projects.${index}.id`),
        display_name: assertString(project.display_name, `projects.${index}.display_name`),
        workspace_id: typeof project.workspace_id === 'string' ? project.workspace_id : undefined,
        workspace_name: typeof project.workspace_name === 'string' ? project.workspace_name : undefined,
        storage: isRecord(project.storage) ? project.storage : undefined,
      }
    }),
    workspaces: Array.isArray(value.workspaces)
      ? value.workspaces.map((workspace, index) => {
        if (!isRecord(workspace)) {
          throw new ApiError(`Invalid API response: workspaces.${index} must be an object`)
        }
        return {
          workspace_id: assertString(workspace.workspace_id, `workspaces.${index}.workspace_id`),
          display_name: assertString(workspace.display_name, `workspaces.${index}.display_name`),
          client_type: typeof workspace.client_type === 'string' ? workspace.client_type : undefined,
          status: typeof workspace.status === 'string' ? workspace.status : undefined,
          default_template_ids: Array.isArray(workspace.default_template_ids) ? workspace.default_template_ids.filter((item): item is string => typeof item === 'string') : undefined,
          allowed_extractors: Array.isArray(workspace.allowed_extractors) ? workspace.allowed_extractors.filter((item): item is string => typeof item === 'string') : undefined,
          lifecycle_contract: typeof workspace.lifecycle_contract === 'string' ? workspace.lifecycle_contract : undefined,
          storage: isRecord(workspace.storage) ? workspace.storage : undefined,
          storage_provisioned: typeof workspace.storage_provisioned === 'boolean' ? workspace.storage_provisioned : undefined,
        }
      })
      : [],
    account: isRecord(value.account)
      ? {
        status: typeof value.account.status === 'string' ? value.account.status : 'active_single_workspace',
        message: typeof value.account.message === 'string' ? value.account.message : undefined,
        can_create_project: typeof value.account.can_create_project === 'boolean' ? value.account.can_create_project : true,
        can_upload: typeof value.account.can_upload === 'boolean' ? value.account.can_upload : true,
        can_train: typeof value.account.can_train === 'boolean' ? value.account.can_train : true,
        can_predict: typeof value.account.can_predict === 'boolean' ? value.account.can_predict : true,
      }
      : undefined,
  }
}

function assertProjectSchema(value: unknown): ProjectSchema {
  if (!isRecord(value) || !Array.isArray(value.inputs) || !Array.isArray(value.outputs)) {
    throw new ApiError('Invalid API response: project schema shape is invalid')
  }

  return {
    project_id: assertString(value.project_id, 'schema.project_id'),
    display_name: assertString(value.display_name, 'schema.display_name'),
    workspace_id: typeof value.workspace_id === 'string' ? value.workspace_id : undefined,
    workspace_name: typeof value.workspace_name === 'string' ? value.workspace_name : undefined,
    description: typeof value.description === 'string' ? value.description : undefined,
    schema_version: typeof value.schema_version === 'string' ? value.schema_version : undefined,
    allow_unknown_inputs:
      typeof value.allow_unknown_inputs === 'boolean' ? value.allow_unknown_inputs : undefined,
    inputs: value.inputs.map((input, index) => {
      if (!isRecord(input)) {
        throw new ApiError(`Invalid API response: inputs.${index} must be an object`)
      }
      return {
        name: assertString(input.name, `inputs.${index}.name`),
        label: assertString(input.label, `inputs.${index}.label`),
        type: input.type === 'continuous' ? input.type : 'continuous',
        min: assertNumber(input.min, `inputs.${index}.min`),
        max: assertNumber(input.max, `inputs.${index}.max`),
        unit: assertString(input.unit, `inputs.${index}.unit`),
      }
    }),
    outputs: value.outputs.map((output, index) => {
      if (!isRecord(output)) {
        throw new ApiError(`Invalid API response: outputs.${index} must be an object`)
      }
      const direction = output.direction
      if (direction !== 'maximize' && direction !== 'minimize') {
        throw new ApiError(`Invalid API response: outputs.${index}.direction is invalid`)
      }
      return {
        name: assertString(output.name, `outputs.${index}.name`),
        label: assertString(output.label, `outputs.${index}.label`),
        direction,
        unit: assertString(output.unit, `outputs.${index}.unit`),
      }
    }),
  }
}

function assertPredictResponse(value: unknown): PredictResponse {
  if (!isRecord(value)) throw new ApiError('Invalid API response: prediction response is invalid')
  return {
    project_id: assertString(value.project_id, 'predict.project_id'),
    predictions: assertNumberRecord(value.predictions, 'predict.predictions'),
    model_version: assertString(value.model_version, 'predict.model_version'),
    warnings: assertStringArray(value.warnings, 'predict.warnings'),
  }
}

function assertBatchPredictResponse(value: unknown): BatchPredictResponse {
  if (!isRecord(value) || !Array.isArray(value.predictions)) {
    throw new ApiError('Invalid API response: batch prediction response is invalid')
  }
  return {
    project_id: assertString(value.project_id, 'batch.project_id'),
    predictions: value.predictions.map((prediction, index) =>
      assertNumberRecord(prediction, `batch.predictions.${index}`),
    ),
    model_version: assertString(value.model_version, 'batch.model_version'),
    warnings: assertStringArray(value.warnings, 'batch.warnings'),
  }
}

function assertRecommendResponse(value: unknown): RecommendResponse {
  if (!isRecord(value) || !Array.isArray(value.recommendations)) {
    throw new ApiError('Invalid API response: recommendation response is invalid')
  }
  return {
    project_id: assertString(value.project_id, 'recommend.project_id'),
    recommendations: value.recommendations.map((recommendation, index) => {
      if (!isRecord(recommendation)) {
        throw new ApiError(`Invalid API response: recommendations.${index} must be an object`)
      }
      return {
        inputs: assertNumberRecord(recommendation.inputs, `recommendations.${index}.inputs`),
        predictions: assertNumberRecord(
          recommendation.predictions,
          `recommendations.${index}.predictions`,
        ),
        score: assertNumber(recommendation.score, `recommendations.${index}.score`),
      }
    }),
    model_version: assertString(value.model_version, 'recommend.model_version'),
    warnings: assertStringArray(value.warnings, 'recommend.warnings'),
  }
}

function normalizeError(error: unknown, fallback: string): ApiError {
  if (axios.isAxiosError(error)) {
    if (error.code === 'ECONNREFUSED' || error.message.includes('Network Error')) {
      return new ApiError('Unable to connect to the DoE API. Check that the backend is running.')
    }

    const responseData = error.response?.data
    const detail = isRecord(responseData) ? responseData.detail : undefined
    if (typeof detail === 'string') {
      return new ApiError(detail)
    }
    if (Array.isArray(detail)) {
      return new ApiError(
        detail
          .map((item) => (isRecord(item) && typeof item.msg === 'string' ? item.msg : JSON.stringify(item)))
          .join('; '),
      )
    }
    if (isRecord(responseData) && typeof responseData.message === 'string') {
      return new ApiError(responseData.message)
    }
  }

  if (error instanceof Error) {
    return new ApiError(error.message)
  }
  return new ApiError(fallback)
}

export async function getProjectsResponse(): Promise<ProjectsResponse> {
  try {
    const response = await api.get<unknown>('/projects')
    return assertProjectsResponse(response.data)
  } catch (error) {
    throw normalizeError(error, 'Unable to load projects')
  }
}

export async function getProjects(): Promise<ProjectSummary[]> {
  return (await getProjectsResponse()).projects
}

export async function getProjectSchema(projectId: string): Promise<ProjectSchema> {
  try {
    const response = await api.get<unknown>(`/projects/${projectId}/schema`)
    return assertProjectSchema(response.data)
  } catch (error) {
    throw normalizeError(error, 'Unable to load project schema')
  }
}

export async function getProjectArtifactStatus(projectId: string): Promise<ProjectArtifactStatus> {
  try {
    const response = await api.get<ProjectArtifactStatus>(`/projects/${projectId}/artifact-status`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load project artifact status')
  }
}

export async function createIngestionSession(
  projectName: string,
  files: File[],
  notes?: string,
  options: { workspaceName?: string; existingProjectId?: string } = {},
): Promise<IngestionSessionResponse> {
  try {
    const formData = new FormData()
    formData.append('project_name', projectName)
    if (notes) formData.append('notes', notes)
    formData.append('ingestion_path', 'generic_tabular_doe')
    if (options.workspaceName) formData.append('workspace_name', options.workspaceName)
    if (options.existingProjectId) formData.append('existing_project_id', options.existingProjectId)
    files.forEach((file) => formData.append('files', file))
    const response = await api.post<IngestionSessionResponse>('/data-intake/sessions', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to create ingestion session')
  }
}

export async function listIngestionSessions(projectId?: string): Promise<IngestionSessionResponse[]> {
  try {
    const response = await api.get<IntakeSessionsResponse>('/data-intake/sessions', {
      params: projectId ? { project_id: projectId } : undefined,
    })
    return response.data.sessions
  } catch (error) {
    throw normalizeError(error, 'Unable to list ingestion sessions')
  }
}

function sessionPath(session: Pick<IngestionSessionResponse, 'project_id' | 'dataset_id' | 'ingestion_session_id'>): string {
  return `/data-intake/projects/${session.project_id}/datasets/${session.dataset_id}/sessions/${session.ingestion_session_id}`
}

export async function appendIngestionFiles(session: IngestionSessionResponse, files: File[]): Promise<IngestionSessionResponse> {
  try {
    const formData = new FormData()
    files.forEach((file) => formData.append('files', file))
    const response = await api.post<IngestionSessionResponse>(`${sessionPath(session)}/files`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to append files to ingestion session')
  }
}

export async function validateMiraiContract(session: IngestionSessionResponse): Promise<MiraiContractValidation> {
  try {
    const response = await api.get<MiraiContractValidation>(`${sessionPath(session)}/fuel-cell-package/validation`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to validate Mirai contract')
  }
}

export async function startMiraiPreprocessing(session: IngestionSessionResponse): Promise<PreprocessingStatus> {
  try {
    const response = await api.post<PreprocessingStatus>(`${sessionPath(session)}/preprocessing/start`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to start preprocessing')
  }
}

export async function getPreprocessingStatus(session: IngestionSessionResponse): Promise<PreprocessingStatus> {
  try {
    const response = await api.get<PreprocessingStatus>(`${sessionPath(session)}/preprocessing/status`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load preprocessing status')
  }
}

export async function getPreprocessingReport(session: IngestionSessionResponse): Promise<PreprocessingReport> {
  try {
    const response = await api.get<PreprocessingReport>(`${sessionPath(session)}/preprocessing-report`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load preprocessing report')
  }
}

export function preprocessingYdataReportUrl(session: IngestionSessionResponse): string {
  return `${API_URL}${sessionPath(session)}/preprocessing/ydata-report.html`
}

export async function getPreprocessingYdataReportBlob(session: IngestionSessionResponse): Promise<{ blob: Blob; filename: string }> {
  try {
    const response = await api.get<Blob>(`${sessionPath(session)}/preprocessing/ydata-report.html`, {
      responseType: 'blob',
    })
    return {
      blob: response.data,
      filename: filenameFromContentDisposition(response.headers['content-disposition']) ?? 'mirai_ydata_profile.html',
    }
  } catch (error) {
    throw normalizeError(error, 'Unable to open HTML EDA report')
  }
}

export async function getPreprocessingEdaSummary(session: IngestionSessionResponse): Promise<PreprocessingEdaSummary> {
  try {
    const response = await api.get<PreprocessingEdaSummary>(`${sessionPath(session)}/preprocessing/eda-summary`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load preprocessing EDA summary')
  }
}

export async function getDomainMetadata(session: IngestionSessionResponse): Promise<DomainMetadataStatus> {
  try {
    const response = await api.get<DomainMetadataStatus>(`${sessionPath(session)}/domain-metadata`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load metadata setup')
  }
}

export async function updateDomainMetadata(session: IngestionSessionResponse, domainMetadata: ProjectDomainMetadata, notes?: string): Promise<DomainMetadataStatus> {
  try {
    const response = await api.put<DomainMetadataStatus>(`${sessionPath(session)}/domain-metadata`, { domain_metadata: domainMetadata, updated_by: 'Mirai admin', notes })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to save metadata setup')
  }
}

export async function approveDomainMetadata(session: IngestionSessionResponse, notes?: string): Promise<DomainMetadataStatus> {
  try {
    const response = await api.post<DomainMetadataStatus>(`${sessionPath(session)}/domain-metadata/approval`, { approver: 'Mirai admin', notes })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to approve metadata setup')
  }
}

export async function approvePreprocessing(session: IngestionSessionResponse, notes?: string): Promise<PreprocessingReport> {
  try {
    const response = await api.post<PreprocessingReport>(`${sessionPath(session)}/preprocessing-approval`, { approver: 'Mirai admin', notes })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to approve preprocessing')
  }
}

export async function startMLPreprocessing(session: IngestionSessionResponse): Promise<MLPreprocessingStatus> {
  try {
    const response = await api.post<MLPreprocessingStatus>(`${sessionPath(session)}/ml-preprocessing/start`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to start ML preprocessing')
  }
}

export async function getMLPreprocessingStatus(session: IngestionSessionResponse): Promise<MLPreprocessingStatus> {
  try {
    const response = await api.get<MLPreprocessingStatus>(`${sessionPath(session)}/ml-preprocessing/status`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load ML preprocessing status')
  }
}

export async function approveMLPreprocessing(session: IngestionSessionResponse, notes?: string): Promise<MLPreprocessingStatus> {
  try {
    const response = await api.post<MLPreprocessingStatus>(`${sessionPath(session)}/ml-preprocessing/approval`, { approver: 'Mirai admin', notes })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to approve ML preprocessing')
  }
}

export async function executeMLPreprocessing(session: IngestionSessionResponse): Promise<MLPreprocessingStatus> {
  try {
    const response = await api.post<MLPreprocessingStatus>(`${sessionPath(session)}/ml-preprocessing/execute`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to execute ML preprocessing')
  }
}

export async function getMLPreprocessingReport(session: IngestionSessionResponse): Promise<MLPreprocessingReport> {
  try {
    const response = await api.get<MLPreprocessingReport>(`${sessionPath(session)}/ml-preprocessing/report`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load ML preprocessing report')
  }
}

export function mlPreprocessedTableUrl(session: IngestionSessionResponse): string {
  return `${API_URL}${sessionPath(session)}/ml-preprocessing/model-table-preprocessed.csv`
}

export async function getMLPreprocessedTableBlob(session: IngestionSessionResponse): Promise<{ blob: Blob; filename: string }> {
  try {
    const response = await api.get<Blob>(`${sessionPath(session)}/ml-preprocessing/model-table-preprocessed.csv`, { responseType: 'blob' })
    return { blob: response.data, filename: filenameFromContentDisposition(response.headers['content-disposition']) ?? 'model_table_preprocessed.csv' }
  } catch (error) {
    throw normalizeError(error, 'Unable to download preprocessed model table')
  }
}

export async function listTrainingRequests(session: IngestionSessionResponse): Promise<TrainingRequestResponse[]> {
  try {
    const response = await api.get<{ training_requests: TrainingRequestResponse[] }>(`${sessionPath(session)}/training-requests`)
    return response.data.training_requests ?? []
  } catch (error) {
    throw normalizeError(error, 'Unable to load training requests')
  }
}

export async function createTrainingRequest(session: IngestionSessionResponse, trainingConfig?: TrainingConfiguration): Promise<TrainingRequestResponse> {
  try {
    const response = await api.post<TrainingRequestResponse>(`${sessionPath(session)}/training-requests`, {
      requested_by: 'Mirai admin',
      preset: trainingConfig?.search.mode ?? 'balanced_training',
      model_families: ['mean_baseline', 'mvlr', 'ridge', 'mlp'],
      training_config: trainingConfig,
      notes: 'Created from Preprocessing Review UI.',
    })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to create training request')
  }
}

export async function startTrainingRequest(session: IngestionSessionResponse, trainingRequestId: string): Promise<TrainingStatus> {
  try {
    const response = await api.post<TrainingStatus>(`${sessionPath(session)}/training-requests/${trainingRequestId}/start`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to start training')
  }
}

export async function getTrainingStatus(session: IngestionSessionResponse, trainingRequestId: string): Promise<TrainingStatus> {
  try {
    const response = await api.get<TrainingStatus>(`${sessionPath(session)}/training-requests/${trainingRequestId}/status`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load training status')
  }
}

export async function importExternalMlflowRun(session: IngestionSessionResponse, trainingRequestId: string, payload: ExternalMlflowRunImportRequest): Promise<TrainingStatus> {
  try {
    const response = await api.post<TrainingStatus>(`${sessionPath(session)}/training-requests/${trainingRequestId}/import-mlflow-run`, payload)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to import MLflow run')
  }
}

export async function loadChampionModel(projectId: string, payload: ChampionLoadRequest = {}): Promise<TrainingStatus> {
  try {
    const response = await api.post<TrainingStatus>(`/projects/${projectId}/models/load-champion-model`, payload)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load champion model')
  }
}

export async function refreshApprovedChampion(projectId: string, payload: ChampionLoadRequest = {}): Promise<TrainingStatus> {
  return loadChampionModel(projectId, payload)
}

function filenameFromContentDisposition(header?: string): string | null {
  if (!header) return null
  const quoted = header.match(/filename="([^"]+)"/i)
  if (quoted?.[1]) return quoted[1]
  const plain = header.match(/filename=([^;]+)/i)
  return plain?.[1]?.trim() ?? null
}

export async function exportApprovedTrainingPackage(session: IngestionSessionResponse, trainingRequestId: string): Promise<void> {
  try {
    const response = await api.get<Blob>(`${sessionPath(session)}/training-requests/${trainingRequestId}/export-package`, {
      responseType: 'blob',
    })
    const filename = filenameFromContentDisposition(response.headers['content-disposition'])
      ?? `mirai-training-package-${session.project_id}-${session.dataset_id}-${trainingRequestId}.zip`
    const url = window.URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } catch (error) {
    throw normalizeError(error, 'Unable to export approved training package')
  }
}

export async function predictExperiment(
  projectId: string,
  inputs: ExperimentInputs,
): Promise<PredictResponse> {
  try {
    const response = await api.post<unknown>(`/projects/${projectId}/predict`, { inputs })
    return assertPredictResponse(response.data)
  } catch (error) {
    throw normalizeError(error, 'Unable to predict experiment')
  }
}

export async function batchPredictExperiments(
  projectId: string,
  inputs: ExperimentInputs[],
): Promise<BatchPredictResponse> {
  try {
    const response = await api.post<unknown>(`/projects/${projectId}/batch-predict`, {
      inputs,
    })
    return assertBatchPredictResponse(response.data)
  } catch (error) {
    throw normalizeError(error, 'Unable to batch predict experiments')
  }
}

export async function recommendExperiments(
  projectId: string,
  request: RecommendRequest,
): Promise<RecommendResponse> {
  try {
    const response = await api.post<unknown>(`/projects/${projectId}/recommend`, request)
    return assertRecommendResponse(response.data)
  } catch (error) {
    throw normalizeError(error, 'Unable to recommend experiments')
  }
}

export async function getBOState(projectId: string): Promise<BOStateResponse> {
  try {
    const response = await api.get<BOStateResponse>(`/projects/${projectId}/bo/state`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load optimization loop state')
  }
}

export async function initializeBOReplay(
  projectId: string,
  request: BOInitializeReplayRequest,
): Promise<BOStateResponse> {
  try {
    const response = await api.post<BOStateResponse>(
      `/projects/${projectId}/bo/initialize-replay`,
      request,
    )
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to initialize replay loop')
  }
}

export async function suggestBOExperiment(
  projectId: string,
  request: BOConfig,
): Promise<BOSuggestResponse> {
  try {
    const response = await api.post<BOSuggestResponse>(`/projects/${projectId}/bo/suggest`, request)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to suggest the next BO experiment')
  }
}

export async function reviewBOExperiment(
  projectId: string,
  experimentId: string,
  request: BOReviewRequest,
): Promise<BOReviewResponse> {
  try {
    const response = await api.post<BOReviewResponse>(
      `/projects/${projectId}/bo/experiments/${experimentId}/review`,
      request,
    )
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to review BO suggestion')
  }
}

export async function revealBOReplayResult(
  projectId: string,
  experimentId: string,
): Promise<BORevealReplayResponse> {
  try {
    const response = await api.post<BORevealReplayResponse>(
      `/projects/${projectId}/bo/experiments/${experimentId}/reveal-replay-result`,
    )
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to reveal replay result')
  }
}

export async function saveBOConfig(
  projectId: string,
  request: BOConfigUpdate,
): Promise<BOStateResponse> {
  try {
    const response = await api.post<BOStateResponse>(`/projects/${projectId}/bo/config`, request)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to save BO configuration')
  }
}

export async function runBOFantasyRollout(
  projectId: string,
  request: BOFantasyRolloutRequest,
): Promise<BOFantasyRolloutResponse> {
  try {
    const response = await api.post<BOFantasyRolloutResponse>(
      `/projects/${projectId}/bo/fantasy-rollout`,
      request,
    )
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to run fantasy rollout')
  }
}

export async function getModelQualityPredictions(
  projectId: string,
  params?: { model_name?: string; splits?: string; limit?: number },
): Promise<ModelQualityPredictionsResponse> {
  try {
    const response = await api.get<ModelQualityPredictionsResponse>(`/projects/${projectId}/model-quality/predictions`, { params })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load prediction diagnostics')
  }
}

export function getModelQualityPredictionsExportUrl(
  projectId: string,
  params?: { model_name?: string; splits?: string },
): string {
  const search = new URLSearchParams()
  if (params?.model_name) search.set('model_name', params.model_name)
  if (params?.splits) search.set('splits', params.splits)
  const query = search.toString()
  return `${API_URL}/projects/${projectId}/model-quality/predictions/export.zip${query ? `?${query}` : ''}`
}

export async function getModelQualitySummary(projectId: string): Promise<ModelQualitySummary> {
  try {
    const response = await api.get<ModelQualitySummary>(`/projects/${projectId}/model-quality/summary`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load model quality summary')
  }
}

export async function getDesignStudioState(projectId: string): Promise<DesignStudioState> {
  try {
    const response = await api.get<DesignStudioState>(`/projects/${projectId}/design-studio/state`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load Design Studio')
  }
}

export async function predictDesignStudio(projectId: string, request: Record<string, unknown>): Promise<DesignStudioPrediction> {
  try {
    const response = await api.post<DesignStudioPrediction>(`/projects/${projectId}/design-studio/predict`, request)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to predict Design Studio candidate')
  }
}

export async function seedDesignStudioBatch(projectId: string, request: Record<string, unknown>): Promise<DesignStudioPrediction> {
  try {
    const response = await api.post<DesignStudioPrediction>(`/projects/${projectId}/design-studio/seed/batch`, request)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to seed Design Studio from batch search')
  }
}

export async function findDesignStudioPareto(projectId: string, request: Record<string, unknown>): Promise<DesignStudioParetoResponse> {
  try {
    const response = await api.post<DesignStudioParetoResponse>(`/projects/${projectId}/design-studio/pareto`, request)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to find Pareto tradeoff candidates')
  }
}

export async function exportDesignStudioZip(projectId: string, request: Record<string, unknown>): Promise<Blob> {
  try {
    const response = await api.post(`/projects/${projectId}/design-studio/export.zip`, request, { responseType: 'blob' })
    return response.data as Blob
  } catch (error) {
    throw normalizeError(error, 'Unable to export Design Studio package')
  }
}

export async function getBusinessImpactSummary(projectId: string): Promise<BusinessImpactSummary> {
  try {
    const response = await api.get<BusinessImpactSummary>(`/projects/${projectId}/impact/summary`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load business impact summary')
  }
}

export type DataScientistRole = 'user' | 'assistant'

export interface DataScientistMessage {
  role: DataScientistRole
  content: string
}

export type DataScientistStopReason =
  | 'completed'
  | 'max_turns'
  | 'max_tool_calls'
  | 'repeated_tool_call'
  | 'provider_unconfigured'
  | 'provider_error'
  | 'tool_error'
  | 'timeout'

export interface DataScientistEvent {
  type: 'message' | 'tool_call' | 'tool_result' | 'warning' | 'error' | 'stop'
  label: string
  detail?: string | null
  tool_name?: string | null
  metadata?: Record<string, unknown>
}

export interface DataScientistResponse {
  answer: string
  stop_reason: DataScientistStopReason
  events: DataScientistEvent[]
  usage?: {
    input_tokens?: number | null
    output_tokens?: number | null
    model?: string | null
  } | null
}

export async function askDataScientist(projectId: string, message: string, history: DataScientistMessage[] = [], signal?: AbortSignal): Promise<DataScientistResponse> {
  try {
    const response = await api.post<DataScientistResponse>(`/projects/${projectId}/data-scientist/messages`, { message, history }, { signal })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to ask Data Scientist')
  }
}
