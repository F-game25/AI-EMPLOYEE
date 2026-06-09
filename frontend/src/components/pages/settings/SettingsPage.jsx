import { useState } from 'react'
import '../SettingsPage.css'
import GeneralTab from './GeneralTab'
import LLMTab from './LLMTab'
import IntegrationsTab from './IntegrationsTab'
import AppearanceTab from './AppearanceTab'
import AdvancedTab from './AdvancedTab'
import SecurityTab from './SecurityTab'
import NotificationsTab from './NotificationsTab'
import BillingTab from './BillingTab'
import TeamTab from './TeamTab'
import ClusterTab from './ClusterTab'

const TABS = ['GENERAL', 'LLM', 'INTEGRATIONS', 'APPEARANCE', 'ADVANCED', 'SECURITY', 'NOTIFICATIONS', 'BILLING & USAGE', 'TEAM & ACCESS', 'CLUSTER']
const TAB_CONTENT = [GeneralTab, LLMTab, IntegrationsTab, AppearanceTab, AdvancedTab, SecurityTab, NotificationsTab, BillingTab, TeamTab, ClusterTab]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState(0)
  const TabComponent = TAB_CONTENT[activeTab]

  return (
    <div className="sp-page">
      <header className="sp-header">
        <div className="sp-title-row">
          <h1 className="sp-title">SYSTEM CONFIGURATION</h1>
          <span className="sp-subtitle">AETERNUS NEXUS — COMMAND CENTER 2095</span>
        </div>
        <nav className="sp-tabs" role="tablist">
          {TABS.map((tab, i) => (
            <button
              key={tab}
              role="tab"
              aria-selected={activeTab === i}
              className={`sp-tab ${activeTab === i ? 'sp-tab--active' : ''}`}
              onClick={() => setActiveTab(i)}
            >
              {tab}
            </button>
          ))}
        </nav>
      </header>

      <main className="sp-body">
        <TabComponent />
      </main>
    </div>
  )
}
