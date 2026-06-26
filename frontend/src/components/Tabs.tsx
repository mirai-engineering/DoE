import { useMemo, useState } from 'react'
import type { ActiveTab } from '../types/doe'

type NavItem = {
  id?: ActiveTab
  label: string
  description: string
  disabled?: boolean
  note?: string
}

const tabGroups: Array<{
  title: string
  subtitle: string
  items: NavItem[]
}> = [
  {
    title: 'Model setup',
    subtitle: 'Prepare',
    items: [
      { id: 'data-intake', label: 'Data Intake', description: 'Upload data and create a project.' },
      { id: 'preprocessing-review', label: 'Preprocessing', description: 'Approve metadata, evidence, and training.' },
      { id: 'model-quality', label: 'Model Quality', description: 'Review model performance.' },
      { id: 'data-scientist', label: 'Data Scientist', description: 'Ask scoped questions about data and models.' },
    ],
  },
  {
    title: 'Design',
    subtitle: 'Use model',
    items: [
      { id: 'design-studio', label: 'Design Studio', description: 'Explore predictions interactively.' },
      { id: 'batch', label: 'Batch Search', description: 'Rank virtual candidates.' },
      { id: 'optimization', label: 'Explore & Exploit', description: 'Plan sequential experiments.' },
    ],
  },
  {
    title: 'Impact',
    subtitle: 'Value',
    items: [
      { id: 'impact', label: 'Business Impact', description: 'Estimate time and cost savings.' },
    ],
  },
]

export function Tabs({
  activeTab,
  onTabChange,
}: {
  activeTab: ActiveTab
  onTabChange: (tab: ActiveTab) => void
}) {
  const [openGroup, setOpenGroup] = useState<string | null>(null)

  const activeGroup = useMemo(
    () => tabGroups.find((group) => group.items.some((item) => item.id === activeTab)),
    [activeTab],
  )

  return (
    <nav className="relative z-[90] mt-6" aria-label="Primary product navigation">
      {openGroup && <button type="button" aria-label="Close navigation menu" className="fixed inset-0 z-[85] cursor-default bg-transparent" onClick={() => setOpenGroup(null)} />}
      <div className="relative z-[90] flex flex-wrap items-center gap-2 rounded-[1.5rem] border border-white/80 bg-white/65 p-2 shadow-inner shadow-white/70 backdrop-blur-xl">
        {tabGroups.map((group) => {
          const groupActive = group.title === activeGroup?.title
          const activeItem = group.items.find((item) => item.id === activeTab)
          const isOpen = openGroup === group.title
          return (
            <div key={group.title} className="relative">
              <button
                type="button"
                onClick={() => setOpenGroup(isOpen ? null : group.title)}
                className={`flex min-w-[10rem] items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left transition ${
                  groupActive ? 'bg-slate-950 text-white shadow-lg shadow-slate-950/20 ring-1 ring-white/20' : 'bg-white/80 text-slate-800 shadow-sm shadow-slate-900/5 hover:bg-white'
                }`}
                aria-haspopup="menu"
                aria-expanded={isOpen}
              >
                <span>
                  <span className="block text-sm font-semibold">{group.title}</span>
                  <span className={`mt-0.5 block text-xs ${groupActive ? 'text-white/60' : 'text-slate-500'}`}>{activeItem?.label ?? group.subtitle}</span>
                </span>
                <span className={`grid h-6 w-6 place-items-center rounded-full text-sm transition ${groupActive ? 'bg-white/10' : 'bg-slate-100'} ${isOpen ? 'rotate-180' : ''}`}>⌄</span>
              </button>

              {isOpen && (
                <div role="menu" className="absolute left-0 z-[95] mt-3 w-[20rem] overflow-hidden rounded-3xl border border-slate-200/90 bg-white shadow-2xl shadow-slate-950/25 ring-1 ring-white/80">
                  <div className="p-2">
                    {group.items.map((item) => {
                      const itemActive = item.id === activeTab
                      return (
                        <button
                          key={item.label}
                          type="button"
                          role="menuitem"
                          disabled={item.disabled}
                          onClick={() => {
                            if (!item.id) return
                            onTabChange(item.id)
                            setOpenGroup(null)
                          }}
                          className={`w-full rounded-2xl px-4 py-3 text-left transition ${
                            itemActive
                              ? 'bg-slate-950 text-white shadow-lg shadow-slate-950/15'
                              : item.disabled
                                ? 'cursor-not-allowed border border-dashed border-slate-200 bg-slate-50/80 text-slate-400'
                                : 'text-slate-700 hover:bg-[#fbfaf5]'
                          }`}
                        >
                          <span className="font-semibold">{item.label}</span>
                          <span className={`mt-1 block text-xs leading-5 ${itemActive ? 'text-white/65' : 'text-slate-500'}`}>{item.description}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </nav>
  )
}
