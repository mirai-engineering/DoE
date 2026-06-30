import type { ActiveTab } from '../types/doe'

type NavItem = {
  id: ActiveTab
  label: string
  description: string
  badge?: string
  short: string
}

const tabGroups: Array<{
  title: string
  subtitle: string
  items: NavItem[]
}> = [
  {
    title: 'Setup',
    subtitle: 'Dev/admin workflow',
    items: [
      { id: 'data-intake', label: 'Data Intake', description: 'Upload data and create a project.', short: 'DI' },
      { id: 'preprocessing-review', label: 'Preprocessing', description: 'Approve metadata, evidence, and training.', short: 'PR' },
      { id: 'model-quality', label: 'Model Quality', description: 'Confirm trained-model readiness.', badge: 'Product', short: 'MQ' },
      { id: 'data-scientist', label: 'Data Scientist', description: 'Ask scoped questions about data and models.', short: 'DS' },
    ],
  },
  {
    title: 'Design',
    subtitle: 'Scientist workflow',
    items: [
      { id: 'design-studio', label: 'Design Studio', description: 'Explore predictions interactively.', badge: 'Product', short: 'ST' },
      { id: 'batch', label: 'Batch Search', description: 'Rank virtual candidates.', short: 'BS' },
      { id: 'optimization', label: 'Explore & Exploit', description: 'Plan sequential experiments.', short: 'EE' },
    ],
  },
  {
    title: 'Impact',
    subtitle: 'Decision support',
    items: [
      { id: 'impact', label: 'Business Impact', description: 'Estimate time and cost savings.', short: 'BI' },
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
    <aside className="sticky top-5 z-[90] flex max-h-[calc(100vh-2.5rem)] flex-col overflow-hidden rounded-lg border border-slate-700/80 bg-[#080D18] shadow-xl shadow-black/25" aria-label="Primary product navigation">
      <div className={`border-b border-slate-700/70 ${collapsed ? 'p-3' : 'p-4'}`}>
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-3'}`}>
          <img src="/assets/mirai-mark.png" alt="Mirai" className="h-10 w-10 rounded-md border border-slate-600 bg-[#050914] object-cover" />
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-[0.68rem] font-bold uppercase tracking-[0.22em] text-[#74C7F5]">Mirai</p>
              <p className="mt-0.5 text-sm font-semibold tracking-[-0.01em] text-slate-100">AI-guided acceleration</p>
            </div>
          )}
        </div>
        {!collapsed && <p className="mt-4 text-xs leading-5 text-slate-400">Process and product acceleration for industrial R&amp;D.</p>}
        <button
          type="button"
          onClick={() => onCollapsedChange(!collapsed)}
          className={`mt-4 inline-flex h-9 items-center justify-center rounded-md border border-slate-700 bg-[#050914] text-xs font-semibold uppercase tracking-[0.12em] text-slate-300 transition hover:border-slate-500 hover:text-white ${collapsed ? 'w-full px-0' : 'w-full px-3'}`}
          aria-label={collapsed ? 'Show dashboard navigation' : 'Hide dashboard navigation'}
          title={collapsed ? 'Show dashboard' : 'Hide dashboard'}
        >
          {collapsed ? '›' : 'Hide dashboard'}
        </button>
      </div>

      <nav className={`min-h-0 flex-1 space-y-5 overflow-y-auto ${collapsed ? 'p-2' : 'p-2.5'}`} aria-label="Workflow sections">
        {tabGroups.map((group) => (
          <div key={group.title}>
            {!collapsed && (
              <div className="mb-2 px-2">
                <p className="text-[0.68rem] font-bold uppercase tracking-[0.18em] text-slate-500">{group.title}</p>
                <p className="mt-0.5 text-[0.72rem] text-slate-500">{group.subtitle}</p>
              </div>
            )}
            <div className="space-y-1">
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
                    className={`group relative w-full rounded-md border text-left transition ${
                      collapsed ? 'px-2 py-3 text-center' : 'px-3 py-3'
                    } ${
                      itemActive
                        ? 'border-[#2F6BFF]/70 bg-[#10203A] text-white shadow-sm shadow-black/20 before:absolute before:bottom-2 before:left-0 before:top-2 before:w-0.5 before:bg-[#74C7F5]'
                        : 'border-transparent text-slate-300 hover:border-slate-700 hover:bg-[#0D1524] hover:text-white'
                    }`}
                  >
                    {collapsed ? (
                      <span className="block text-xs font-bold tracking-[0.08em]">{item.short}</span>
                    ) : (
                      <>
                        <span className="flex items-center justify-between gap-3">
                          <span className="text-sm font-semibold tracking-[-0.01em]">{item.label}</span>
                          {item.badge && (
                            <span className={`rounded px-2 py-0.5 text-[0.62rem] font-bold uppercase tracking-[0.14em] ${itemActive ? 'bg-[#74C7F5]/15 text-[#BDEAFF]' : 'bg-slate-800 text-[#74C7F5]'}`}>
                              {item.badge}
                            </span>
                          )}
                        </span>
                        <span className={`mt-1 block text-xs leading-5 ${itemActive ? 'text-white/[.72]' : 'text-[#7F8EA8]'}`}>{item.description}</span>
                      </>
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
