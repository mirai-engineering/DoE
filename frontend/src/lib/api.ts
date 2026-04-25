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

function normalizeError(error: unknown, fallback: string): ApiError {
  if (axios.isAxiosError(error)) {
    if (error.code === 'ECONNREFUSED' || error.message.includes('Network Error')) {
      return new ApiError('Unable to connect to the DoE API. Check that the backend is running.')
    }

    const detail = error.response?.data?.detail
    if (typeof detail === 'string') {
      return new ApiError(detail)
    }
    if (Array.isArray(detail)) {
      return new ApiError(detail.map((item) => item.msg ?? JSON.stringify(item)).join('; '))
    }
    if (typeof error.response?.data?.message === 'string') {
      return new ApiError(error.response.data.message)
    }
  }

  if (error instanceof Error) {
    return new ApiError(error.message)
  }
  return new ApiError(fallback)
}

export async function getProjects(): Promise<ProjectSummary[]> {
  try {
    const response = await api.get<ProjectsResponse>('/projects')
    return response.data.projects
  } catch (error) {
    throw normalizeError(error, 'Unable to load projects')
  }
}

export async function getProjectSchema(projectId: string): Promise<ProjectSchema> {
  try {
    const response = await api.get<ProjectSchema>(`/projects/${projectId}/schema`)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to load project schema')
  }
}

export async function predictExperiment(
  projectId: string,
  inputs: ExperimentInputs,
): Promise<PredictResponse> {
  try {
    const response = await api.post<PredictResponse>(`/projects/${projectId}/predict`, { inputs })
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to predict experiment')
  }
}

export async function recommendExperiments(
  projectId: string,
  request: RecommendRequest,
): Promise<RecommendResponse> {
  try {
    const response = await api.post<RecommendResponse>(`/projects/${projectId}/recommend`, request)
    return response.data
  } catch (error) {
    throw normalizeError(error, 'Unable to recommend experiments')
  }
}
