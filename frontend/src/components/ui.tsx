import { ReactNode, useState } from 'react'
import type { ProjectSchema } from '../lib/api'
import { formatNumber } from '../lib/doeUtils'

export type StatusTone = 'neutral' | 'active' | 'success' | 'warning' | 'error'

export function StatusBadge({ tone, children }: { tone: StatusTone; children: ReactNode }) {
  const classes: Record<StatusTone, string> = {
    neutral: 'bg-white/[0.07] text-slate-200',
    active: 'bg-[#5BA8FF]/12 text-[#D9F3FF]',
    success: 'bg-emerald-500/10 text-emerald-100',
    warning: 'bg-amber-500/10 text-amber-100',
    error: 'bg-red-500/10 text-red-100',
  }
  return <span className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${classes[tone]}`}>{children}</span>
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return <div className="py-16 text-center"><h2 className="text-xl font-semibold text-white">{title}</h2><p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-[#9FB0C8]">{description}</p></div>
}

export function TechnicalDetails({ children, title = 'Technical details' }: { children: ReactNode; title?: string }) {
  return <details className="mt-5 border-t border-white/[0.10] pt-3 text-sm text-[#B8C2D4]"><summary className="cursor-pointer font-semibold text-[#BDEAFF]">{title}</summary><div className="mt-4 space-y-2">{children}</div></details>
}

export type LifecycleStep = {
  id: string
  label: string
  status: 'done' | 'current' | 'locked'
}

export function LifecycleStepper({ steps }: { steps: LifecycleStep[] }) {
  return (
    <div className="border-y border-slate-400/[0.07] py-4">
      <div className="grid gap-3 md:grid-cols-5">
        {steps.map((step, index) => {
          const isDone = step.status === 'done'
          const isCurrent = step.status === 'current'
          return (
            <div key={step.id} className="relative flex items-center gap-2.5 text-sm">
              <span className={`grid h-6 w-6 shrink-0 place-items-center rounded-full text-[0.7rem] font-semibold ring-1 ${isCurrent ? 'bg-[#2F6BFF] text-white ring-[#74C7F5]/40' : isDone ? 'bg-[#74C7F5]/12 text-[#74C7F5] ring-[#74C7F5]/24' : 'bg-transparent text-slate-500 ring-white/10'}`}>
                {isDone ? '✓' : index + 1}
              </span>
              <span className={isCurrent ? 'font-semibold text-white' : isDone ? 'font-medium text-slate-200' : 'font-medium text-slate-500'}>{step.label}</span>
              {index < steps.length - 1 && <span className="hidden h-px flex-1 bg-white/10 md:block" />}
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
  variant?: 'glass' | 'solid' | 'subtle' | 'flat'
  density?: 'compact' | 'normal'
}) {
  const variants = {
    glass: 'border-slate-400/[0.10] bg-[#081526]/45',
    solid: 'border-slate-400/[0.10] bg-[#081526]/55',
    subtle: 'border-slate-400/[0.07] bg-transparent',
    flat: 'border-slate-400/[0.07] bg-transparent',
  }
  const padding = density === 'compact' ? 'py-4 sm:py-5' : 'py-5 sm:py-6'
  return <section className={`border-y ${variants[variant]} ${padding} ${className}`}>{children}</section>
}

export function DisclosurePanel({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border-t border-white/10">
      <button type="button" onClick={() => setOpen((current) => !current)} className="flex w-full items-center justify-between gap-3 py-3 text-left text-sm font-semibold text-slate-100">
        {title}
        <span className={`grid h-6 w-6 place-items-center rounded text-slate-400 transition ${open ? 'rotate-180' : ''}`}>⌄</span>
      </button>
      {open && <div className="pb-4 text-sm text-slate-300">{children}</div>}
    </div>
  )
}

export function Metadata({ label, value, inline = false }: { label: string; value: string; inline?: boolean }) {
  if (inline) {
    return <span className="whitespace-nowrap text-sm text-[#9FB0C8]"><span className="text-slate-200">{value}</span> {label}</span>
  }
  return (
    <div className="border-l border-slate-400/[0.10] pl-3">
      <div className="text-[0.68rem] font-medium text-[#9FB0C8]">
        {label}
      </div>
      <div className="mt-0.5 truncate text-sm font-semibold text-slate-50">{value}</div>
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
        className={`text-sm font-medium ${
          dark ? 'text-[#74C7F5]' : 'text-[#74C7F5]'
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
      <p className={`mt-2 max-w-3xl text-sm leading-6 ${dark ? 'text-white/76' : 'text-[#C7D2E4]'}`}>
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
  dark = false,
}: {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  options: { value: string; label: string }[]
  dark?: boolean
}) {
  return (
    <label htmlFor={id} className="block">
      <span className={`text-sm font-semibold ${dark ? 'text-slate-200' : 'text-slate-700'}`}>{label}</span>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className={`mt-2 w-full rounded-md border px-3 py-2.5 text-sm font-medium outline-none transition focus:ring-2 ${dark ? 'border-white/[0.12] bg-[#050914] text-white focus:border-[#74C7F5] focus:ring-[#74C7F5]/20' : 'border-slate-300 bg-white text-slate-950 focus:border-[#475569] focus:ring-slate-500/20'}`}
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
    <label htmlFor={id} className="block border-t border-slate-400/[0.07] pt-3">
      <span className="flex items-center justify-between gap-3 text-sm font-semibold text-white/90">
        {label}
        <span className="text-xs font-medium text-white/45">
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
    <div className="border-t border-slate-400/[0.07] pt-3">
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
    <div className="border-l border-slate-400/[0.10] pl-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-semibold text-slate-200">{label}</p>
        <span className="rounded bg-[#2F6BFF]/10 px-2 py-1 text-[0.68rem] font-semibold text-[#74C7F5]">
          {direction}
        </span>
      </div>
      <div className="mt-4 flex items-baseline gap-2">
        <span className="text-3xl font-semibold tracking-[-0.05em] text-white">
          {formatNumber(value)}
        </span>
        <span className="text-sm text-slate-500">{unit}</span>
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
      ? 'bg-red-500/10 text-red-100'
      : 'bg-amber-500/10 text-amber-100'

  return (
    <div className={`px-3 py-2 ${className}`}>
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
    <section className="border-y border-dashed border-white/10 py-10 text-center">
      <p className="text-sm font-medium text-[#74C7F5]">
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
