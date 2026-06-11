import { useState } from 'react'
import { useAuth } from '../lib/auth'
import { t } from '../i18n/es'
import { UsersTab } from './admin/UsersTab'
import { TenantsTab } from './admin/TenantsTab'
import { SettingsTab } from './admin/SettingsTab'
import { EtlTab } from './admin/EtlTab'

type TabId = 'users' | 'tenants' | 'settings' | 'etl'

export function AdminPage() {
  const { isSuperadmin } = useAuth()
  const [tab, setTab] = useState<TabId>('users')

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: 'users', label: t.admin.tabUsers },
    ...(isSuperadmin
      ? ([
          { id: 'tenants', label: t.admin.tabTenants },
          { id: 'settings', label: t.admin.tabSettings },
          { id: 'etl', label: t.admin.tabEtl },
        ] as Array<{ id: TabId; label: string }>)
      : []),
  ]

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-gray-900">{t.admin.title}</h1>

      <div className="flex flex-wrap gap-1 border-b border-gray-200">
        {tabs.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium transition-colors ${
              tab === id
                ? 'border-primary-600 text-primary-700'
                : 'border-transparent text-gray-500 hover:border-gray-300 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === 'users' && <UsersTab />}
      {tab === 'tenants' && isSuperadmin && <TenantsTab />}
      {tab === 'settings' && isSuperadmin && <SettingsTab />}
      {tab === 'etl' && isSuperadmin && <EtlTab />}
    </div>
  )
}
