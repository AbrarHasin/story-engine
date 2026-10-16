import { BrowserRouter, Routes, Route, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { BookOpen, User2, Library, Activity, Settings, LogOut, CreditCard } from 'lucide-react'
import { clsx } from 'clsx'
import GeneratePage from '@/pages/GeneratePage'
import PersonalitiesPage from '@/pages/PersonalitiesPage'
import LibraryPage from '@/pages/LibraryPage'
import StoryDetailPage from '@/pages/StoryDetailPage'
import SettingsPage from '@/pages/SettingsPage'
import LoginPage from '@/pages/LoginPage'
import BillingPage from '@/pages/BillingPage'
import BillingReturnPage from '@/pages/BillingReturnPage'
import { useAuthStore } from '@/lib/auth'

export default function App() {
  const token = useAuthStore((s) => s.token)
  const logout = useAuthStore((s) => s.logout)

  return (
    <BrowserRouter>
      <div className="min-h-screen flex flex-col">
        {/* Top nav */}
        <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
          <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6">
            <div className="flex items-center gap-2 font-bold text-sky-400 text-lg mr-4">
              <BookOpen size={20} />
              Story Engine
            </div>
            {token && <nav className="flex gap-1">
              <NavItem to="/" icon={<Activity size={15} />} label="Generate" />
              <NavItem to="/personalities" icon={<User2 size={15} />} label="Personalities" />
              <NavItem to="/library" icon={<Library size={15} />} label="Library" />
              <NavItem to="/billing" icon={<CreditCard size={15} />} label="Billing" />
              <NavItem to="/settings" icon={<Settings size={15} />} label="Settings" />
            </nav>}
            <div className="ml-auto flex items-center gap-3">
              <a
                href={import.meta.env.VITE_LANGFUSE_HOST || 'http://localhost:3000'}
                target="_blank"
                rel="noreferrer"
                className="token-badge hover:border-sky-600 transition-colors"
              >
                Traces ↗
              </a>
              {token && (
                <button
                  type="button"
                  onClick={logout}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
                >
                  <LogOut size={15} />
                  Log out
                </button>
              )}
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth />}>
              <Route path="/" element={<GeneratePage />} />
              <Route path="/personalities" element={<PersonalitiesPage />} />
              <Route path="/library" element={<LibraryPage />} />
              <Route path="/stories/:id" element={<StoryDetailPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/billing" element={<BillingPage />} />
              <Route path="/billing/success" element={<BillingReturnPage outcome="success" />} />
              <Route path="/billing/fail" element={<BillingReturnPage outcome="fail" />} />
              <Route path="/billing/cancel" element={<BillingReturnPage outcome="cancel" />} />
            </Route>
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

/** No token (never logged in, logged out, or a 401) -> /login, then back here. */
function RequireAuth() {
  const token = useAuthStore((s) => s.token)
  const location = useLocation()
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  return <Outlet />
}

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
          isActive
            ? 'bg-sky-900/50 text-sky-400'
            : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800',
        )
      }
    >
      {icon}
      {label}
    </NavLink>
  )
}
