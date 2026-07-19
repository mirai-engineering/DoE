import { MODEL_QUALITY_TABS, type ModelQualityView } from '../../lib/modelQualityPresentation'
import { WorkspaceTabs } from '../WorkspaceTabs'

export function ModelQualityTabs({ activeTab, onChange }: { activeTab: ModelQualityView; onChange: (tab: ModelQualityView) => void }) {
  return <WorkspaceTabs tabs={MODEL_QUALITY_TABS} activeTab={activeTab} onChange={onChange} ariaLabel="Model Quality sections" idPrefix="model-quality" />
}

export function ModelQualityPanel({ tab, activeTab, children }: { tab: ModelQualityView; activeTab: ModelQualityView; children: React.ReactNode }) {
  return <section id={`model-quality-panel-${tab}`} role="tabpanel" aria-labelledby={`model-quality-tab-${tab}`} hidden={activeTab !== tab} tabIndex={0}>{children}</section>
}
