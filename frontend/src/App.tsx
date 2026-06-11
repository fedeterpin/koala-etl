import { Navigate, Route, Routes } from 'react-router-dom'
import { Layout, RequireAdmin, RequireAuth } from './components/Layout'
import { LoginPage } from './pages/Login'
import { DashboardUsuarios } from './pages/dashboard/Usuarios'
import { DashboardClientes } from './pages/dashboard/Clientes'
import { DashboardSiniestros } from './pages/dashboard/Siniestros'
import { ConversacionesPage } from './pages/Conversaciones'
import { DescargasFallidasPage } from './pages/DescargasFallidas'
import { BackupsPage } from './pages/Backups'
import { AdminPage } from './pages/Admin'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/dashboard/usuarios" replace />} />
          <Route path="/dashboard/usuarios" element={<DashboardUsuarios />} />
          <Route path="/dashboard/clientes" element={<DashboardClientes />} />
          <Route path="/dashboard/siniestros" element={<DashboardSiniestros />} />
          <Route path="/conversaciones" element={<ConversacionesPage />} />
          <Route element={<RequireAdmin />}>
            <Route path="/descargas-fallidas" element={<DescargasFallidasPage />} />
            <Route path="/backups" element={<BackupsPage />} />
            <Route path="/admin" element={<AdminPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard/usuarios" replace />} />
        </Route>
      </Route>
    </Routes>
  )
}
