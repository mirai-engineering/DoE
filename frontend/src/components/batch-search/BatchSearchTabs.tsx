import { BATCH_SEARCH_TABS, type BatchSearchView } from '../../lib/batchSearchPresentation'
import { WorkspaceTabs } from '../WorkspaceTabs'

export function BatchSearchTabs({ activeTab, onChange }: { activeTab: BatchSearchView; onChange: (tab: BatchSearchView) => void }) {
  return <WorkspaceTabs tabs={BATCH_SEARCH_TABS} activeTab={activeTab} onChange={onChange} ariaLabel="Batch Search workflow" idPrefix="batch-search" />
}

export function BatchSearchPanel({ tab, activeTab, children }: { tab: BatchSearchView; activeTab: BatchSearchView; children: React.ReactNode }) {
  return <section id={`batch-search-panel-${tab}`} role="tabpanel" aria-labelledby={`batch-search-tab-${tab}`} hidden={tab !== activeTab} tabIndex={0}>{children}</section>
}
