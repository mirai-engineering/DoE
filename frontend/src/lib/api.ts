import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

export interface ProjectSummary {
  id: string
  display_name: string
}

export interface ProjectsResponse {
  projects: ProjectSummary[]
}

export interface SchemaInput {
  name: string
  label: string
  type: 'continuous'
  min: number
  max: number
  unit: string
}

export interface SchemaOutput {
  name: string
  label: string
  direction: 'maximize' | 'minimize'
  unit: string
}

export interface ProjectSchema {
  project_id: string
  display_name: string
  description?: string
  schema_version?: string
  allow_unknown_inputs?: boolean
  inputs: SchemaInput[]
  outputs: SchemaOutput[]
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
      }
    }),
  }
}

function assertProjectSchema(value: unknown): ProjectSchema {
  if (!isRecord(value) || !Array.isArray(value.inputs) || !Array.isArray(value.outputs)) {
    throw new ApiError('Invalid API response: project schema shape is invalid')
  }

  return {
    project_id: assertString(value.project_id, 'schema.project_id'),
    display_name: assertString(value.display_name, 'schema.display_name'),
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

export async function getProjects(): Promise<ProjectSummary[]> {
  try {
    const response = await api.get<unknown>('/projects')
    return assertProjectsResponse(response.data).projects
  } catch (error) {
    throw normalizeError(error, 'Unable to load projects')
  }
}

export async function getProjectSchema(projectId: string): Promise<ProjectSchema> {
  try {
    const response = await api.get<unknown>(`/projects/${projectId}/schema`)
    return assertProjectSchema(response.data)
  } catch (error) {
    throw normalizeError(error, 'Unable to load project schema')
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
