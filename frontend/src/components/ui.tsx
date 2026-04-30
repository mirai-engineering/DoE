import type { ProjectSchema } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'

export function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-[#f8f6ef] p-3">
      <div className="text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-slate-400">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-semibold text-slate-800">{value}</div>
    </div>
  )
}

export function PanelHeader({
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
      <h2
        className={`mt-2 text-2xl font-semibold tracking-[-0.04em] ${
          dark ? 'text-white' : 'text-slate-950'
        }`}
      >
        {title}
      </h2>
      <p className={`mt-2 text-sm leading-6 ${dark ? 'text-white/70' : 'text-slate-600'}`}>
        {description}
      </p>
    </div>
  )
}

export function NumberField({
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
      <span
        className={`flex items-center justify-between gap-3 text-sm font-semibold ${
          dark ? 'text-white/90' : 'text-slate-700'
        }`}
      >
        {label}
        <span className={`text-xs font-medium ${dark ? 'text-white/50' : 'text-slate-400'}`}>
          {unit}
        </span>
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

export function SelectField({
  id,
  label,
  value,
  onChange,
  options,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label htmlFor={id} className="block">
      <span className="text-sm font-semibold text-slate-700">{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium text-slate-950 outline-none transition focus:border-[#60745c] focus:ring-4 focus:ring-[#60745c]/20"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function WeightField({
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
        <span className="text-xs font-medium uppercase tracking-[0.16em] text-white/40">
          {direction}
        </span>
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

export function FixedInputField({
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

export function KpiCard({
  label,
  value,
  unit,
  direction,
}: {
  label: string
  value: number | undefined
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

export function Alert({
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

export function EmptyRecommendationsState({ onGoHome }: { onGoHome: () => void }) {
  return (
    <section className="rounded-[2rem] border border-dashed border-slate-300 bg-white/80 p-10 text-center shadow-xl shadow-slate-900/10 backdrop-blur">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#60745c]">
        Awaiting candidate search
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950">
        Run candidate recommendation first to unlock visualizations.
      </h2>
      <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-600">
        Use the Batch Explorer tab to sample the design space. The ranked table, KPI comparison,
        parallel coordinates, and response surface will use the generated candidates.
      </p>
      <button
        type="button"
        onClick={onGoHome}
        className="mt-6 rounded-full bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-lg shadow-slate-950/20 transition hover:-translate-y-0.5 hover:bg-[#263329]"
      >
        Go to Batch Explorer
      </button>
    </section>
  )
}
