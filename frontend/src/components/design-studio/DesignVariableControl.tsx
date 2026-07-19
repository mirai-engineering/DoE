import type { ProjectSchema } from '../../lib/api'
import { formatNumber } from '../../lib/doeUtils'

export function DesignVariableControl({ input, value, onChange }: { input: ProjectSchema['inputs'][number]; value: string; onChange: (value: string) => void }) {
  const step = (input.max - input.min) / 200
  return (
    <label className="block border-t border-white/[0.08] pt-4">
      <span className="flex items-start justify-between gap-3">
        <span>
          <span className="block text-sm font-semibold text-slate-100">{input.label}</span>
          <span className="mt-1 block text-xs text-slate-500">Allowed range {formatNumber(input.min)}–{formatNumber(input.max)}{input.unit ? ` ${input.unit}` : ''}</span>
        </span>
        {input.unit && <span className="rounded bg-white/[0.05] px-2 py-1 text-xs font-semibold text-slate-400">{input.unit}</span>}
      </span>
      <input type="range" min={input.min} max={input.max} step={step} value={value || input.min} onChange={(event) => onChange(event.target.value)} className="mt-4 w-full accent-[#5BA8FF]" />
      <div className="mt-2 grid grid-cols-[1fr_7rem] items-center gap-3">
        <div className="flex justify-between text-[0.68rem] text-slate-500"><span>{formatNumber(input.min)}</span><span>{formatNumber(input.max)}</span></div>
        <input aria-label={`${input.label} numeric value`} type="number" min={input.min} max={input.max} step={step} value={value} onChange={(event) => onChange(event.target.value)} className="w-full rounded-md border border-white/[0.12] bg-[#050914] px-2.5 py-2 text-right text-sm font-semibold text-white outline-none focus:border-[#74C7F5] focus:ring-2 focus:ring-[#74C7F5]/20" />
      </div>
    </label>
  )
}
