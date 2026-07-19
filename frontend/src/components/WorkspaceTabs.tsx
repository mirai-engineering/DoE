import { type KeyboardEvent, useRef } from 'react'

export type WorkspaceTab<T extends string> = { id: T; label: string }

function nextWorkspaceTab<T extends string>(tabs: WorkspaceTab<T>[], active: T, key: 'ArrowLeft' | 'ArrowRight' | 'Home' | 'End'): T {
  const currentIndex = Math.max(0, tabs.findIndex((tab) => tab.id === active))
  if (key === 'Home') return tabs[0].id
  if (key === 'End') return tabs[tabs.length - 1].id
  const offset = key === 'ArrowLeft' ? -1 : 1
  return tabs[(currentIndex + offset + tabs.length) % tabs.length].id
}

export function WorkspaceTabs<T extends string>({ tabs, activeTab, onChange, ariaLabel, idPrefix }: { tabs: WorkspaceTab<T>[]; activeTab: T; onChange: (tab: T) => void; ariaLabel: string; idPrefix: string }) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([])

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(event.key)) return
    event.preventDefault()
    const nextTab = nextWorkspaceTab(tabs, tabs[index].id, event.key as 'ArrowLeft' | 'ArrowRight' | 'Home' | 'End')
    const nextIndex = tabs.findIndex((tab) => tab.id === nextTab)
    onChange(nextTab)
    tabRefs.current[nextIndex]?.focus()
  }

  return (
    <div className="overflow-x-auto border-b border-white/[0.10]" role="tablist" aria-label={ariaLabel}>
      <div className="flex min-w-max gap-1">
        {tabs.map((tab, index) => {
          const selected = activeTab === tab.id
          return (
            <button
              key={tab.id}
              ref={(element) => { tabRefs.current[index] = element }}
              id={`${idPrefix}-tab-${tab.id}`}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={`${idPrefix}-panel-${tab.id}`}
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
