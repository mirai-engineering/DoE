import type { Dispatch, FormEvent, SetStateAction } from 'react'
import type { PredictionMap, ProjectSchema } from '../lib/api'
import { DesignVariableControl } from './design-studio/DesignVariableControl'
import { Alert, KpiCard, PanelHeader } from './ui'

export function PredictPanel({
  schema,
  inputValues,
  setInputValues,
  prediction,
  warnings,
  loading,
  error,
  onSubmit,
  embedded = false,
}: {
  schema: ProjectSchema
  inputValues: Record<string, string>
  setInputValues: Dispatch<SetStateAction<Record<string, string>>>
  prediction: PredictionMap | null
  warnings: string[]
  loading: boolean
  error: string | null
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  embedded?: boolean
}) {
  return (
    <section className={embedded ? '' : 'border-y border-slate-400/[0.10] py-5'}>
      {!embedded && <PanelHeader
        eyebrow="Single experiment"
        title="Evaluate one reference design"
        description="Set one known or proposed formulation or operating point and estimate its outcomes."
      />}

      <form className="mt-6 space-y-5" onSubmit={onSubmit}>
        <div className="grid gap-x-5 gap-y-4 md:grid-cols-2">
          {schema.inputs.map((input) => (
            <DesignVariableControl
              key={input.name}
              input={input}
              value={inputValues[input.name] ?? ''}
              onChange={(value) =>
                setInputValues((current) => ({ ...current, [input.name]: value }))
              }
            />
          ))}
        </div>

        <button
          type="submit"
          disabled={loading}
          className="rounded-md border border-white/[0.12] px-5 py-3 text-sm font-semibold text-white transition hover:border-[#74C7F5]/50 hover:bg-white/[0.04] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Generating estimate…' : 'Generate reference estimate'}
        </button>
      </form>

      {error && (
        <div className="mt-5">
          <Alert tone="error" title="Prediction failed" messages={[error]} />
        </div>
      )}

      {warnings.length > 0 && (
        <div className="mt-5">
          <Alert tone="warning" title="Validation warnings" messages={warnings} />
        </div>
      )}

      {prediction && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold tracking-normal text-slate-500">
            Model-estimated outcomes
          </h3>
          <div className="mt-3 grid gap-6 sm:grid-cols-2">
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
  )
}
