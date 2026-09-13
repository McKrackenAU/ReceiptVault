import { useEffect, useState, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Layout } from '@/components/Layout'
import { api, setCsrf } from '@/lib/api'
import { LoginPage } from '@/pages/LoginPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { AccountsPage } from '@/pages/AccountsPage'
import { JobsPage } from '@/pages/JobsPage'
import { DocumentsPage } from '@/pages/DocumentsPage'
import { DocumentDetailPage } from '@/pages/DocumentDetailPage'
import { ReviewPage } from '@/pages/ReviewPage'
import { DuplicatesPage } from '@/pages/DuplicatesPage'
import { ExportsPage } from '@/pages/ExportsPage'
import { AuditPage } from '@/pages/AuditPage'
import { SettingsPage } from '@/pages/SettingsPage'
import { HelpPage } from '@/pages/HelpPage'

function Guard({ children }: { children: ReactNode }) {
  const [ok, setOk] = useState<boolean | null>(null)
  useEffect(() => {
    api<{ csrf: string }>('/api/v1/auth/me')
      .then((r) => {
        setCsrf(r.csrf)
        setOk(true)
      })
      .catch(() => setOk(false))
  }, [])
  if (ok === null) return <p className="p-8">Checking session…</p>
  if (!ok) return <Navigate to="/login" replace />
  return children
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route
          element={
            <Guard>
              <Layout />
            </Guard>
          }
        >
          <Route path="/" element={<DashboardPage />} />
          <Route path="/accounts" element={<AccountsPage />} />
          <Route path="/jobs" element={<JobsPage />} />
          <Route path="/documents" element={<DocumentsPage />} />
          <Route path="/documents/:id" element={<DocumentDetailPage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/duplicates" element={<DuplicatesPage />} />
          <Route path="/exports" element={<ExportsPage />} />
          <Route path="/audit" element={<AuditPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/help" element={<HelpPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
