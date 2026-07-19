import { type KeyboardEvent, useRef } from 'react'
import { nextPreparationTab, type PreparationTab } from '../../lib/preparationPresentation'

const tabs: Array<{ id: PreparationTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'variables', label: 'Variables' },
  { id: 'preprocessing', label: 'Preprocessing' },
  { id: 'training', label: 'Training' },
  { id: 'ask-mirai', label: 'Ask Mirai' },
]

export function PreparationTabs({ activeTab, onChange }: { activeTab: PreparationTab; onChange: (tab: PreparationTab) => void }) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const nextTab = nextPreparationTab(tabs[index].id, event.key as 'ArrowLeft' | 'ArrowRight' | 'Home' | 'End')
    const nextIndex = tabs.findIndex((tab) => tab.id === nextTab)
    onChange(nextTab)
    tabRefs.current[nextIndex]?.focus()
  }

  return (
    <div className="overflow-x-auto border-b border-white/[0.10]" role="tablist" aria-label="Project preparation sections">
      <div className="flex min-w-max gap-1">
        {tabs.map((tab, index) => {
          const selected = activeTab === tab.id
          return (
            <button
              key={tab.id}
              ref={(element) => { tabRefs.current[index] = element }}
              id={`preparation-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`preparation-panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={`relative px-4 py-3 text-sm font-semibold transition ${selected ? 'text-white after:absolute after:inset-x-2 after:bottom-0 after:h-0.5 after:bg-[#74C7F5]' : 'text-[#9FB0C8] hover:text-white'}`}
            >
              {tab.label}
              {selected && <span className="sr-only">, selected</span>}
            </button>
          )
        })}
      </div>
    </div>
  )
}
