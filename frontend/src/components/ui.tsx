import { ReactNode, useState } from 'react'
import type { ProjectSchema } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'

export type LifecycleStep = {
  id: string
  label: string
  status: 'done' | 'current' | 'locked'
}

export function LifecycleStepper({ steps }: { steps: LifecycleStep[] }) {
  return (
    <div className="rounded-lg border border-slate-700/80 bg-[#0B1220] p-3">
      <div className="grid gap-2 md:grid-cols-5">
        {steps.map((step, index) => {
          const isDone = step.status === 'done'
          const isCurrent = step.status === 'current'
          return (
            <div key={step.id} className={`rounded-md border px-3 py-3 ${isCurrent ? 'border-[#2F6BFF]/70 bg-[#10203A] text-white' : isDone ? 'border-[#74C7F5]/30 bg-[#0D1B2D] text-slate-100' : 'border-slate-800 bg-[#070C16] text-slate-500'}`}>
              <div className="flex items-center gap-2">
                <span className={`grid h-6 w-6 place-items-center rounded text-xs font-bold ${isCurrent ? 'bg-[#2F6BFF] text-white' : isDone ? 'bg-[#74C7F5]/15 text-[#74C7F5]' : 'bg-[#050914] text-slate-500'}`}>
                  {isDone ? '✓' : index + 1}
                </span>
                <span className="text-sm font-semibold">{step.label}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function SectionCard({
  children,
  className = '',
  variant = 'glass',
  density = 'normal',
}: {
  children: ReactNode
  className?: string
  variant?: 'glass' | 'solid' | 'subtle'
  density?: 'compact' | 'normal'
}) {
  const variants = {
    glass: 'border-white/10 bg-[linear-gradient(145deg,rgba(16,27,50,0.88),rgba(8,13,24,0.82))] shadow-[0_20px_55px_rgba(2,6,23,0.22)] backdrop-blur-xl',
    solid: 'border-slate-700/70 bg-[#0B1220] shadow-[0_16px_42px_rgba(2,6,23,0.18)]',
    subtle: 'border-slate-700/55 bg-[#08111F]/82',
  }
  const padding = density === 'compact' ? 'p-4 sm:p-5' : 'p-5 sm:p-6'
  return <section className={`rounded-2xl border ${variants[variant]} ${padding} ${className}`}>{children}</section>
}

export function DisclosurePanel({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="rounded-md border border-slate-700 bg-[#070C16]">
      <button type="button" onClick={() => setOpen((current) => !current)} className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left text-sm font-semibold text-slate-100">
        {title}
        <span className={`grid h-7 w-7 place-items-center rounded bg-[#050914] text-slate-400 transition ${open ? 'rotate-180' : ''}`}>⌄</span>
      </button>
      {open && <div className="border-t border-slate-700 px-4 py-4">{children}</div>}
    </div>
  )
}

export function Metadata({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.035] px-3 py-2.5">
      <div className="text-[0.66rem] font-semibold uppercase tracking-[0.16em] text-[#9FB0C8]">
        {label}
      </div>
      <div className="mt-1 truncate text-sm font-semibold text-slate-50">{value}</div>
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
          dark ? 'text-[#74C7F5]' : 'text-[#2F6BFF]'
        }`}
      >
        {eyebrow}
      </p>
      <h2
        className={`mt-1.5 text-[1.35rem] font-semibold tracking-[-0.035em] sm:text-2xl ${
          dark ? 'text-white' : 'text-[#F6F4EA]'
        }`}
      >
        {title}
      </h2>
      <p className={`mt-2 text-sm leading-6 ${dark ? 'text-white/76' : 'text-[#C7D2E4]'}`}>
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
        className={`mt-2 w-full rounded-md border px-3 py-2.5 text-sm font-medium outline-none transition focus:ring-2 ${
          dark
            ? 'border-slate-700 bg-[#050914] text-white focus:border-[#74C7F5] focus:ring-[#74C7F5]/20'
            : 'border-slate-300 bg-white text-slate-950 focus:border-[#475569] focus:ring-slate-500/20'
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
        className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-950 outline-none transition focus:border-[#475569] focus:ring-2 focus:ring-slate-500/20"
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
    <label htmlFor={id} className="block rounded-md border border-slate-700 bg-[#070C16] p-3">
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
        className="mt-2 w-full rounded-md border border-slate-700 bg-[#050914] px-3 py-2 text-sm font-medium text-white outline-none transition focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20"
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
    <div className="rounded-md border border-slate-700 bg-[#070C16] p-3">
      <label className="flex items-center gap-3 text-sm font-semibold text-white/90">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(event) => onEnabledChange(event.target.checked)}
          className="h-4 w-4 rounded border-slate-600 bg-slate-950 accent-[#74C7F5]"
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
        className="mt-2 w-full rounded-md border border-slate-700 bg-[#050914] px-3 py-2 text-sm font-medium text-white outline-none transition focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20 disabled:brightness-50"
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
    <div className="rounded-lg border border-slate-300 bg-[#0B1220] p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-700">{label}</p>
        <span className="rounded bg-[#e8eadf] px-2 py-1 text-[0.65rem] font-bold uppercase tracking-[0.16em] text-[#2F6BFF]">
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
    <div className={`rounded-lg border p-4 ${className}`}>
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
    <section className="rounded-lg border border-dashed border-slate-300 bg-white/90 p-10 text-center shadow-xl shadow-slate-900/10">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-[#74C7F5]">
        Awaiting candidate search
      </p>
      <h2 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-slate-950">
        Run candidate recommendation first to unlock visualizations.
      </h2>
      <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-600">
        Use Batch Search → Configure to sample the design space. The ranked table, KPI comparison,
        parallel coordinates, and response surface will use the generated candidates.
      </p>
      <button
        type="button"
        onClick={onGoHome}
        className="mt-6 rounded-md bg-slate-950 px-5 py-3 text-sm font-semibold text-white shadow-sm shadow-slate-950/20 transition hover:bg-[#263329]"
      >
        Go to Batch Search
      </button>
    </section>
  )
}
