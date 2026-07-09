import type { Data, Layout } from 'plotly.js'
import type { Dispatch, SetStateAction } from 'react'
import { useEffect, useMemo, useState } from 'react'
import type {
  BOAcquisitionFunction,
  BOExplorationLevel,
  BOFantasyStep,
  BOInputConstraint,
  BOReviewReason,
  BOStateResponse,
  LoggedExperiment,
  ProjectSchema,
} from '../../lib/api'
import {
  getBOState,
  initializeBOReplay,
  revealBOReplayResult,
  reviewBOExperiment,
  runBOFantasyRollout,
  saveBOConfig,
  suggestBOExperiment,
} from '../../lib/api'
import { formatNumber, toNumberMap } from '../../lib/doeUtils'
import { Plot } from '../../lib/plotly'
import { transparentDarkPlotLayout } from '../../lib/plotlyTheme'
import { Alert, Metadata, PanelHeader, WeightField } from '../ui'

type ConstraintDraft = Record<
  string,
  {
    min: string
    max: string
    fixed: string
    fixedEnabled: boolean
  }
>

type BOView = 'configure' | 'review' | 'diagnostics' | 'history'

const boViews: Array<{ id: BOView; label: string; description: string }> = [
  { id: 'configure', label: 'Configure', description: 'Weights, policy, and constraints' },
  { id: 'review', label: 'Review', description: 'Current best and next experiment' },
  { id: 'diagnostics', label: 'Diagnostics', description: 'Iteration and acquisition evidence' },
  { id: 'history', label: 'History', description: 'Replay trajectory and logged tests' },
]

const explorationOptions: Array<{ value: BOExplorationLevel; label: string }> = [
  { value: 'conservative', label: 'Conservative' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'exploratory', label: 'Exploratory' },
]

const acquisitionOptions: Array<{ value: BOAcquisitionFunction; label: string }> = [
  { value: 'ei', label: 'Expected Improvement' },
  { value: 'ucb', label: 'Upper Confidence Bound' },
]

const rejectionReasons: Array<{ value: BOReviewReason; label: string }> = [
  { value: 'infeasible', label: 'Infeasible' },
  { value: 'unsafe', label: 'Unsafe' },
  { value: 'too_expensive', label: 'Too expensive' },
  { value: 'outside_protocol', label: 'Outside protocol' },
  { value: 'chemically_implausible', label: 'Chemically implausible' },
  { value: 'duplicate', label: 'Duplicate' },
  { value: 'other', label: 'Other' },
]

function initialConstraintDraft(schema: ProjectSchema): ConstraintDraft {
  return Object.fromEntries(
    schema.inputs.map((input) => [
      input.name,
      {
        min: '',
        max: '',
        fixed: '',
        fixedEnabled: false,
      },
    ]),
  )
}

function buildInputConstraints(draft: ConstraintDraft, schema: ProjectSchema) {
  const constraints: Record<string, BOInputConstraint> = {}
  schema.inputs.forEach((input) => {
    const row = draft[input.name]
    if (!row) return
    const constraint: BOInputConstraint = {}
    if (row.min.trim() !== '') constraint.min = Number(row.min)
    if (row.max.trim() !== '') constraint.max = Number(row.max)
    if (row.fixedEnabled && row.fixed.trim() !== '') constraint.fixed = Number(row.fixed)
    if (Object.keys(constraint).length > 0) constraints[input.name] = constraint
  })
  return constraints
}

function latestLoopExperiment(state: BOStateResponse | null) {
  if (!state) return null
  return (
    [...state.history]
      .reverse()
      .find((experiment) => experiment.source === 'bo_suggested' || experiment.source === 'replay_revealed') ??
    null
  )
}

function numberMetric(record: Record<string, unknown> | null | undefined, key: string) {
  const value = record?.[key]
  return typeof value === 'number' ? value : undefined
}

function objectiveMetric(experiment: LoggedExperiment | null, key: string) {
  const value = experiment?.objective?.[key]
  return typeof value === 'number' ? value : undefined
}

function metadataText(experiment: LoggedExperiment | null, key: string) {
  const value = experiment?.metadata[key]
  return typeof value === 'string' ? value : undefined
}

function statusClass(status: LoggedExperiment['status']) {
  const classes: Record<LoggedExperiment['status'], string> = {
    suggested: 'bg-blue-50 text-blue-900 border-blue-200',
    accepted: 'bg-[#0D1B2D] text-[#BDEAFF] border-[#74C7F5]/30',
    rejected: 'bg-red-50 text-red-900 border-red-200',
    skipped: 'bg-slate-100 text-slate-300 border-slate-200',
    tested: 'bg-purple-50 text-purple-900 border-purple-200',
    observed: 'bg-[#0D1B2D] text-[#BDEAFF] border-[#74C7F5]',
  }
  return classes[status]
}

export function OptimizationLoopPage({
  schema,
  objectiveWeights,
  setObjectiveWeights,
}: {
  schema: ProjectSchema
  objectiveWeights: Record<string, string>
  setObjectiveWeights: Dispatch<SetStateAction<Record<string, string>>>
}) {
  const [state, setState] = useState<BOStateResponse | null>(null)
  const [stateLoading, setStateLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [explorationLevel, setExplorationLevel] = useState<BOExplorationLevel>('balanced')
  const [acquisitionFunction, setAcquisitionFunction] = useState<BOAcquisitionFunction>('ei')
  const [constraints, setConstraints] = useState<ConstraintDraft>(() => initialConstraintDraft(schema))
  const [rejectingExperimentId, setRejectingExperimentId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState<BOReviewReason>('infeasible')
  const [rejectNotes, setRejectNotes] = useState('')
  const [fantasyTrajectory, setFantasyTrajectory] = useState<BOFantasyStep[]>([])
  const [boView, setBoView] = useState<BOView>('configure')

  useEffect(() => {
    setConstraints(initialConstraintDraft(schema))
    setExplorationLevel('balanced')
    setAcquisitionFunction('ei')
  }, [schema])

  useEffect(() => {
    let isMounted = true
    async function loadState() {
      setStateLoading(true)
      setError(null)
      try {
        const response = await getBOState(schema.project_id)
        if (!isMounted) return
        setState(response)
        setExplorationLevel(response.config.exploration_level ?? 'balanced')
        setAcquisitionFunction(response.config.acquisition_function ?? 'ei')
      } catch (loadError) {
        if (isMounted) {
          setError(loadError instanceof Error ? loadError.message : 'Unable to load BO state')
        }
      } finally {
        if (isMounted) setStateLoading(false)
      }
    }

    loadState()
    return () => {
      isMounted = false
    }
  }, [schema.project_id])

  const numericWeights = useMemo(() => toNumberMap(objectiveWeights), [objectiveWeights])
  const activeConstraints = useMemo(
    () => buildInputConstraints(constraints, schema),
    [constraints, schema],
  )
  const activeExperiment = state?.latest_suggestion ?? latestLoopExperiment(state)
  const canReveal = activeExperiment?.status === 'accepted'

  async function runAction(label: string, action: () => Promise<BOStateResponse>) {
    setActionLoading(label)
    setError(null)
    setNotice(null)
    setFantasyTrajectory([])
    try {
      const nextState = await action()
      setState(nextState)
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Optimization loop action failed')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleFantasyRollout() {
    setActionLoading('fantasy')
    setError(null)
    setNotice(null)
    try {
      const response = await runBOFantasyRollout(schema.project_id, {
        steps: 5,
        config: {
          objective_weights: numericWeights,
          strategy: explorationLevel,
          exploration_level: explorationLevel,
          acquisition_function: acquisitionFunction,
          input_constraints: activeConstraints,
          n_suggestions: 1,
          random_seed: 42,
          replay_mode: true,
        },
      })
      setFantasyTrajectory(response.fantasy_trajectory)
      setNotice('5-step MLP fantasy rollout generated for planning only. No fantasy points were logged as observed.')
    } catch (actionError) {
      setError(actionError instanceof Error ? actionError.message : 'Fantasy rollout failed')
    } finally {
      setActionLoading(null)
    }
  }

  async function handleInitialize(reset: boolean) {
    await runAction(reset ? 'reset' : 'initialize', async () => {
      const response = await initializeBOReplay(schema.project_id, {
        reset,
        n_initial: 10,
        selection: 'diverse',
      })
      setNotice('Replay loop initialized from held-out historical rows.')
      return response
    })
  }

  async function handleSaveConfig() {
    await runAction('config', async () => {
      const response = await saveBOConfig(schema.project_id, {
        objective_weights: numericWeights,
        exploration_level: explorationLevel,
        acquisition_function: acquisitionFunction,
        input_constraints: activeConstraints,
        n_suggestions: 1,
        replay_mode: true,
      })
      setNotice('Future BO suggestions will respect the updated constraints.')
      return response
    })
  }

  async function handleSuggest() {
    await runAction('suggest', async () => {
      const response = await suggestBOExperiment(schema.project_id, {
        objective_weights: numericWeights,
        strategy: explorationLevel,
        exploration_level: explorationLevel,
        acquisition_function: acquisitionFunction,
        input_constraints: activeConstraints,
        n_suggestions: 1,
        random_seed: 42,
        replay_mode: true,
      })
      setNotice('Next experiment suggested and logged for scientist review.')
      return response.state
    })
  }

  async function handleAccept(experimentId: string) {
    await runAction('accept', async () => {
      const response = await reviewBOExperiment(schema.project_id, experimentId, {
        decision: 'accepted',
      })
      setNotice('Suggestion accepted. Replay result can now be revealed.')
      return response.state
    })
  }

  async function handleReject() {
    if (!rejectingExperimentId) return
    await runAction('reject', async () => {
      const response = await reviewBOExperiment(schema.project_id, rejectingExperimentId, {
        decision: 'rejected',
        reason: rejectReason,
        notes: rejectNotes || null,
      })
      setRejectingExperimentId(null)
      setRejectNotes('')
      setNotice('Suggestion rejected and kept out of the replay reveal step.')
      return response.state
    })
  }

  async function handleSkip(experimentId: string) {
    await runAction('skip', async () => {
      const response = await reviewBOExperiment(schema.project_id, experimentId, {
        decision: 'skipped',
      })
      setNotice('Suggestion skipped without revealing a replay result.')
      return response.state
    })
  }

  async function handleReveal(experimentId: string) {
    await runAction('reveal', async () => {
      const response = await revealBOReplayResult(schema.project_id, experimentId)
      setNotice('Replay result revealed from the hidden historical pool.')
      return response.state
    })
  }

  return (
    <div className="space-y-8">
      <section className="border-y border-slate-400/[0.10] py-6">
        <PanelHeader
          eyebrow="Explore & Exploit Tests"
          title="Choose the next test with measured feedback"
          description="Balance exploring uncertain regions with exploiting designs the model already believes are strong. This replay workflow simulates sequential learning from completed tests."
        />
        <div className="mt-6 grid gap-3 md:grid-cols-4">
          <Metadata label="Observed" value={formatNumber(state?.observed_count)} />
          <Metadata label="Open suggestions" value={formatNumber(state?.suggested_count)} />
          <Metadata label="Rejected" value={formatNumber(state?.rejected_count)} />
          <Metadata label="Learning mode" value="Historical replay" />
        </div>
      </section>

      {error && <Alert tone="error" title="Optimization loop issue" messages={[error]} />}
      {notice && (
        <div className="rounded-lg border border-[#74C7F5]/30 bg-[#0D1B2D] p-4 text-sm font-semibold text-[#BDEAFF]">
          {notice}
        </div>
      )}

      <nav className="border-b border-slate-400/[0.10] pb-2" aria-label="Explore and Exploit workbench sections">
        <div className="grid gap-2 md:grid-cols-4">
          {boViews.map((view) => {
            const active = boView === view.id
            return (
              <button
                key={view.id}
                type="button"
                onClick={() => setBoView(view.id)}
                className={`rounded-md border px-4 py-3 text-left transition ${active ? 'border-transparent bg-[#2F6BFF] text-white' : 'border-transparent text-slate-300 hover:bg-white/[0.035] hover:text-white'}`}
                aria-pressed={active}
              >
                <span className="block text-sm font-semibold">{view.label}</span>
                <span className="mt-1 block text-xs text-slate-400">{view.description}</span>
              </button>
            )
          })}
        </div>
      </nav>

      {boView === 'configure' && (
        <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
          <SetupPanel
            schema={schema}
            objectiveWeights={objectiveWeights}
            setObjectiveWeights={setObjectiveWeights}
            explorationLevel={explorationLevel}
            setExplorationLevel={setExplorationLevel}
            acquisitionFunction={acquisitionFunction}
            setAcquisitionFunction={setAcquisitionFunction}
            onInitialize={() => handleInitialize(false)}
            onReset={() => handleInitialize(true)}
            onSuggest={handleSuggest}
            onFantasyRollout={handleFantasyRollout}
            onSaveConfig={handleSaveConfig}
            loading={stateLoading || actionLoading !== null}
            actionLoading={actionLoading}
          />
          <ConstraintsPanel schema={schema} constraints={constraints} setConstraints={setConstraints} />
        </div>
      )}

      {boView === 'review' && (
        <div className="grid gap-6 xl:grid-cols-2">
          <CurrentBestCard schema={schema} state={state} />
          <NextSuggestionCard
            schema={schema}
            experiment={activeExperiment}
            canReveal={canReveal}
            loading={actionLoading !== null}
            onAccept={handleAccept}
            onReject={(experimentId) => setRejectingExperimentId(experimentId)}
            onSkip={handleSkip}
            onReveal={handleReveal}
          />
        </div>
      )}

      {boView === 'diagnostics' && (
        <div className="grid gap-6 xl:grid-cols-2">
          <ObjectiveIterationChart state={state} fantasyTrajectory={fantasyTrajectory} />
          <AcquisitionChart state={state} />
          <div className="xl:col-span-2">
            <PredictedObservedChart schema={schema} state={state} />
          </div>
        </div>
      )}

      {boView === 'history' && (
        <div className="space-y-6">
          <FantasyRolloutPanel schema={schema} trajectory={fantasyTrajectory} />
          <HistoryTable schema={schema} state={state} />
        </div>
      )}

      {rejectingExperimentId && (
        <ScientistReviewDialog
          reason={rejectReason}
          notes={rejectNotes}
          setReason={setRejectReason}
          setNotes={setRejectNotes}
          onCancel={() => setRejectingExperimentId(null)}
          onSave={handleReject}
          loading={actionLoading === 'reject'}
        />
      )}
    </div>
  )
}

function SetupPanel({
  schema,
  objectiveWeights,
  setObjectiveWeights,
  explorationLevel,
  setExplorationLevel,
  acquisitionFunction,
  setAcquisitionFunction,
  onInitialize,
  onReset,
  onSuggest,
  onFantasyRollout,
  onSaveConfig,
  loading,
  actionLoading,
}: {
  schema: ProjectSchema
  objectiveWeights: Record<string, string>
  setObjectiveWeights: Dispatch<SetStateAction<Record<string, string>>>
  explorationLevel: BOExplorationLevel
  setExplorationLevel: (value: BOExplorationLevel) => void
  acquisitionFunction: BOAcquisitionFunction
  setAcquisitionFunction: (value: BOAcquisitionFunction) => void
  onInitialize: () => void
  onReset: () => void
  onSuggest: () => void
  onFantasyRollout: () => void
  onSaveConfig: () => void
  loading: boolean
  actionLoading: string | null
}) {
  return (
    <section className="border-y border-slate-400/[0.10] py-6 text-white">
      <PanelHeader
        eyebrow="Setup"
        title="Replay-backed BO run"
        description="Historical replay reveals hidden measurements only after a suggested experiment is accepted."
        dark
      />

      <div className="mt-6 space-y-6">
        <div>
          <h3 className="text-sm font-semibold tracking-normal text-white/60">
            Objective weights
          </h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            {schema.outputs.map((output) => (
              <WeightField
                key={output.name}
                id={`bo-weight-${output.name}`}
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

        <div className="grid gap-3 sm:grid-cols-2">
          <label htmlFor="bo-exploration" className="block">
            <span className="text-sm font-semibold text-white/90">Exploration mode</span>
            <select
              id="bo-exploration"
              value={explorationLevel}
              onChange={(event) => setExplorationLevel(event.target.value as BOExplorationLevel)}
              className="mt-2 w-full rounded-lg border border-white/10 bg-white/10 px-4 py-3 text-sm font-medium text-white outline-none transition focus:border-[#74C7F5] focus:ring-4 focus:ring-[#74C7F5]/20"
            >
              {explorationOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label htmlFor="bo-acquisition" className="block">
            <span className="text-sm font-semibold text-white/90">Acquisition</span>
            <select
              id="bo-acquisition"
              value={acquisitionFunction}
              onChange={(event) => setAcquisitionFunction(event.target.value as BOAcquisitionFunction)}
              className="mt-2 w-full rounded-lg border border-white/10 bg-white/10 px-4 py-3 text-sm font-medium text-white outline-none transition focus:border-[#74C7F5] focus:ring-4 focus:ring-[#74C7F5]/20"
            >
              {acquisitionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="rounded-lg border border-[#74C7F5]/25 bg-[#0D1B2D] p-4 text-sm leading-6 text-[#BDEAFF]">
          The optimizer fits only observed replay results. MLP predictions are displayed for
          comparison and are not fed back as lab measurements.
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={onInitialize}
            disabled={loading}
            className="rounded-lg bg-white/10 px-4 py-3 text-sm font-semibold tracking-normal text-white transition hover:bg-white/20 disabled:cursor-not-allowed disabled:brightness-75"
          >
            {actionLoading === 'initialize' ? 'Initializing...' : 'Initialize Replay'}
          </button>
          <button
            type="button"
            onClick={onReset}
            disabled={loading}
            className="rounded-lg px-4 py-3 text-sm font-semibold tracking-normal text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:brightness-75"
          >
            {actionLoading === 'reset' ? 'Resetting...' : 'Reset Loop'}
          </button>
          <button
            type="button"
            onClick={onSaveConfig}
            disabled={loading}
            className="rounded-lg border border-[#74C7F5]/40 px-4 py-3 text-sm font-semibold tracking-normal text-[#BDEAFF] transition hover:bg-[#10203A] disabled:cursor-not-allowed disabled:brightness-75"
          >
            {actionLoading === 'config' ? 'Saving...' : 'Save BO Config'}
          </button>
          <button
            type="button"
            onClick={onSuggest}
            disabled={loading}
            className="rounded-lg bg-[#2F6BFF] px-4 py-3 text-sm font-semibold tracking-normal text-white transition hover:bg-[#1E5BFF] disabled:cursor-not-allowed disabled:brightness-75"
          >
            {actionLoading === 'suggest' ? 'Suggesting...' : 'Suggest Next'}
          </button>
          <button
            type="button"
            onClick={onFantasyRollout}
            disabled={loading}
            className="rounded-lg border border-blue-200/40 bg-blue-50/10 px-4 py-3 text-sm font-semibold tracking-normal text-blue-100 transition hover:bg-blue-50/20 disabled:cursor-not-allowed disabled:brightness-75 sm:col-span-2"
          >
            {actionLoading === 'fantasy' ? 'Running lookahead...' : 'Run 5-Step Lookahead'}
          </button>
        </div>
      </div>
    </section>
  )
}

function CurrentBestCard({ schema, state }: { schema: ProjectSchema; state: BOStateResponse | null }) {
  const currentBest = state?.current_best
  return (
    <section className="border-y border-slate-400/[0.10] py-6">
      <PanelHeader
        eyebrow="Current best"
        title="Best observed experiment"
        description="Only revealed or initial observed measurements are eligible for this score."
      />
      {currentBest ? (
        <div className="mt-5 grid gap-4 lg:grid-cols-[0.8fr_1.2fr]">
          <div className="rounded-lg border border-[#74C7F5] bg-[#0D1B2D] p-4">
            <p className="text-xs font-semibold tracking-normal text-[#2F6BFF]">
              Observed score
            </p>
            <p className="mt-2 text-4xl font-semibold tracking-[-0.05em] text-white">
              {formatNumber(currentBest.observed_score)}
            </p>
          </div>
          <ValueList
            title="Observed KPIs"
            values={currentBest.observed_outputs}
            names={schema.outputs.map((output) => ({
              name: output.name,
              label: output.label,
              unit: output.unit,
            }))}
          />
        </div>
      ) : (
        <p className="mt-5 rounded-lg border border-dashed border-slate-300 bg-[#0D1B2D] p-5 text-sm text-slate-300">
          Initialize replay to seed observed experiments.
        </p>
      )}
    </section>
  )
}

function NextSuggestionCard({
  schema,
  experiment,
  canReveal,
  loading,
  onAccept,
  onReject,
  onSkip,
  onReveal,
}: {
  schema: ProjectSchema
  experiment: LoggedExperiment | null
  canReveal: boolean
  loading: boolean
  onAccept: (experimentId: string) => void
  onReject: (experimentId: string) => void
  onSkip: (experimentId: string) => void
  onReveal: (experimentId: string) => void
}) {
  if (!experiment) {
    return (
      <section className="border-y border-dashed border-slate-400/[0.12] py-8 text-center">
        <p className="text-xs font-semibold tracking-normal text-[#74C7F5]">
          Next suggested experiment
        </p>
        <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] text-white">
          No active suggestion yet.
        </h2>
      </section>
    )
  }

  const isObserved = experiment.observed_outputs !== null && experiment.observed_outputs !== undefined
  const reason = metadataText(experiment, 'reason')
  const replayDistance = numberMetric(experiment.metadata, 'replay_distance')
  const predictionError =
    typeof experiment.metadata.prediction_error === 'object' && experiment.metadata.prediction_error !== null
      ? (experiment.metadata.prediction_error as Record<string, number>)
      : null

  return (
    <section className="border-y border-slate-400/[0.10] py-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <PanelHeader
          eyebrow={isObserved ? 'Replay result revealed' : 'Next suggested experiment'}
          title={`Iteration ${experiment.iteration}`}
          description={
            isObserved
              ? 'The accepted suggestion was mapped to the nearest hidden replay measurement.'
              : 'Suggested candidate awaiting scientist review.'
          }
        />
        <span
          className={`rounded-full border px-3 py-1 text-xs font-bold tracking-normal ${statusClass(
            experiment.status,
          )}`}
        >
          {experiment.status}
        </span>
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <ValueList
          title="Suggested inputs"
          values={experiment.inputs}
          names={schema.inputs.map((input) => ({
            name: input.name,
            label: input.label,
            unit: input.unit,
          }))}
        />
        <ValueList
          title="Predicted KPIs"
          values={experiment.predicted_outputs ?? {}}
          names={schema.outputs.map((output) => ({
            name: output.name,
            label: output.label,
            unit: output.unit,
          }))}
        />
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-4">
        <Metadata label="Expected improvement" value={formatNumber(objectiveMetric(experiment, 'expected_improvement'))} />
        <Metadata label="Uncertainty" value={formatNumber(numberMetric(experiment.uncertainty, 'objective_std'))} />
        <Metadata label="Acquisition" value={formatNumber(objectiveMetric(experiment, 'acquisition_score'))} />
        <Metadata label="Replay distance" value={formatNumber(replayDistance)} />
      </div>

      {reason && (
        <div className="mt-5 rounded-lg border border-blue-200 bg-[#0D1B2D] p-4 text-sm leading-6 text-[#BDEAFF]">
          {reason}
        </div>
      )}

      {isObserved && experiment.observed_outputs && (
        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          <ValueList
            title="Observed replay KPIs"
            values={experiment.observed_outputs}
            names={schema.outputs.map((output) => ({
              name: output.name,
              label: output.label,
              unit: output.unit,
            }))}
          />
          {predictionError && (
            <ValueList
              title="Prediction error"
              values={predictionError}
              names={schema.outputs.map((output) => ({
                name: output.name,
                label: output.label,
                unit: output.unit,
              }))}
            />
          )}
        </div>
      )}

      {!isObserved && (
        <div className="mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => onAccept(experiment.experiment_id)}
            disabled={loading || experiment.status !== 'suggested'}
            className="rounded-full bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#0B1220] disabled:cursor-not-allowed disabled:brightness-75"
          >
            Accept
          </button>
          <button
            type="button"
            onClick={() => onReject(experiment.experiment_id)}
            disabled={loading || experiment.status === 'rejected'}
            className="rounded-md border border-rose-400/30 bg-rose-950/30 px-5 py-3 text-sm font-semibold text-rose-100 transition hover:bg-rose-900/40 disabled:cursor-not-allowed disabled:brightness-75"
          >
            Reject
          </button>
          <button
            type="button"
            onClick={() => onSkip(experiment.experiment_id)}
            disabled={loading || experiment.status !== 'suggested'}
            className="rounded-md border border-slate-700 bg-[#070C16] px-5 py-3 text-sm font-semibold text-slate-300 transition hover:bg-[#10203A] disabled:cursor-not-allowed disabled:brightness-75"
          >
            Skip
          </button>
          <button
            type="button"
            onClick={() => onReveal(experiment.experiment_id)}
            disabled={loading || !canReveal}
            className="rounded-md border border-[#74C7F5]/40 bg-[#0D1B2D] px-5 py-3 text-sm font-semibold text-[#BDEAFF] transition hover:bg-[#1E5BFF] disabled:cursor-not-allowed disabled:brightness-75"
          >
            Reveal replay result
          </button>
        </div>
      )}
    </section>
  )
}

function ConstraintsPanel({
  schema,
  constraints,
  setConstraints,
}: {
  schema: ProjectSchema
  constraints: ConstraintDraft
  setConstraints: Dispatch<SetStateAction<ConstraintDraft>>
}) {
  return (
    <section className="border-y border-slate-400/[0.10] py-6">
      <PanelHeader
        eyebrow="Expert constraints"
        title="Sequential-search limits"
        description="These bounds affect future explore/exploit suggestions without changing Batch Search."
      />
      <div className="mt-6 overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead>
            <tr className="text-xs font-semibold tracking-normal text-slate-500">
              <th className="px-3 py-3">Input</th>
              <th className="px-3 py-3">Schema range</th>
              <th className="px-3 py-3">Active min</th>
              <th className="px-3 py-3">Active max</th>
              <th className="px-3 py-3">Fixed</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {schema.inputs.map((input) => {
              const row = constraints[input.name] ?? {
                min: '',
                max: '',
                fixed: '',
                fixedEnabled: false,
              }
              return (
                <tr key={input.name} className="align-top">
                  <td className="px-3 py-3 font-semibold text-slate-100">{input.label}</td>
                  <td className="px-3 py-3 text-slate-500">
                    {formatNumber(input.min)} to {formatNumber(input.max)} {input.unit}
                  </td>
                  <td className="px-3 py-3">
                    <input
                      type="number"
                      step="any"
                      value={row.min}
                      placeholder={formatNumber(input.min)}
                      onChange={(event) =>
                        setConstraints((current) => ({
                          ...current,
                          [input.name]: { ...row, min: event.target.value },
                        }))
                      }
                      className="w-28 rounded-xl border border-slate-200 bg-white px-3 py-2 outline-none transition focus:border-[#74C7F5] focus:ring-4 focus:ring-[#74C7F5]/20"
                    />
                  </td>
                  <td className="px-3 py-3">
                    <input
                      type="number"
                      step="any"
                      value={row.max}
                      placeholder={formatNumber(input.max)}
                      onChange={(event) =>
                        setConstraints((current) => ({
                          ...current,
                          [input.name]: { ...row, max: event.target.value },
                        }))
                      }
                      className="w-28 rounded-xl border border-slate-200 bg-white px-3 py-2 outline-none transition focus:border-[#74C7F5] focus:ring-4 focus:ring-[#74C7F5]/20"
                    />
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex min-w-44 items-center gap-2">
                      <input
                        type="checkbox"
                        checked={row.fixedEnabled}
                        onChange={(event) =>
                          setConstraints((current) => ({
                            ...current,
                            [input.name]: { ...row, fixedEnabled: event.target.checked },
                          }))
                        }
                        className="h-4 w-4 rounded border-slate-300 accent-[#74C7F5]"
                      />
                      <input
                        type="number"
                        step="any"
                        value={row.fixed}
                        disabled={!row.fixedEnabled}
                        onChange={(event) =>
                          setConstraints((current) => ({
                            ...current,
                            [input.name]: { ...row, fixed: event.target.value },
                          }))
                        }
                        className="w-28 rounded-xl border border-slate-200 bg-white px-3 py-2 outline-none transition focus:border-[#74C7F5] focus:ring-4 focus:ring-[#74C7F5]/20 disabled:bg-slate-100 disabled:text-slate-400"
                      />
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function ValueList({
  title,
  values,
  names,
}: {
  title: string
  values: Record<string, number>
  names: Array<{ name: string; label: string; unit: string }>
}) {
  return (
    <div className="border-t border-slate-400/[0.07] pt-4">
      <h3 className="text-sm font-semibold tracking-normal text-slate-500">{title}</h3>
      <dl className="mt-3 space-y-2">
        {names.map((item) => (
          <div key={item.name} className="flex items-baseline justify-between gap-4">
            <dt className="text-sm text-slate-300">{item.label}</dt>
            <dd className="text-right text-sm font-semibold text-white">
              {formatNumber(values[item.name])}
              <span className="ml-1 font-normal text-slate-400">{item.unit}</span>
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function ObjectiveIterationChart({
  state,
  fantasyTrajectory,
}: {
  state: BOStateResponse | null
  fantasyTrajectory: BOFantasyStep[]
}) {
  const experiments = state?.history ?? []
  const xValues = experiments.map((experiment) => experiment.iteration)
  const observed = experiments.map((experiment) => experiment.objective?.observed_score ?? null)
  const predicted = experiments.map((experiment) => experiment.objective?.predicted_score ?? null)
  const bestObserved: Array<number | null> = []
  let best: number | null = null
  observed.forEach((value) => {
    if (typeof value === 'number') best = best === null ? value : Math.max(best, value)
    bestObserved.push(best)
  })

  const data: Data[] = [
    {
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Observed score',
      x: xValues,
      y: observed,
      marker: { color: '#2F6BFF' },
      line: { color: '#2F6BFF' },
    },
    {
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Predicted score',
      x: xValues,
      y: predicted,
      marker: { color: '#5DA8FF' },
      line: { color: '#5DA8FF', dash: 'dot' },
    },
    {
      type: 'scatter',
      mode: 'lines',
      name: 'Current best',
      x: xValues,
      y: bestObserved,
      line: { color: '#050914', width: 3 },
    },
  ]
  if (fantasyTrajectory.length > 0) {
    const lastIteration = Math.max(0, ...xValues)
    data.push({
      type: 'scatter',
      mode: 'lines+markers',
      name: 'MLP fantasy rollout',
      x: fantasyTrajectory.map((step) => lastIteration + step.iteration),
      y: fantasyTrajectory.map((step) => step.predicted_score),
      customdata: fantasyTrajectory.map((step) =>
        step.low_confidence_region ? 'Simulated using MLP (not observed), low-confidence region' : 'Simulated using MLP (not observed)',
      ),
      hovertemplate:
        '<b>Fantasy step %{x}</b><br>Predicted objective: %{y:.3f}<br>%{customdata}<extra>%{fullData.name}</extra>',
      marker: { color: '#93c5fd', symbol: 'diamond' },
      line: { color: '#93c5fd', dash: 'dash', width: 3 },
    })
  }

  return (
    <ChartPanel
      eyebrow="Loop progress"
      title="Objective over iterations"
      data={data}
      xAxisTitle="BO iteration"
      yAxisTitle="Weighted objective score"
    />
  )
}

function AcquisitionChart({ state }: { state: BOStateResponse | null }) {
  const experiments =
    state?.history.filter(
      (experiment) => experiment.source === 'bo_suggested' || experiment.source === 'replay_revealed',
    ) ?? []
  const xValues = experiments.map((experiment) => experiment.iteration)
  const acquisition = experiments.map((experiment) => experiment.objective?.acquisition_score ?? null)
  const improvement = experiments.map((experiment) => experiment.objective?.expected_improvement ?? null)
  const uncertainty = experiments.map((experiment) => numberMetric(experiment.uncertainty, 'objective_std') ?? null)

  const data: Data[] = [
    {
      type: 'bar',
      name: 'Acquisition',
      x: xValues,
      y: acquisition,
      marker: { color: '#74C7F5' },
    },
    {
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Expected improvement',
      x: xValues,
      y: improvement,
      marker: { color: '#2F6BFF' },
      line: { color: '#2F6BFF' },
    },
    {
      type: 'scatter',
      mode: 'lines+markers',
      name: 'Objective std',
      x: xValues,
      y: uncertainty,
      marker: { color: '#2563eb' },
      line: { color: '#2563eb', dash: 'dot' },
    },
  ]

  return (
    <ChartPanel
      eyebrow="Acquisition"
      title="Uncertainty and expected improvement"
      data={data}
      xAxisTitle="BO suggestion iteration"
      yAxisTitle="Acquisition / uncertainty value"
    />
  )
}

function FantasyRolloutPanel({
  schema,
  trajectory,
}: {
  schema: ProjectSchema
  trajectory: BOFantasyStep[]
}) {
  if (trajectory.length === 0) return null

  const firstInput = schema.inputs[0]
  const secondInput = schema.inputs[1]

  return (
    <section className="border-y border-slate-400/[0.10] py-6">
      <PanelHeader
        eyebrow="Fantasy rollout"
        title="5-step MLP lookahead"
        description="Simulated using the MLP surrogate for planning only. These fantasy points are not stored in the experiment log and are not treated as observed data."
      />
      <div className="mt-5 grid gap-3 md:grid-cols-5">
        {trajectory.map((step) => (
          <div
            key={step.iteration}
            className="border-l border-slate-400/[0.10] pl-4"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-bold tracking-normal text-blue-900">
                Step {step.iteration}
              </p>
              <span
                className={`rounded-full px-2 py-1 text-[0.65rem] font-bold tracking-normal ${
                  step.low_confidence_region
                    ? 'bg-amber-100 text-amber-900'
                    : 'bg-[#0D1B2D] text-[#BDEAFF] ring-1 ring-[#74C7F5]/30'
                }`}
              >
                {step.low_confidence_region ? 'Low confidence' : 'Near data'}
              </span>
            </div>
            <dl className="mt-4 space-y-2 text-sm">
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Predicted score</dt>
                <dd className="font-semibold text-white">{formatNumber(step.predicted_score)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Acquisition</dt>
                <dd className="font-semibold text-white">{formatNumber(step.acquisition_score)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt className="text-slate-500">Distance</dt>
                <dd className="font-semibold text-white">
                  {formatNumber(step.distance_to_nearest_real)}
                </dd>
              </div>
              {firstInput && (
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">{firstInput.label}</dt>
                  <dd className="font-semibold text-white">
                    {formatNumber(step.inputs[firstInput.name])}
                  </dd>
                </div>
              )}
              {secondInput && (
                <div className="flex justify-between gap-3">
                  <dt className="text-slate-500">{secondInput.label}</dt>
                  <dd className="font-semibold text-white">
                    {formatNumber(step.inputs[secondInput.name])}
                  </dd>
                </div>
              )}
            </dl>
          </div>
        ))}
      </div>
    </section>
  )
}

function PredictedObservedChart({
  schema,
  state,
}: {
  schema: ProjectSchema
  state: BOStateResponse | null
}) {
  const observedExperiment =
    [...(state?.history ?? [])]
      .filter((experiment) => experiment.observed_outputs != null && experiment.predicted_outputs != null)
      .sort((left, right) => right.iteration - left.iteration)[0] ?? null

  const labels = schema.outputs.map((output) => output.label)
  const predictedValues = observedExperiment
    ? schema.outputs.map((output) => observedExperiment.predicted_outputs?.[output.name] ?? 0)
    : []
  const observedValues = observedExperiment
    ? schema.outputs.map((output) => observedExperiment.observed_outputs?.[output.name] ?? 0)
    : []

  const layout: Partial<Layout> = transparentDarkPlotLayout({
    autosize: true,
    barmode: 'group',
    margin: { l: 54, r: 24, t: 24, b: 58 },
    legend: { orientation: 'h', y: 1.16 },
  })

  const traces: Data[] = observedExperiment
    ? [
        {
          type: 'bar',
          name: 'Predicted',
          x: labels,
          y: predictedValues,
          marker: { color: '#5DA8FF' },
        },
        {
          type: 'bar',
          name: 'Observed',
          x: labels,
          y: observedValues,
          marker: { color: '#2F6BFF' },
        },
      ]
    : []

  return (
    <section className="border-y border-slate-400/[0.10] py-6">
      <PanelHeader
        eyebrow="Surrogate check"
        title={
          observedExperiment
            ? `Predicted vs observed KPIs, iteration ${observedExperiment.iteration}`
            : 'Predicted vs observed KPIs'
        }
        description="Predicted and observed values remain visually separate."
      />
      <div className="mt-6 overflow-hidden border-y border-slate-400/[0.10] py-3">
        {observedExperiment ? (
          <Plot
            data={traces}
            layout={layout}
            config={{ displayModeBar: false, responsive: true }}
            useResizeHandler
            className="h-[360px] w-full"
          />
        ) : (
          <div className="flex h-[280px] items-center justify-center text-center text-sm text-slate-500">
            No experiment with both predicted and observed KPI values is available yet.
          </div>
        )}
      </div>
    </section>
  )
}

function ChartPanel({
  eyebrow,
  title,
  data,
  emptyMessage = 'Initialize and run the loop to populate this chart.',
  barmode,
  xAxisTitle,
  yAxisTitle,
}: {
  eyebrow: string
  title: string
  data: Data[]
  emptyMessage?: string
  barmode?: 'group'
  xAxisTitle?: string
  yAxisTitle?: string
}) {
  const hasData = data.some((trace) => {
    const yValues = (trace as { y?: unknown }).y
    return Array.isArray(yValues) && yValues.length > 0
  })
  const layout: Partial<Layout> = transparentDarkPlotLayout({
    autosize: true,
    barmode,
    margin: { l: 54, r: 24, t: 24, b: 58 },
    legend: { orientation: 'h', y: 1.16 },
    xaxis: xAxisTitle ? { title: { text: xAxisTitle } } : undefined,
    yaxis: yAxisTitle ? { title: { text: yAxisTitle } } : undefined,
  })

  return (
    <section className="border-y border-slate-400/[0.10] py-6">
      <PanelHeader eyebrow={eyebrow} title={title} description="Predicted and observed values remain visually separate." />
      <div className="mt-6 overflow-hidden border-y border-slate-400/[0.10] py-3">
        {hasData ? (
          <Plot
            data={data}
            layout={layout}
            config={{ displayModeBar: false, responsive: true }}
            useResizeHandler
            className="h-[360px] w-full"
          />
        ) : (
          <div className="flex h-[280px] items-center justify-center text-center text-sm text-slate-500">
            {emptyMessage}
          </div>
        )}
      </div>
    </section>
  )
}

function HistoryTable({ schema, state }: { schema: ProjectSchema; state: BOStateResponse | null }) {
  const history = [...(state?.history ?? [])].reverse().slice(0, 30)
  return (
    <section className="border-y border-slate-400/[0.10] py-6">
      <PanelHeader
        eyebrow="Experiment log"
        title="Explore/exploit history"
        description="JSONL-backed history persists suggested, reviewed, and observed replay states."
      />
      <div className="mt-6 overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead>
            <tr className="text-xs font-semibold tracking-normal text-slate-500">
              <th className="px-3 py-3">Iteration</th>
              <th className="px-3 py-3">Status</th>
              <th className="px-3 py-3">Source</th>
              <th className="px-3 py-3">{schema.inputs[0]?.label ?? 'Input'}</th>
              <th className="px-3 py-3">Predicted score</th>
              <th className="px-3 py-3">Observed score</th>
              <th className="px-3 py-3">Uncertainty</th>
              <th className="px-3 py-3">Decision</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {history.map((experiment) => (
              <tr key={experiment.experiment_id}>
                <td className="px-3 py-3 font-semibold text-white">{experiment.iteration}</td>
                <td className="px-3 py-3">
                  <span
                    className={`rounded-full border px-2 py-1 text-xs font-bold tracking-normal ${statusClass(
                      experiment.status,
                    )}`}
                  >
                    {experiment.status}
                  </span>
                </td>
                <td className="px-3 py-3 text-slate-300">{experiment.source}</td>
                <td className="px-3 py-3 text-slate-300">
                  {formatNumber(experiment.inputs[schema.inputs[0]?.name ?? ''])}
                </td>
                <td className="px-3 py-3 text-slate-300">
                  {formatNumber(objectiveMetric(experiment, 'predicted_score'))}
                </td>
                <td className="px-3 py-3 text-slate-300">
                  {formatNumber(objectiveMetric(experiment, 'observed_score'))}
                </td>
                <td className="px-3 py-3 text-slate-300">
                  {formatNumber(numberMetric(experiment.uncertainty, 'objective_std'))}
                </td>
                <td className="px-3 py-3 text-slate-300">{experiment.review?.decision ?? 'none'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {history.length === 0 && (
          <p className="rounded-md border border-dashed border-[#74C7F5]/25 bg-[#0D1B2D] p-5 text-center text-sm text-slate-300">
            No BO experiments logged yet.
          </p>
        )}
      </div>
    </section>
  )
}

function ScientistReviewDialog({
  reason,
  notes,
  setReason,
  setNotes,
  onCancel,
  onSave,
  loading,
}: {
  reason: BOReviewReason
  notes: string
  setReason: (value: BOReviewReason) => void
  setNotes: (value: string) => void
  onCancel: () => void
  onSave: () => void
  loading: boolean
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/45 px-4">
      <section className="w-full max-w-lg border-y border-slate-400/[0.10] py-6">
        <PanelHeader
          eyebrow="Scientist review"
          title="Reject suggestion"
          description="Rejected suggestions are logged and do not reveal hidden replay measurements."
        />
        <label htmlFor="reject-reason" className="mt-5 block">
          <span className="text-sm font-semibold text-slate-300">Reason</span>
          <select
            id="reject-reason"
            value={reason}
            onChange={(event) => setReason(event.target.value as BOReviewReason)}
            className="mt-2 w-full rounded-md border border-slate-700 bg-[#050914] px-4 py-3 text-sm font-medium text-white outline-none transition focus:border-[#74C7F5] focus:ring-4 focus:ring-[#74C7F5]/20"
          >
            {rejectionReasons.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        <label htmlFor="reject-notes" className="mt-4 block">
          <span className="text-sm font-semibold text-slate-300">Notes</span>
          <textarea
            id="reject-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={4}
            className="mt-2 w-full rounded-md border border-slate-700 bg-[#050914] px-4 py-3 text-sm font-medium text-white outline-none transition focus:border-[#74C7F5] focus:ring-4 focus:ring-[#74C7F5]/20"
          />
        </label>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className="rounded-full border border-slate-200 px-5 py-3 text-sm font-semibold text-slate-300 transition hover:bg-[#10203A] disabled:cursor-not-allowed disabled:brightness-75"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={loading}
            className="rounded-full bg-red-900 px-5 py-3 text-sm font-semibold text-white transition hover:bg-red-950 disabled:cursor-not-allowed disabled:brightness-75"
          >
            {loading ? 'Saving...' : 'Save rejection'}
          </button>
        </div>
      </section>
    </div>
  )
}
