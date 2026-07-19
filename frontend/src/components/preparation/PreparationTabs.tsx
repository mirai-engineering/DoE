import type { PreparationTab } from '../../lib/preparationPresentation'
import { WorkspaceTabs } from '../WorkspaceTabs'

const tabs: Array<{ id: PreparationTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'variables', label: 'Variables' },
  { id: 'preprocessing', label: 'Preprocessing' },
  { id: 'training', label: 'Training' },
  { id: 'ask-mirai', label: 'Ask Mirai' },
]

export function PreparationTabs({ activeTab, onChange }: { activeTab: PreparationTab; onChange: (tab: PreparationTab) => void }) {
  return <WorkspaceTabs tabs={tabs} activeTab={activeTab} onChange={onChange} ariaLabel="Project preparation sections" idPrefix="preparation" />
}
