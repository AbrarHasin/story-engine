import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { BookOpen, User2, Library, Activity, Settings } from 'lucide-react'
import { clsx } from 'clsx'
import GeneratePage from '@/pages/GeneratePage'
import PersonalitiesPage from '@/pages/PersonalitiesPage'
import LibraryPage from '@/pages/LibraryPage'
import StoryDetailPage from '@/pages/StoryDetailPage'
import SettingsPage from '@/pages/SettingsPage'

export default function App() {
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
            <nav className="flex gap-1">
              <NavItem to="/" icon={<Activity size={15} />} label="Generate" />
              <NavItem to="/personalities" icon={<User2 size={15} />} label="Personalities" />
              <NavItem to="/library" icon={<Library size={15} />} label="Library" />
              <NavItem to="/settings" icon={<Settings size={15} />} label="Settings" />
            </nav>
            <div className="ml-auto">
              <a
                href={import.meta.env.VITE_LANGFUSE_HOST || 'http://localhost:3000'}
                target="_blank"
                rel="noreferrer"
                className="token-badge hover:border-sky-600 transition-colors"
              >
                Traces ↗
              </a>
            </div>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
          <Routes>
            <Route path="/" element={<GeneratePage />} />
            <Route path="/personalities" element={<PersonalitiesPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/stories/:id" element={<StoryDetailPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
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
