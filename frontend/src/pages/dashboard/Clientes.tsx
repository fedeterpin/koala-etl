import { t } from '../../i18n/es'
import { ContactsDashboard } from './ContactsDashboard'

export function DashboardClientes() {
  return (
    <ContactsDashboard
      context="general"
      title={t.dashboards.clientesTitle}
      subtitle={t.dashboards.clientesSubtitle}
    />
  )
}
