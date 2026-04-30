import { FormEvent, useEffect, useState } from 'react'
import { ProjectHeader } from './components/ProjectHeader'
import { PredictPanel } from './components/PredictPanel'
import { RecommendPanel } from './components/RecommendPanel'
import { RecommendationsPage } from './components/RecommendationsPage'
import { VisualizationsPage } from './components/VisualizationsPage'
import { OptimizationLoopPage } from './components/bo/OptimizationLoopPage'
import { Alert } from './components/ui'
import type { ProjectSchema, ProjectSummary } from './lib/api'
import { getProjectSchema, getProjects, predictExperiment, recommendExperiments } from './lib/api'
import {
  clampInteger,
  defaultTableTopK,
  defaultVisualizationTopK,
  enabledFixedInputValues,
  initialFixedInputs,
  initialInputValues,
  initialWeights,
  maxVisualizationTopK,
  selectDefaultProject,
  toNumberMap,
} from './lib/doeUtils'
import type { ActiveTab, FixedInputConfig, RecommendationRun } from './types/doe'
import type { PredictionMap } from './lib/api'

function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('batch')
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [schema, setSchema] = useState<ProjectSchema | null>(null)
  const [appError, setAppError] = useState<string | null>(null)
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [schemaLoading, setSchemaLoading] = useState(false)

  const [inputValues, setInputValues] = useState<Record<string, string>>({})
  const [prediction, setPrediction] = useState<PredictionMap | null>(null)
  const [predictWarnings, setPredictWarnings] = useState<string[]>([])
  const [predictLoading, setPredictLoading] = useState(false)
  const [predictError, setPredictError] = useState<string | null>(null)

  const [objectiveWeights, setObjectiveWeights] = useState<Record<string, string>>({})
  const [fixedInputs, setFixedInputs] = useState<FixedInputConfig>({})
  const [nCandidates, setNCandidates] = useState('2000')
  const [tableTopK, setTableTopK] = useState(String(defaultTableTopK))
  const [visualizationTopK, setVisualizationTopK] = useState(String(defaultVisualizationTopK))
  const [recommendationRun, setRecommendationRun] = useState<RecommendationRun | null>(null)
  const [recommendWarnings, setRecommendWarnings] = useState<string[]>([])
  const [recommendLoading, setRecommendLoading] = useState(false)
  const [recommendError, setRecommendError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    async function loadProjects() {
      setProjectsLoading(true)
      setAppError(null)
      try {
        const projectList = await getProjects()
        if (!isMounted) return
        setProjects(projectList)
        setSelectedProjectId(selectDefaultProject(projectList)?.id ?? '')
      } catch (error) {
        if (isMounted) {
          setAppError(error instanceof Error ? error.message : 'Unable to load projects')
        }
      } finally {
        if (isMounted) setProjectsLoading(false)
      }
    }

    loadProjects()
    return () => {
      isMounted = false
    }
  }, [])

  useEffect(() => {
    if (!selectedProjectId) return
    let isMounted = true

    async function loadSchema() {
      setSchemaLoading(true)
      setAppError(null)
      resetRunState()
      try {
        const nextSchema = await getProjectSchema(selectedProjectId)
        if (!isMounted) return
        setSchema(nextSchema)
        setInputValues(initialInputValues(nextSchema))
        setObjectiveWeights(initialWeights(nextSchema))
        setFixedInputs(initialFixedInputs(nextSchema))
      } catch (error) {
        if (isMounted) {
          setSchema(null)
          setAppError(error instanceof Error ? error.message : 'Unable to load project schema')
        }
      } finally {
        if (isMounted) setSchemaLoading(false)
      }
    }

    loadSchema()
    return () => {
      isMounted = false
    }
  }, [selectedProjectId])

  function resetRunState() {
    setPrediction(null)
    setPredictWarnings([])
    setPredictError(null)
    setRecommendationRun(null)
    setRecommendWarnings([])
    setRecommendError(null)
  }

  async function handlePredictSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!schema) return

    setPredictLoading(true)
    setPredictError(null)
    setPredictWarnings([])
    try {
      const response = await predictExperiment(schema.project_id, toNumberMap(inputValues))
      setPrediction(response.predictions)
      setPredictWarnings(response.warnings)
    } catch (error) {
      setPrediction(null)
      setPredictError(error instanceof Error ? error.message : 'Prediction failed')
    } finally {
      setPredictLoading(false)
    }
  }

  async function handleRecommendSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!schema) return

    const requestedCandidates = clampInteger(nCandidates, 2000, 1, 100000)
    const requestedTableTopK = clampInteger(tableTopK, defaultTableTopK, 1, 25)
    const requestedVisualizationTopK = clampInteger(
      visualizationTopK,
      defaultVisualizationTopK,
      requestedTableTopK,
      maxVisualizationTopK,
    )
    const requestedTopK = Math.min(
      Math.max(requestedTableTopK, requestedVisualizationTopK),
      requestedCandidates,
      maxVisualizationTopK,
    )
    const weights = toNumberMap(objectiveWeights)
    const fixedInputValues = enabledFixedInputValues(fixedInputs)

    setRecommendLoading(true)
    setRecommendError(null)
    setRecommendWarnings([])
    try {
      const response = await recommendExperiments(schema.project_id, {
        objective_weights: weights,
        fixed_inputs: fixedInputValues,
        n_candidates: requestedCandidates,
        top_k: requestedTopK,
      })
      setRecommendationRun({
        projectId: schema.project_id,
        projectDisplayName: schema.display_name,
        nCandidates: requestedCandidates,
        tableTopK: requestedTableTopK,
        visualizationTopK: requestedVisualizationTopK,
        requestedTopK,
        objectiveWeights: weights,
        fixedInputs: fixedInputValues,
        recommendations: response.recommendations,
      })
      setRecommendWarnings(response.warnings)
      setActiveTab('recommendations')
    } catch (error) {
      setRecommendationRun(null)
      setRecommendError(error instanceof Error ? error.message : 'Recommendation failed')
    } finally {
      setRecommendLoading(false)
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId)

  return (
    <main className="min-h-screen overflow-hidden bg-[#eef0ea] text-slate-950">
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute -left-32 top-[-18rem] h-[34rem] w-[34rem] rounded-full bg-[#d4c3a3]/60 blur-3xl" />
        <div className="absolute right-[-12rem] top-40 h-[30rem] w-[30rem] rounded-full bg-[#6f8c7b]/25 blur-3xl" />
        <div className="absolute inset-x-0 bottom-0 h-72 bg-gradient-to-t from-[#dfe4d7] to-transparent" />
      </div>

      <div className="relative mx-auto flex max-w-7xl flex-col gap-8 px-5 py-8 sm:px-8 lg:px-10">
        <ProjectHeader
          projects={projects}
          selectedProjectId={selectedProjectId}
          selectedProject={selectedProject}
          schema={schema}
          projectsLoading={projectsLoading}
          activeTab={activeTab}
          onProjectChange={setSelectedProjectId}
          onTabChange={setActiveTab}
        />

        {appError && <Alert tone="error" title="Backend connection issue" messages={[appError]} />}

        {schemaLoading || projectsLoading ? (
          <div className="rounded-[2rem] border border-white/70 bg-white/70 p-8 text-slate-600 shadow-xl">
            Loading project schema...
          </div>
        ) : schema ? (
          <>
            {activeTab === 'batch' && (
              <div className="space-y-8">
                <section className="rounded-[2rem] border border-white/70 bg-white/85 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#60745c]">
                    Batch Explorer
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-slate-950">
                    Design-space scan with weighted KPI ranking
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                    Scan thousands of candidate configurations using the surrogate model and
                    weighted objectives before moving into sequential optimization.
                  </p>
                </section>

                <div className="grid gap-8 xl:grid-cols-[0.95fr_1.05fr]">
                  <PredictPanel
                    schema={schema}
                    inputValues={inputValues}
                    setInputValues={setInputValues}
                    prediction={prediction}
                    warnings={predictWarnings}
                    loading={predictLoading}
                    error={predictError}
                    onSubmit={handlePredictSubmit}
                  />

                  <RecommendPanel
                    schema={schema}
                    objectiveWeights={objectiveWeights}
                    setObjectiveWeights={setObjectiveWeights}
                    fixedInputs={fixedInputs}
                    setFixedInputs={setFixedInputs}
                    nCandidates={nCandidates}
                    setNCandidates={setNCandidates}
                    tableTopK={tableTopK}
                    setTableTopK={setTableTopK}
                    visualizationTopK={visualizationTopK}
                    setVisualizationTopK={setVisualizationTopK}
                    loading={recommendLoading}
                    error={recommendError}
                    warnings={recommendWarnings}
                    recommendationRun={recommendationRun}
                    onSubmit={handleRecommendSubmit}
                    onViewRecommendations={() => setActiveTab('recommendations')}
                  />
                </div>
              </div>
            )}

            {activeTab === 'recommendations' && (
              <RecommendationsPage
                schema={schema}
                recommendationRun={recommendationRun}
                onGoHome={() => setActiveTab('batch')}
              />
            )}

            {activeTab === 'visualizations' && (
              <VisualizationsPage
                schema={schema}
                recommendationRun={recommendationRun}
                inputValues={inputValues}
                onGoHome={() => setActiveTab('batch')}
              />
            )}

            {activeTab === 'optimization' && (
              <OptimizationLoopPage
                schema={schema}
                objectiveWeights={objectiveWeights}
                setObjectiveWeights={setObjectiveWeights}
              />
            )}
          </>
        ) : null}
      </div>
    </main>
  )
}

export default App
