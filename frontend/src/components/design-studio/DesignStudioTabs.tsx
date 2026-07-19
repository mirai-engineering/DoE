import { DESIGN_STUDIO_TABS, type DesignStudioView } from '../../lib/designStudioPresentation'
import { WorkspaceTabs } from '../WorkspaceTabs'

export function DesignStudioTabs({ activeTab, onChange }: { activeTab: DesignStudioView; onChange: (tab: DesignStudioView) => void }) {
  return <WorkspaceTabs tabs={DESIGN_STUDIO_TABS} activeTab={activeTab} onChange={onChange} ariaLabel="Design Studio workflows" idPrefix="design-studio" />
}

export function DesignStudioPanel({ tab, activeTab, children }: { tab: DesignStudioView; activeTab: DesignStudioView; children: React.ReactNode }) {
  return <section id={`design-studio-panel-${tab}`} role="tabpanel" aria-labelledby={`design-studio-tab-${tab}`} hidden={activeTab !== tab} tabIndex={0}>{children}</section>
}
