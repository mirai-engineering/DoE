import type { ActiveTab } from '../types/doe'

type NavItem = {
  id: ActiveTab
  label: string
  short: string
}

const tabGroups: Array<{
  title: string
  items: NavItem[]
}> = [
  {
    title: 'Setup',
    items: [
      { id: 'knowledge-intake', label: 'Knowledge Intake', short: 'KI' },
      { id: 'data-intake', label: 'Data Intake', short: 'DI' },
      { id: 'preprocessing-review', label: 'Preprocessing', short: 'PR' },
      { id: 'model-quality', label: 'Model Quality', short: 'MQ' },
      { id: 'data-scientist', label: 'Data Scientist', short: 'DS' },
    ],
  },
  {
    title: 'Design',
    items: [
      { id: 'design-studio', label: 'Design Studio', short: 'ST' },
      { id: 'batch', label: 'Batch Search', short: 'BS' },
      { id: 'optimization', label: 'Explore & Exploit', short: 'EE' },
    ],
  },
  {
    title: 'Impact',
    items: [
      { id: 'impact', label: 'Business Impact', short: 'BI' },
    ],
  },
]

export function Tabs({
  activeTab,
  onTabChange,
  collapsed,
  onCollapsedChange,
}: {
  activeTab: ActiveTab
  onTabChange: (tab: ActiveTab) => void
  collapsed: boolean
  onCollapsedChange: (collapsed: boolean) => void
}) {
  return (
    <aside className="sticky top-4 z-[90] flex max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-xl border border-white/[0.06] bg-[#07101D]/86 shadow-[0_10px_30px_rgba(2,6,23,0.16)] backdrop-blur-xl" aria-label="Primary product navigation">
      <div className={`border-b border-white/[0.06] ${collapsed ? 'p-3' : 'p-4'}`}>
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
          <img src="/assets/mirai-mark.png" alt="Mirai" className="h-9 w-9 rounded-md bg-[#050914] object-cover ring-1 ring-white/10" />
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-[0.68rem] font-semibold uppercase tracking-[0.16em] text-[#74C7F5]">Mirai</p>
              <p className="mt-0.5 text-sm font-medium tracking-[-0.01em] text-slate-100">AI-guided acceleration</p>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => onCollapsedChange(!collapsed)}
          className={`mt-3 inline-flex h-8 items-center justify-center rounded-md text-xs font-medium text-[#9FB0C8] transition hover:bg-white/[0.045] hover:text-white ${collapsed ? 'w-full px-0' : 'w-full px-3'}`}
          aria-label={collapsed ? 'Show dashboard navigation' : 'Hide dashboard navigation'}
          title={collapsed ? 'Show dashboard' : 'Hide dashboard'}
        >
          {collapsed ? '›' : 'Collapse'}
        </button>
      </div>

      <nav className={`min-h-0 flex-1 overflow-y-auto ${collapsed ? 'space-y-4 p-2' : 'space-y-5 p-3'}`} aria-label="Workflow sections">
        {tabGroups.map((group) => (
          <div key={group.title}>
            {!collapsed && (
              <p className="mb-1.5 px-2 text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-slate-500">{group.title}</p>
            )}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const itemActive = item.id === activeTab
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onTabChange(item.id)}
                    aria-current={itemActive ? 'page' : undefined}
                    aria-label={collapsed ? item.label : undefined}
                    title={collapsed ? item.label : undefined}
                    className={`group relative w-full rounded-md border border-transparent text-left transition ${
                      collapsed ? 'px-2 py-2.5 text-center' : 'px-3 py-2.5'
                    } ${
                      itemActive
                        ? 'bg-[#2F6BFF]/10 text-white before:absolute before:bottom-2 before:left-0 before:top-2 before:w-0.5 before:rounded-full before:bg-[#74C7F5]'
                        : 'text-[#C7D2E4] hover:bg-white/[0.035] hover:text-white'
                    }`}
                  >
                    {collapsed ? (
                      <span className={`block text-xs font-semibold tracking-[0.04em] ${itemActive ? 'text-[#BDEAFF]' : 'text-[#9FB0C8]'}`}>{item.short}</span>
                    ) : (
                      <span className={`text-sm tracking-[-0.01em] ${itemActive ? 'font-semibold' : 'font-medium'}`}>{item.label}</span>
                    )}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  )
}
