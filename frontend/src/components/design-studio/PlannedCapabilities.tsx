type PlannedCapability = { title: string; description: string }

export function PlannedCapabilities({ title, items }: { title: string; items: PlannedCapability[] }) {
  return (
    <section className="border-t border-white/[0.08] pt-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-slate-200">{title}</h3>
        <span className="text-xs font-semibold text-slate-500">Planned</span>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {items.map((item) => (
          <button key={item.title} type="button" disabled className="cursor-not-allowed rounded-lg border border-white/[0.07] bg-white/[0.02] p-3 text-left opacity-60">
            <span className="block text-sm font-semibold text-slate-300">{item.title}</span>
            <span className="mt-1 block text-xs leading-5 text-slate-500">{item.description}</span>
          </button>
        ))}
      </div>
    </section>
  )
}
