import { t } from '../../i18n/es'
import { ContactsDashboard } from './ContactsDashboard'

export function DashboardSiniestros() {
  return (
    <ContactsDashboard
      context="siniestros"
      title={t.dashboards.siniestrosTitle}
      subtitle={t.dashboards.siniestrosSubtitle}
      withGranularity
    />
  )
}
