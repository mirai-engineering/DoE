import type { Dispatch, FormEvent, SetStateAction } from 'react'
import type { PredictionMap, ProjectSchema } from '../lib/api'
import { Alert, KpiCard, NumberField, PanelHeader } from './ui'

export function PredictPanel({
  schema,
  inputValues,
  setInputValues,
  prediction,
  warnings,
  loading,
  error,
  onSubmit,
}: {
  schema: ProjectSchema
  inputValues: Record<string, string>
  setInputValues: Dispatch<SetStateAction<Record<string, string>>>
  prediction: PredictionMap | null
  warnings: string[]
  loading: boolean
  error: string | null
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
  return (
    <section className="rounded-[2rem] border border-white/70 bg-white/80 p-6 shadow-xl shadow-slate-900/10 backdrop-blur">
      <PanelHeader
        eyebrow="Single experiment"
        title="Predict outcomes"
        description="Set one candidate formulation or operating point and score the expected KPIs."
      />

      <form className="mt-6 space-y-5" onSubmit={onSubmit}>
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
          disabled={loading}
          className="w-full rounded-2xl bg-slate-950 px-5 py-4 text-sm font-semibold uppercase tracking-[0.18em] text-white shadow-lg shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-[#263329] disabled:cursor-not-allowed disabled:brightness-75"
        >
          {loading ? 'Predicting...' : 'Predict experiment'}
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
  )
}
