import { BriefcaseBusiness, Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { FeedPage } from './components/FeedPage'
import { ProfilePage } from './components/ProfilePage'
import { RefreshButton } from './components/RefreshButton'

type Tab = 'feed' | 'profile'

const TABS: { id: Tab; label: string }[] = [
  { id: 'feed', label: 'Вакансии' },
  { id: 'profile', label: 'Профиль' },
]

function tabFromHash(): Tab {
  return window.location.hash === '#/profile' ? 'profile' : 'feed'
}

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash)
  const [reloadKey, setReloadKey] = useState(0)
  const [dark, toggleDark] = useTheme()

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const go = (next: Tab) => {
    window.location.hash = `#/${next}`
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur dark:border-slate-800 dark:bg-slate-950/85">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4 sm:gap-6">
          <a href="#/feed" className="flex items-center gap-2 font-semibold">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
              <BriefcaseBusiness className="h-4.5 w-4.5" aria-hidden />
            </span>
            <span className="hidden sm:inline">Job Matcher</span>
          </a>

          <nav className="flex gap-1" aria-label="Разделы">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => go(t.id)}
                aria-current={tab === t.id ? 'page' : undefined}
                className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  tab === t.id
                    ? 'bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
                }`}
              >
                {t.label}
              </button>
            ))}
          </nav>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={toggleDark}
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              aria-label={dark ? 'Светлая тема' : 'Тёмная тема'}
              title={dark ? 'Светлая тема' : 'Тёмная тема'}
            >
              {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
            </button>
            <RefreshButton onDone={() => setReloadKey((k) => k + 1)} />
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        {tab === 'feed' ? (
          <FeedPage reloadKey={reloadKey} onGoToProfile={() => go('profile')} />
        ) : (
          <ProfilePage onSaved={() => setReloadKey((k) => k + 1)} />
        )}
      </main>
    </div>
  )
}

// Тема по умолчанию — как в системе; выбор пользователя запоминается.
function useTheme(): [boolean, () => void] {
  const [dark, setDark] = useState(() => {
    try {
      const stored = localStorage.getItem('jm.theme')
      if (stored) return stored === 'dark'
    } catch {
      /* localStorage недоступен */
    }
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const toggle = () =>
    setDark((d) => {
      try {
        localStorage.setItem('jm.theme', d ? 'light' : 'dark')
      } catch {
        /* ignore */
      }
      return !d
    })

  return [dark, toggle]
}
