import type { Dispatch, FormEvent, SetStateAction } from 'react'
import type { ProjectSchema } from '../lib/api'
import { defaultVisualizationTopK, maxVisualizationTopK } from '../lib/doeUtils'
import type { FixedInputConfig, RecommendationRun } from '../types/doe'
import { Alert, FixedInputField, NumberField, PanelHeader, WeightField } from './ui'

export function RecommendPanel({
  schema,
  objectiveWeights,
  setObjectiveWeights,
  fixedInputs,
  setFixedInputs,
  nCandidates,
  setNCandidates,
  tableTopK,
  setTableTopK,
  visualizationTopK,
  setVisualizationTopK,
  loading,
  error,
  warnings,
  recommendationRun,
  onSubmit,
  onViewRecommendations,
}: {
  schema: ProjectSchema
  objectiveWeights: Record<string, string>
  setObjectiveWeights: Dispatch<SetStateAction<Record<string, string>>>
  fixedInputs: FixedInputConfig
  setFixedInputs: Dispatch<SetStateAction<FixedInputConfig>>
  nCandidates: string
  setNCandidates: (value: string) => void
  tableTopK: string
  setTableTopK: (value: string) => void
  visualizationTopK: string
  setVisualizationTopK: (value: string) => void
  loading: boolean
  error: string | null
  warnings: string[]
  recommendationRun: RecommendationRun | null
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  onViewRecommendations: () => void
}) {
  return (
    <section className="rounded-[2rem] border border-white/70 bg-[#18211d] p-6 text-white shadow-xl shadow-slate-900/20">
      <PanelHeader
        eyebrow="Candidate search"
        title="Recommend experiments"
        description="Sample the design space, rank many candidates for visualization, and keep the table focused on the best rows."
        dark
      />

      <form className="mt-6 space-y-6" onSubmit={onSubmit}>
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

        <div className="grid gap-3 sm:grid-cols-3">
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
            id="table-top-k"
            label="Table rows"
            unit="top k"
            min={1}
            max={25}
            value={tableTopK}
            onChange={setTableTopK}
            dark
          />
          <NumberField
            id="visualization-top-k"
            label="Chart rows"
            unit={`API cap ${maxVisualizationTopK}`}
            min={5}
            max={maxVisualizationTopK}
            value={visualizationTopK || String(defaultVisualizationTopK)}
            onChange={setVisualizationTopK}
            dark
          />
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-2xl bg-[#74C7F5] px-5 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-slate-950 shadow-lg shadow-black/20 transition hover:-translate-y-0.5 hover:bg-[#BDEAFF] disabled:cursor-not-allowed disabled:brightness-75"
        >
          {loading ? 'Searching...' : 'Recommend candidates'}
        </button>
      </form>

      {error && (
        <div className="mt-5">
          <Alert tone="error" title="Recommendation failed" messages={[error]} />
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mt-5">
          <Alert tone="warning" title="Recommendation warnings" messages={warnings} />
        </div>
      )}

      {recommendationRun && (
        <div className="mt-5 rounded-2xl border border-[#74C7F5]/30 bg-[#74C7F5]/10 p-4">
          <p className="text-sm font-semibold text-[#BDEAFF]">
            {recommendationRun.recommendations.length} ranked candidates available for charts.
          </p>
          <button
            type="button"
            onClick={onViewRecommendations}
            className="mt-3 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold uppercase tracking-[0.16em] text-white transition hover:bg-white/20"
          >
            View results
          </button>
        </div>
      )}
    </section>
  )
}
