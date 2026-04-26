import type { ActiveTab } from '../types/doe'
import { tabs } from '../types/doe'

export function Tabs({
  activeTab,
  onTabChange,
}: {
  activeTab: ActiveTab
  onTabChange: (tab: ActiveTab) => void
}) {
  return (
    <nav className="mt-8 flex flex-wrap gap-2" aria-label="Primary">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onTabChange(tab.id)}
          className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
            activeTab === tab.id
              ? 'bg-slate-950 text-white shadow-lg shadow-slate-950/20'
              : 'border border-slate-900/10 bg-white/70 text-slate-600 hover:bg-white'
          }`}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  )
}
