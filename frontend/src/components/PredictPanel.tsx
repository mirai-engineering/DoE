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
    <section className="border-y border-slate-400/[0.10] py-5">
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
          className="w-full rounded-md bg-[#2F6BFF] px-5 py-3 text-sm font-semibold text-white transition hover:bg-[#245CF0] disabled:cursor-not-allowed disabled:opacity-50"
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
          <h3 className="text-sm font-semibold tracking-normal text-slate-500">
            Predicted KPIs
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
