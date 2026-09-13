import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api } from '@/lib/api'

const links = [
  ['/', 'Dashboard'],
  ['/accounts', 'Inbox accounts'],
  ['/jobs', 'Scan jobs'],
  ['/documents', 'Documents'],
  ['/review', 'Needs review'],
  ['/duplicates', 'Duplicates'],
  ['/exports', 'Exports'],
  ['/audit', 'Audit log'],
  ['/settings', 'Settings'],
  ['/help', 'Help'],
]

export function Layout() {
  const navigate = useNavigate()
  async function logout() {
    await api('/api/v1/auth/logout', { method: 'POST' })
    navigate('/login')
  }
  return (
    <div className="min-h-screen md:grid md:grid-cols-[240px_1fr]">
      <aside className="bg-pine-deep text-paper px-4 py-6">
        <p className="font-serif text-2xl">ReceiptVault</p>
        <p className="mt-1 text-xs text-paper/70">Private evidence locker</p>
        <nav className="mt-8 flex flex-col gap-1" aria-label="Main">
          {links.map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `rounded-md px-3 py-2 text-sm ${isActive ? 'bg-white/15 font-semibold' : 'hover:bg-white/10'}`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <ButtonLogout onClick={logout} />
      </aside>
      <main className="min-w-0 p-4 md:p-8">
        <Outlet />
      </main>
    </div>
  )
}

function ButtonLogout({ onClick }: { onClick: () => void }) {
  return (
    <button className="mt-8 text-sm text-paper/80 underline" onClick={onClick}>
      Log out
    </button>
  )
}

export function Disclaimer() {
  return (
    <p className="disclaimer mb-4" role="note">
      ReceiptVault organises evidence and suggests review labels. It is not tax or legal advice and must not be treated as a
      final claim decision. See Help for current ATO record-keeping guidance.
    </p>
  )
}
