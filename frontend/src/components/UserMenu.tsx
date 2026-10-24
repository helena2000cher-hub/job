import { LogIn, LogOut, Trash2, UserRound } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'

interface Props {
  name: string
  headline: string
  email: string
  isDemo: boolean
  canRegister: boolean // гость в демо может зарегистрироваться
  canLogout: boolean
  active: boolean // открыта страница профиля
  onProfile: () => void
  onLogin: () => void
  onLogout: () => void
  onDeleteAccount?: () => void // только у пользователя: удалить аккаунт и данные
}

/** Кружок пользователя справа в шапке и выпадающее меню: профиль, вход/выход. */
export function UserMenu({
  name,
  headline,
  email,
  isDemo,
  canRegister,
  canLogout,
  active,
  onProfile,
  onLogin,
  onLogout,
  onDeleteAccount,
}: Props) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const initial = (name.trim() || email).charAt(0).toUpperCase()

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const pick = (action: () => void) => () => {
    setOpen(false)
    action()
  }

  return (
    <div className="relative" ref={root}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={name ? `Меню пользователя: ${name}` : 'Меню пользователя'}
        title={name || 'Профиль'}
        className={`flex h-9 w-9 items-center justify-center rounded-full text-sm font-semibold ring-2 transition ${
          active
            ? 'bg-indigo-600 text-white ring-indigo-300 dark:ring-indigo-500/50'
            : 'bg-indigo-100 text-indigo-700 ring-transparent hover:ring-indigo-200 dark:bg-indigo-500/20 dark:text-indigo-200 dark:hover:ring-indigo-500/40'
        }`}
      >
        {initial || <UserRound className="h-5 w-5" aria-hidden />}
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-40 mt-2 w-64 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="border-b border-slate-100 px-4 py-3 dark:border-slate-800">
            <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">{name || email || 'Без имени'}</p>
            {email && name && <p className="truncate text-xs text-slate-500 dark:text-slate-400">{email}</p>}
            {headline && <p className="mt-0.5 line-clamp-2 text-xs text-slate-500 dark:text-slate-400">{headline}</p>}
          </div>
          <div className="p-1.5">
            <MenuItem icon={<UserRound className="h-4 w-4" />} onClick={pick(onProfile)}>
              Мой профиль
            </MenuItem>
            {isDemo && (
              <MenuItem icon={<LogIn className="h-4 w-4" />} onClick={pick(onLogin)}>
                {canRegister ? 'Войти или зарегистрироваться' : 'Войти как владелец'}
              </MenuItem>
            )}
            {canLogout && (
              <MenuItem icon={<LogOut className="h-4 w-4" />} onClick={pick(onLogout)}>
                Выйти
              </MenuItem>
            )}
            {onDeleteAccount && (
              <MenuItem icon={<Trash2 className="h-4 w-4" />} onClick={pick(onDeleteAccount)}>
                Удалить аккаунт
              </MenuItem>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function MenuItem({ icon, onClick, children }: { icon: ReactNode; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
    >
      <span className="text-slate-400" aria-hidden>
        {icon}
      </span>
      {children}
    </button>
  )
}
