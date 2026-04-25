import { FormEvent, useEffect, useState } from 'react'
import {
  ProjectSchema,
  ProjectSummary,
  Recommendation,
  predictExperiment,
  recommendExperiments,
  getProjectSchema,
  getProjects,
  type PredictionMap,
} from './lib/api'

const preferredProjectId = 'pem_fuel_cell_demo'

const defaultObjectiveWeights: Record<string, number> = {
  bol_current_density: 0.35,
  eol_current_density: 0.35,
  durability_score: 0.2,
  ecsa_loss: -0.1,
  cost_score: -0.1,
}

function midpoint(minimum: number, maximum: number) {
  return Number(((minimum + maximum) / 2).toPrecision(6))
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: Math.abs(value) >= 100 ? 1 : 4,
  }).format(value)
}

function initialInputValues(schema: ProjectSchema) {
  return Object.fromEntries(
    schema.inputs.map((input) => [input.name, String(midpoint(input.min, input.max))]),
  )
}

function initialWeights(schema: ProjectSchema) {
  return Object.fromEntries(
    schema.outputs.map((output) => {
      const fallback = output.direction === 'minimize' ? -0.1 : 0.2
      return [output.name, String(defaultObjectiveWeights[output.name] ?? fallback)]
    }),
  )
}

function initialFixedInputs(schema: ProjectSchema) {
  return Object.fromEntries(
    schema.inputs.map((input) => {
      const enabled = input.name === 'operating_rh' || input.name === 'operating_voltage'
      return [input.name, { enabled, value: String(midpoint(input.min, input.max)) }]
    }),
  )
}

function toNumberMap(values: Record<string, string>) {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [key, Number(value)]),
  )
}

function App() {
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
  const [fixedInputs, setFixedInputs] = useState<Record<string, { enabled: boolean; value: string }>>({})
  const [nCandidates, setNCandidates] = useState('2000')
  const [topK, setTopK] = useState('5')
  const [recommendations, setRecommendations] = useState<Recommendation[]>([])
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
        const preferredProject = projectList.find((project) => project.id === preferredProjectId)
        setSelectedProjectId((preferredProject ?? projectList[0])?.id ?? '')
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
      setPrediction(null)
      setRecommendations([])
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

    const enabledFixedInputs = Object.fromEntries(
      Object.entries(fixedInputs)
        .filter(([, config]) => config.enabled)
        .map(([key, config]) => [key, Number(config.value)]),
    )

    setRecommendLoading(true)
    setRecommendError(null)
    try {
      const response = await recommendExperiments(schema.project_id, {
        objective_weights: toNumberMap(objectiveWeights),
        fixed_inputs: enabledFixedInputs,
        n_candidates: Number(nCandidates),
        top_k: Number(topK),
      })
      setRecommendations(response.recommendations)
    } catch (error) {
      setRecommendations([])
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
        <section className="overflow-hidden rounded-[2rem] border border-white/70 bg-[#f8f6ef]/90 shadow-2xl shadow-slate-900/10 backdrop-blur">
          <div className="grid gap-8 p-6 md:grid-cols-[1.35fr_0.65fr] md:p-8">
            <div>
              <div className="mb-6 inline-flex items-center gap-3 rounded-full border border-slate-900/10 bg-white/70 px-4 py-2 text-xs font-semibold uppercase tracking-[0.24em] text-slate-600">
                Surrogate model console
              </div>
              <h1 className="max-w-3xl text-5xl font-semibold tracking-[-0.06em] text-slate-950 sm:text-6xl">
                Mirai DoE Engine
              </h1>
              <p className="mt-4 max-w-2xl text-lg leading-8 text-slate-600">
                Predict experiment outcomes and recommend the next best candidates.
              </p>
            </div>

            <div className="rounded-3xl border border-slate-900/10 bg-white/75 p-5 shadow-inner shadow-white">
              <label htmlFor="project" className="text-sm font-semibold text-slate-700">
                Project
              </label>
              <select
                id="project"
                value={selectedProjectId}
                onChange={(event) => setSelectedProjectId(event.target.value)}
                disabled={projectsLoading || projects.length === 0}
                className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-950 outline-none transition focus:border-[#60745c] focus:ring-4 focus:ring-[#60745c]/20"
              >
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.display_name}
                  </option>
                ))}
              </select>

              <div className="mt-5 grid grid-cols-2 gap-3 text-sm">
                <Metadata label="Project ID" value={selectedProject?.id ?? 'Loading'} />
                <Metadata label="Version" value={schema?.schema_version ?? '-'} />
                <Metadata label="Inputs" value={schema ? String(schema.inputs.length) : '-'} />
                <Metadata label="Outputs" value={schema ? String(schema.outputs.length) : '-'} />
              </div>
              {schema?.description && (
                <p className="mt-4 text-sm leading-6 text-slate-600">{schema.description}</p>
              )}
            </div>
          </div>
        </section>

        {appError && <Alert tone="error" title="Backend connection issue" messages={[appError]} />}

        {schemaLoading || projectsLoading ? (
          <div className="rounded-[2rem] border border-white/70 bg-white/70 p-8 text-slate-600 shadow-xl">
            Loading project schema...
          </div>
        ) : schema ? (
          <div className="grid gap-8 xl:grid-cols-[0.95fr_1.05fr]">
            <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
              <PanelHeader
                eyebrow="Single experiment"
                title="Predict outcomes"
                description="Set one candidate formulation or operating point and score the expected KPIs."
              />

              <form className="mt-6 space-y-5" onSubmit={handlePredictSubmit}>
                <div className="grid gap-4 sm:grid-cols-2">
                  {schema.inputs.map((input) => (
                    <NumberField
                      key={input.name}
                      id={`predict-${input.name}`}
                      label={input.label}
                      unit={input.unit}
                      min={input.min}
                      max={input.max}
                      value={inputValues[input.name] ?? ''}
                      onChange={(value) =>
                        setInputValues((current) => ({ ...current, [input.name]: value }))
                      }
                    />
                  ))}
                </div>

                <button
                  type="submit"
                  disabled={predictLoading}
                  className="w-full rounded-2xl bg-slate-950 px-5 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-white shadow-lg shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-[#263329] disabled:cursor-not-allowed disabled:brightness-75"
                >
                  {predictLoading ? 'Predicting...' : 'Predict experiment'}
                </button>
              </form>

              {predictError && (
                <div className="mt-5">
                  <Alert tone="error" title="Prediction failed" messages={[predictError]} />
                </div>
              )}

              {predictWarnings.length > 0 && (
                <div className="mt-5">
                  <Alert tone="warning" title="Validation warnings" messages={predictWarnings} />
                </div>
              )}

              {prediction && (
                <div className="mt-6">
                  <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
                    Predicted KPIs
                  </h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {schema.outputs.map((output) => (
                      <KpiCard
                        key={output.name}
                        label={output.label}
                        value={prediction[output.name]}
                        unit={output.unit}
                        direction={output.direction}
                      />
                    ))}
                  </div>
                </div>
              )}
            </section>

            <section className="rounded-[2rem] border border-white/70 bg-[#18211d] p-6 text-white shadow-xl shadow-slate-900/20">
              <PanelHeader
                eyebrow="Candidate search"
                title="Recommend experiments"
                description="Sample the project design space, apply fixed variables, and rank candidates by weighted KPI score."
                dark
              />

              <form className="mt-6 space-y-6" onSubmit={handleRecommendSubmit}>
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-white/60">
                    Objective weights
                  </h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {schema.outputs.map((output) => (
                      <WeightField
                        key={output.name}
                        id={`weight-${output.name}`}
                        label={output.label}
                        direction={output.direction}
                        value={objectiveWeights[output.name] ?? ''}
                        onChange={(value) =>
                          setObjectiveWeights((current) => ({ ...current, [output.name]: value }))
                        }
                      />
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-[0.18em] text-white/60">
                    Fixed inputs
                  </h3>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {schema.inputs.map((input) => {
                      const config = fixedInputs[input.name] ?? { enabled: false, value: '' }
                      return (
                        <FixedInputField
                          key={input.name}
                          input={input}
                          enabled={config.enabled}
                          value={config.value}
                          onEnabledChange={(enabled) =>
                            setFixedInputs((current) => ({
                              ...current,
                              [input.name]: { ...config, enabled },
                            }))
                          }
                          onValueChange={(value) =>
                            setFixedInputs((current) => ({
                              ...current,
                              [input.name]: { ...config, value },
                            }))
                          }
                        />
                      )
                    })}
                  </div>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <NumberField
                    id="n-candidates"
                    label="Candidates sampled"
                    unit="rows"
                    min={1}
                    max={100000}
                    value={nCandidates}
                    onChange={setNCandidates}
                    dark
                  />
                  <NumberField
                    id="top-k"
                    label="Recommendations"
                    unit="top k"
                    min={1}
                    max={100}
                    value={topK}
                    onChange={setTopK}
                    dark
                  />
                </div>

                <button
                  type="submit"
                  disabled={recommendLoading}
                  className="w-full rounded-2xl bg-[#d8c49a] px-5 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-slate-950 shadow-lg shadow-black/20 transition hover:-translate-y-0.5 hover:bg-[#ead7ad] disabled:cursor-not-allowed disabled:brightness-75"
                >
                  {recommendLoading ? 'Searching...' : 'Recommend candidates'}
                </button>
              </form>

              {recommendError && (
                <div className="mt-5">
                  <Alert tone="error" title="Recommendation failed" messages={[recommendError]} />
                </div>
              )}
            </section>
          </div>
        ) : null}

        {schema && recommendations.length > 0 && (
          <section className="rounded-[2rem] border border-white/70 bg-white/90 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
            <PanelHeader
              eyebrow="Ranked design points"
              title="Recommended experiments"
              description="Scores are normalized across the sampled candidates for the current objective weights."
            />
            <div className="mt-6 overflow-x-auto rounded-3xl border border-slate-200 bg-white">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-950 text-white">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold">Rank</th>
                    <th className="px-4 py-3 text-left font-semibold">Score</th>
                    {schema.inputs.map((input) => (
                      <th key={input.name} className="px-4 py-3 text-left font-semibold">
                        {input.label}
                      </th>
                    ))}
                    {schema.outputs.map((output) => (
                      <th key={output.name} className="px-4 py-3 text-left font-semibold">
                        {output.label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {recommendations.map((candidate, index) => (
                    <tr key={`${candidate.score}-${index}`} className="hover:bg-[#f7f5ed]">
                      <td className="px-4 py-3 font-semibold text-slate-950">{index + 1}</td>
                      <td className="px-4 py-3 font-semibold text-[#526949]">
                        {formatNumber(candidate.score)}
                      </td>
                      {schema.inputs.map((input) => (
                        <td key={input.name} className="whitespace-nowrap px-4 py-3 text-slate-700">
                          {formatNumber(candidate.inputs[input.name])}
                          <span className="ml-1 text-slate-400">{input.unit}</span>
                        </td>
                      ))}
                      {schema.outputs.map((output) => (
                        <td key={output.name} className="whitespace-nowrap px-4 py-3 text-slate-700">
                          {formatNumber(candidate.predictions[output.name])}
                          <span className="ml-1 text-slate-400">{output.unit}</span>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </main>
  )
}

function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-[#f8f6ef] p-3">
      <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-slate-400">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-semibold text-slate-800">{value}</div>
    </div>
  )
}

function PanelHeader({
  eyebrow,
  title,
  description,
  dark = false,
}: {
  eyebrow: string
  title: string
  description: string
  dark?: boolean
}) {
  return (
    <div>
      <p
        className={`text-xs font-semibold uppercase tracking-[0.22em] ${
          dark ? 'text-[#d8c49a]' : 'text-[#60745c]'
        }`}
      >
        {eyebrow}
      </p>
      <h2 className={`mt-2 text-2xl font-semibold tracking-[-0.04em] ${dark ? 'text-white' : 'text-slate-950'}`}>
        {title}
      </h2>
      <p className={`mt-2 text-sm leading-6 ${dark ? 'text-white/70' : 'text-slate-600'}`}>
        {description}
      </p>
    </div>
  )
}

function NumberField({
  id,
  label,
  unit,
  min,
  max,
  value,
  onChange,
  dark = false,
}: {
  id: string
  label: string
  unit: string
  min: number
  max: number
  value: string
  onChange: (value: string) => void
  dark?: boolean
}) {
  return (
    <label htmlFor={id} className="block">
      <span className={`flex items-center justify-between gap-3 text-sm font-semibold ${dark ? 'text-white/90' : 'text-slate-700'}`}>
        {label}
        <span className={`text-xs font-medium ${dark ? 'text-white/50' : 'text-slate-400'}`}>{unit}</span>
      </span>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        step="any"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={`mt-2 w-full rounded-2xl border px-4 py-3 text-sm font-medium outline-none transition focus:ring-4 ${
          dark
            ? 'border-white/10 bg-white/10 text-white focus:border-[#d8c49a] focus:ring-[#d8c49a]/20'
            : 'border-slate-200 bg-white text-slate-950 focus:border-[#60745c] focus:ring-[#60745c]/20'
        }`}
      />
      <span className={`mt-1 block text-xs ${dark ? 'text-white/40' : 'text-slate-400'}`}>
        Range {formatNumber(min)} to {formatNumber(max)}
      </span>
    </label>
  )
}

function WeightField({
  id,
  label,
  direction,
  value,
  onChange,
}: {
  id: string
  label: string
  direction: 'maximize' | 'minimize'
  value: string
  onChange: (value: string) => void
}) {
  return (
    <label htmlFor={id} className="block rounded-2xl border border-white/10 bg-white/5 p-3">
      <span className="flex items-center justify-between gap-3 text-sm font-semibold text-white/90">
        {label}
        <span className="text-xs font-medium uppercase tracking-[0.16em] text-white/40">{direction}</span>
      </span>
      <input
        id={id}
        type="number"
        step="0.01"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2 text-sm font-medium text-white outline-none transition focus:border-[#d8c49a] focus:ring-4 focus:ring-[#d8c49a]/20"
      />
    </label>
  )
}

function FixedInputField({
  input,
  enabled,
  value,
  onEnabledChange,
  onValueChange,
}: {
  input: ProjectSchema['inputs'][number]
  enabled: boolean
  value: string
  onEnabledChange: (enabled: boolean) => void
  onValueChange: (value: string) => void
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 p-3">
      <label className="flex items-center gap-3 text-sm font-semibold text-white/90">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
          className="h-4 w-4 rounded border-white/20 bg-slate-950 accent-[#d8c49a]"
        />
        {input.label}
      </label>
      <input
        type="number"
        min={input.min}
        max={input.max}
        step="any"
        value={value}
        disabled={!enabled}
        onChange={(event) => onValueChange(event.target.value)}
        className="mt-2 w-full rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2 text-sm font-medium text-white outline-none transition focus:border-[#d8c49a] focus:ring-4 focus:ring-[#d8c49a]/20 disabled:brightness-50"
      />
      <span className="mt-1 block text-xs text-white/40">
        {input.unit} | {formatNumber(input.min)} to {formatNumber(input.max)}
      </span>
    </div>
  )
}

function KpiCard({
  label,
  value,
  unit,
  direction,
}: {
  label: string
  value: number
  unit: string
  direction: 'maximize' | 'minimize'
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-[#fbfaf5] p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-700">{label}</p>
        <span className="rounded-full bg-[#e8eadf] px-2 py-1 text-[0.65rem] font-bold uppercase tracking-[0.16em] text-[#526949]">
          {direction}
        </span>
      </div>
      <div className="mt-4 flex items-baseline gap-2">
        <span className="text-3xl font-semibold tracking-[-0.05em] text-slate-950">
          {formatNumber(value)}
        </span>
        <span className="text-sm text-slate-400">{unit}</span>
      </div>
    </div>
  )
}

function Alert({
  title,
  messages,
  tone,
}: {
  title: string
  messages: string[]
  tone: 'error' | 'warning'
}) {
  const className =
    tone === 'error'
      ? 'border-red-200 bg-red-50 text-red-950'
      : 'border-amber-200 bg-amber-50 text-amber-950'

  return (
    <div className={`rounded-2xl border p-4 ${className}`}>
      <p className="font-semibold">{title}</p>
      <ul className="mt-2 space-y-1 text-sm">
        {messages.map((message) => (
          <li key={message}>{message}</li>
        ))}
      </ul>
    </div>
  )
}

export default App
