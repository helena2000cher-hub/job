import { BriefcaseBusiness, Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'
import { ApiError, api } from './api'
import type { Me } from './api'
import { AnalyticsPage } from './components/AnalyticsPage'
import { FeedPage } from './components/FeedPage'
import { LoginPage, ResetPasswordPage } from './components/LoginPage'
import { PrivacyPage } from './components/PrivacyPage'
import { ProfilePage } from './components/ProfilePage'
import { RefreshButton } from './components/RefreshButton'
import { TrackerPage } from './components/TrackerPage'
import { UserMenu } from './components/UserMenu'
import { Spinner } from './components/ui'
import { SessionContext } from './session'

type Tab = 'feed' | 'tracker' | 'analytics' | 'profile' | 'login' | 'reset' | 'privacy'

const TABS: { id: Tab; label: string }[] = [
  { id: 'feed', label: 'Вакансии' },
  { id: 'tracker', label: 'Отклики' },
  { id: 'analytics', label: 'Аналитика' },
]

function tabFromHash(): Tab {
  const tab = window.location.hash.replace('#/', '').split('?')[0] // #/reset?token=…
  const known: Tab[] = ['tracker', 'analytics', 'profile', 'login', 'reset', 'privacy']
  return known.includes(tab as Tab) ? (tab as Tab) : 'feed'
}

type SessionState = { status: 'loading' } | { status: 'ready'; me: Me } | { status: 'login' } | { status: 'error'; message: string }

export default function App() {
  const [tab, setTab] = useState<Tab>(tabFromHash)
  const [reloadKey, setReloadKey] = useState(0)
  const [dark, toggleDark] = useTheme()
  const [session, setSession] = useState<SessionState>({ status: 'loading' })
  const [person, setPerson] = useState({ name: '', headline: '' })
  const [profileKey, setProfileKey] = useState(0) // +1 после сохранения профиля — обновить шапку

  useEffect(() => {
    const onHash = () => setTab(tabFromHash())
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    api
      .me()
      .then((me) => setSession({ status: 'ready', me }))
      .catch((e) =>
        setSession(
          e instanceof ApiError && e.status === 401 ? { status: 'login' } : { status: 'error', message: e.message },
        ),
      )
  }, [])

  const ready = session.status === 'ready'
  useEffect(() => {
    if (!ready) return
    api
      .profile()
      .then((p) => setPerson({ name: p.name ?? '', headline: p.headline }))
      .catch(() => setPerson({ name: '', headline: '' })) // профиля ещё нет — кружок без буквы
  }, [ready, profileKey])

  const go = (next: Tab) => {
    window.location.hash = `#/${next}`
  }

  const logout = async () => {
    await api.logout()
    window.location.hash = '#/feed'
    window.location.reload()
  }

  const me = session.status === 'ready' ? session.me : null
  const isDemo = me?.role === 'demo'
  const isUser = me?.role === 'user'
  const standalone = tab === 'reset' || tab === 'privacy' // открываются и без входа
  const showLogin = !standalone && (session.status === 'login' || tab === 'login')

  const deleteAccount = async () => {
    if (!window.confirm('Удалить аккаунт? Резюме, профиль, вакансии и отклики удалятся безвозвратно.')) return
    try {
      await api.deleteAccount()
      window.location.hash = '#/feed'
      window.location.reload()
    } catch (e) {
      window.alert((e as Error).message)
    }
  }

  return (
    <SessionContext.Provider value={me ?? { role: 'demo', auth_enabled: true, demo_available: false }}>
      <div className="min-h-screen">
        <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur dark:border-slate-800 dark:bg-slate-950/85">
          <div className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4 sm:gap-6">
            <a href="#/feed" className="hidden items-center gap-2 font-semibold sm:flex">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
                <BriefcaseBusiness className="h-4.5 w-4.5" aria-hidden />
              </span>
              <span className="hidden sm:inline">Job Matcher</span>
            </a>

            {me && (
              <nav className="-mx-1 flex min-w-0 gap-0.5 overflow-x-auto px-1 sm:gap-1" aria-label="Разделы">
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => go(t.id)}
                    aria-current={tab === t.id ? 'page' : undefined}
                    className={`shrink-0 rounded-lg px-2 py-2 text-sm font-medium transition-colors sm:px-3 ${
                      tab === t.id
                        ? 'bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-100'
                        : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </nav>
            )}

            <div className="ml-auto flex items-center gap-1 sm:gap-2">
              <button
                type="button"
                onClick={toggleDark}
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                aria-label={dark ? 'Светлая тема' : 'Тёмная тема'}
                title={dark ? 'Светлая тема' : 'Тёмная тема'}
              >
                {dark ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
              </button>
              {(me?.role === 'owner' || isUser) && <RefreshButton onDone={() => setReloadKey((k) => k + 1)} />}
              {me && (
                <UserMenu
                  name={person.name}
                  headline={person.headline}
                  email={me.email ?? ''}
                  isDemo={isDemo}
                  canRegister={isDemo && (me.registration ?? false)}
                  canLogout={(me.role === 'owner' && me.auth_enabled) || isUser}
                  onDeleteAccount={isUser ? deleteAccount : undefined}
                  active={tab === 'profile'}
                  onProfile={() => go('profile')}
                  onLogin={() => go('login')}
                  onLogout={logout}
                />
              )}
            </div>
          </div>
        </header>

        {isDemo && !showLogin && (
          <div className="border-b border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
            <p className="mx-auto max-w-6xl px-4 py-2.5 text-sm">
              <strong className="font-semibold">Демо-режим.</strong> Кандидат, компании и вакансии вымышлены.
              Можно листать ленту, открывать разборы и двигать карточки в трекере — песочница периодически
              сбрасывается.{' '}
              {me?.registration ? (
                <>
                  Чтобы искать вакансии под своё резюме,{' '}
                  <a href="#/login" className="font-medium underline">
                    зарегистрируйтесь
                  </a>
                  .{' '}
                </>
              ) : (
                'Сбор вакансий и генерация писем доступны только владельцу. '
              )}
              <a href="https://github.com/helena2000cher-hub/job" className="font-medium underline" target="_blank" rel="noreferrer">
                Код на GitHub
              </a>
            </p>
          </div>
        )}

        <main className="mx-auto max-w-6xl px-4 py-6">
          {session.status === 'loading' && (
            <div className="flex justify-center py-20 text-slate-400">
              <Spinner className="h-6 w-6" />
            </div>
          )}
          {session.status === 'error' && (
            <div className="mx-auto max-w-lg rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-800 dark:border-rose-500/30 dark:bg-rose-500/10 dark:text-rose-200">
              <p className="font-semibold">Сервер не отвечает</p>
              <p className="mt-1">{session.message}</p>
              <p className="mt-2 text-rose-700/80 dark:text-rose-300/80">
                Сайт открывается по адресу <strong>localhost:8000</strong> после двойного клика по start.bat.
              </p>
            </div>
          )}
          {showLogin && session.status !== 'loading' && (
            <LoginPage me={me} canGoBack={me !== null} onBack={() => go('feed')} />
          )}
          {tab === 'reset' && session.status !== 'loading' && <ResetPasswordPage />}
          {tab === 'privacy' && <PrivacyPage />}
          {me && !showLogin && !standalone && (
            <>
              {tab === 'feed' && <FeedPage reloadKey={reloadKey} onGoToProfile={() => go('profile')} />}
              {tab === 'tracker' && <TrackerPage onGoToFeed={() => go('feed')} />}
              {tab === 'analytics' && <AnalyticsPage onGoToFeed={() => go('feed')} />}
              {tab === 'profile' && (
                <ProfilePage
                  onSaved={() => {
                    setReloadKey((k) => k + 1)
                    setProfileKey((k) => k + 1)
                  }}
                />
              )}
            </>
          )}
        </main>
      </div>
    </SessionContext.Provider>
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
