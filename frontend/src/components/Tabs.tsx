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
      <div className="relative z-[90] flex flex-wrap items-center gap-2 rounded-[1.5rem] border border-violet-300/15 bg-white/[0.04] p-2 shadow-inner shadow-white/5 backdrop-blur-xl">
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
                  groupActive ? 'bg-[#7C5CFF] text-white shadow-lg shadow-[#7C5CFF]/25 ring-1 ring-white/20' : 'bg-white/5 text-[#F6F4EA] shadow-sm shadow-black/10 hover:bg-white/10'
                }`}
                aria-haspopup="menu"
                aria-expanded={isOpen}
              >
                <span>
                  <span className="block text-sm font-semibold">{group.title}</span>
                  <span className={`mt-0.5 block text-xs ${groupActive ? 'text-white/70' : 'text-[#9BA8C0]'}`}>{activeItem?.label ?? group.subtitle}</span>
                </span>
                <span className={`grid h-6 w-6 place-items-center rounded-full text-sm transition ${groupActive ? 'bg-white/10' : 'bg-[#030716]/70 text-[#9BA8C0]'} ${isOpen ? 'rotate-180' : ''}`}>⌄</span>
              </button>

              {isOpen && (
                <div role="menu" className="absolute left-0 z-[95] mt-3 w-[20rem] overflow-hidden rounded-3xl border border-violet-300/15 bg-[#0A1630] shadow-2xl shadow-black/40 ring-1 ring-white/10">
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
                              ? 'bg-[#7C5CFF] text-white shadow-lg shadow-[#7C5CFF]/20'
                              : item.disabled
                                ? 'cursor-not-allowed border border-dashed border-violet-300/10 bg-white/5 text-[#5A6B89]'
                                : 'text-[#F6F4EA] hover:bg-white/10'
                          }`}
                        >
                          <span className="font-semibold">{item.label}</span>
                          <span className={`mt-1 block text-xs leading-5 ${itemActive ? 'text-white/70' : 'text-[#9BA8C0]'}`}>{item.description}</span>
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
