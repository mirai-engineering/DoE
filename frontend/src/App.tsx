import { FormEvent, useEffect, useState } from 'react'
import { ProjectHeader } from './components/ProjectHeader'
import { Tabs } from './components/Tabs'
import { PredictPanel } from './components/PredictPanel'
import { RecommendPanel } from './components/RecommendPanel'
import { RecommendationsPage } from './components/RecommendationsPage'
import { VisualizationsPage } from './components/VisualizationsPage'
import { OptimizationLoopPage } from './components/bo/OptimizationLoopPage'
import { ModelQualityPage } from './components/ModelQualityPage'
import { BusinessImpactPage } from './components/BusinessImpactPage'
import { DesignStudioPage } from './components/DesignStudioPage'
import { DataIntakePage } from './components/DataIntakePage'
import { KnowledgeIntakePage } from './components/KnowledgeIntakePage'
import { DataScientistPage } from './components/DataScientistPage'
import { PreprocessingReviewPage } from './components/PreprocessingReviewPage'
import { Alert } from './components/ui'
import type { AccountStatus, ProjectSchema, ProjectSummary, WorkspaceSummary } from './lib/api'
import { getProjectSchema, getProjectsResponse, predictExperiment, recommendExperiments } from './lib/api'
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
  const [activeTab, setActiveTab] = useState<ActiveTab>('knowledge-intake')
  const [batchView, setBatchView] = useState<'configure' | 'results' | 'visuals'>('configure')
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([])
  const [account, setAccount] = useState<AccountStatus | null>(null)
  const [selectedProjectId, setSelectedProjectId] = useState('')
  const [schema, setSchema] = useState<ProjectSchema | null>(null)
  const [appError, setAppError] = useState<string | null>(null)
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [schemaLoading, setSchemaLoading] = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.localStorage.getItem('mirai.sidebarCollapsed') === 'true')

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
        const response = await getProjectsResponse()
        const projectList = response.projects
        if (!isMounted) return
        setProjects(projectList)
        setWorkspaces(response.workspaces)
        setAccount(response.account ?? null)
        const storedProjectId = window.localStorage.getItem('mirai.activeProjectId')
        const preferred = storedProjectId && projectList.some((project) => project.id === storedProjectId)
          ? storedProjectId
          : selectDefaultProject(projectList)?.id ?? ''
        setSelectedProjectId(preferred)
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
    window.localStorage.setItem('mirai.sidebarCollapsed', String(sidebarCollapsed))
  }, [sidebarCollapsed])

  useEffect(() => {
    if (!selectedProjectId) return
    let isMounted = true

    async function loadSchema() {
      setSchemaLoading(true)
      setSchema(null)
      setInputValues({})
      setObjectiveWeights({})
      setFixedInputs({})
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

  async function refreshProjectsAndSelect(projectId: string) {
    setProjectsLoading(true)
    setAppError(null)
    try {
      const response = await getProjectsResponse()
      const projectList = response.projects
      setProjects(projectList)
      setWorkspaces(response.workspaces)
      setAccount(response.account ?? null)
      setSelectedProjectId(projectId)
      window.localStorage.setItem('mirai.activeProjectId', projectId)
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to refresh projects')
    } finally {
      setProjectsLoading(false)
    }
  }

  function handleProjectChange(projectId: string) {
    setSchema(null)
    resetRunState()
    setSelectedProjectId(projectId)
    window.localStorage.setItem('mirai.activeProjectId', projectId)
  }

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
      setActiveTab('batch')
      setBatchView('results')
    } catch (error) {
      setRecommendationRun(null)
      setRecommendError(error instanceof Error ? error.message : 'Recommendation failed')
    } finally {
      setRecommendLoading(false)
    }
  }

  const selectedProject = projects.find((project) => project.id === selectedProjectId)

  return (
    <main className="mirai-auth-shell min-h-screen overflow-x-hidden bg-[#050914] text-[#F8FAFC]">
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(91,168,255,0.055),transparent_360px),linear-gradient(180deg,#08111F_0%,#050914_46%,#07101D_100%)]" />
        <div className="absolute inset-0 opacity-[0.055] constellation-grid" />
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-slate-400/30 to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-64 bg-gradient-to-t from-[#050914] to-transparent" />
      </div>

      <Tabs activeTab={activeTab} onTabChange={setActiveTab} collapsed={sidebarCollapsed} onCollapsedChange={setSidebarCollapsed} />

      <div className={`relative min-h-screen transition-[padding-left] duration-200 ${sidebarCollapsed ? 'lg:pl-[4.75rem]' : 'lg:pl-[15.75rem]'}`}>
        <div className="mx-auto min-w-0 max-w-[90rem] space-y-6 px-4 py-6 sm:px-6 lg:px-8 lg:py-7">
          <ProjectHeader
            projects={projects}
            selectedProjectId={selectedProjectId}
            selectedProject={selectedProject}
            schema={schema}
            workspaces={workspaces}
            projectsLoading={projectsLoading}
            onProjectChange={handleProjectChange}
            compact={activeTab === 'knowledge-intake' || activeTab === 'preprocessing-review' || activeTab === 'data-scientist'}
          />

          {appError && <Alert tone="error" title="Backend connection issue" messages={[appError]} />}

          {account && account.status !== 'active_single_workspace' && (
            <Alert
              tone="warning"
              title="Workspace setup required"
              messages={[account.message ?? 'Your account is active, but no client workspace has been assigned yet.']}
            />
          )}

          {projectsLoading || (schemaLoading && activeTab !== 'preprocessing-review') ? (
          <div className="border-y border-white/[0.08] py-5 text-slate-300">
            Loading project schema...
          </div>
        ) : schema || activeTab === 'preprocessing-review' ? (
          <>
            {activeTab === 'batch' && schema && (
              <div className="space-y-8">
                <section className="border-b border-slate-400/[0.10] pb-5">
                  <p className="text-sm font-medium text-[#74C7F5]">
                    Batch Search
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em] text-[#F6F4EA]">
                    Design-space scan with weighted KPI ranking
                  </h2>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-[#9BA8C0]">
                    Configure candidate scans, review ranked results, and inspect response-surface visuals in one workflow.
                  </p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    {[
                      { id: 'configure', label: 'Configure' },
                      { id: 'results', label: 'Results' },
                      { id: 'visuals', label: 'Visuals' },
                    ].map((view) => (
                      <button
                        key={view.id}
                        type="button"
                        onClick={() => setBatchView(view.id as 'configure' | 'results' | 'visuals')}
                        className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
                          batchView === view.id ? 'bg-[#2F6BFF] text-white' : 'text-slate-300 hover:bg-white/[0.035] hover:text-white'
                        }`}
                      >
                        {view.label}
                      </button>
                    ))}
                  </div>
                </section>

                {batchView === 'configure' && (
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
                      onViewRecommendations={() => setBatchView('results')}
                    />
                  </div>
                )}

                {batchView === 'results' && (
                  <RecommendationsPage
                    schema={schema}
                    recommendationRun={recommendationRun}
                    onGoHome={() => setBatchView('configure')}
                  />
                )}

                {batchView === 'visuals' && (
                  <VisualizationsPage
                    schema={schema}
                    recommendationRun={recommendationRun}
                    inputValues={inputValues}
                    onGoHome={() => setBatchView('configure')}
                  />
                )}
              </div>
            )}

            {activeTab === 'knowledge-intake' && schema && <KnowledgeIntakePage schema={schema} onGoToDataIntake={() => setActiveTab('data-intake')} />}

            {activeTab === 'data-intake' && <DataIntakePage schema={schema} projects={projects} workspaces={workspaces} account={account} onSessionCreated={(session) => refreshProjectsAndSelect(session.project_id)} onReviewPreprocessing={() => setActiveTab('preprocessing-review')} />}

            {activeTab === 'preprocessing-review' && <PreprocessingReviewPage schema={schema} onOpenModelQuality={() => setActiveTab('model-quality')} />}

            {activeTab === 'design-studio' && schema && <DesignStudioPage schema={schema} />}

            {activeTab === 'optimization' && schema && (
              <OptimizationLoopPage
                schema={schema}
                objectiveWeights={objectiveWeights}
                setObjectiveWeights={setObjectiveWeights}
              />
            )}

            {activeTab === 'impact' && schema && <BusinessImpactPage schema={schema} />}

            {activeTab === 'model-quality' && schema && <ModelQualityPage schema={schema} />}

            {activeTab === 'data-scientist' && schema && <DataScientistPage schema={schema} />}
          </>
          ) : activeTab === 'data-intake' ? (
            <DataIntakePage schema={null} projects={projects} workspaces={workspaces} account={account} onSessionCreated={(session) => refreshProjectsAndSelect(session.project_id)} onReviewPreprocessing={() => setActiveTab('preprocessing-review')} />
          ) : null}
        </div>
      </div>
    </main>
  )
}

export default App
