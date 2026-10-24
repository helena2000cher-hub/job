import { KeyRound, LockKeyhole, MailCheck, UserPlus } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api } from '../api'
import type { Me } from '../api'
import { Button, Spinner } from './ui'

type Mode = 'login' | 'register' | 'forgot' | 'owner' | 'sent'

const INPUT =
  'w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-indigo-500 dark:bg-slate-950 dark:ring-slate-700'

// Ошибки, с которыми сервер возвращает на #/login после ссылки из письма или входа через Яндекс/VK
const HASH_ERRORS: Record<string, string> = {
  link: 'Ссылка устарела или уже использована. Войдите или запросите новую.',
  oauth: 'Не получилось войти через внешний сервис. Попробуйте ещё раз или войдите по почте.',
}

function hashError(): string | null {
  const query = window.location.hash.split('?')[1] ?? ''
  const code = new URLSearchParams(query).get('error')
  return code ? (HASH_ERRORS[code] ?? null) : null
}

/** Полная перезагрузка: все экраны заново получат данные уже вошедшего человека. */
function enter(tab = 'feed') {
  window.location.hash = `#/${tab}`
  window.location.reload()
}

interface Props {
  me: Me | null
  canGoBack: boolean
  onBack: () => void
}

export function LoginPage({ me, canGoBack, onBack }: Props) {
  const registration = me?.registration ?? false
  const [mode, setMode] = useState<Mode>(registration ? 'login' : 'owner')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [consent, setConsent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(hashError)
  const [sentText, setSentText] = useState('')

  const switchTo = (next: Mode) => {
    setMode(next)
    setError(null)
  }

  const run = async (action: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    run(async () => {
      if (mode === 'owner') {
        await api.login(password)
        enter()
      } else if (mode === 'login') {
        await api.login(password, email)
        enter()
      } else if (mode === 'register') {
        const result = await api.register(email, password, consent)
        setSentText(`Мы отправили письмо на ${result.email}. Откройте ссылку из письма, чтобы закончить регистрацию.`)
        setMode('sent')
      } else if (mode === 'forgot') {
        await api.forgotPassword(email)
        setSentText(`Если ${email.trim()} зарегистрирована, на неё придёт письмо со ссылкой для нового пароля.`)
        setMode('sent')
      }
    })
  }

  const providers = Object.entries(me?.providers ?? {})
  const titles: Record<Mode, [string, string]> = {
    login: ['Вход', 'Ваши резюме, вакансии и отклики'],
    register: ['Регистрация', 'Свой подбор вакансий под ваше резюме'],
    forgot: ['Сброс пароля', 'Пришлём ссылку для нового пароля'],
    owner: ['Вход владельца', 'Личные данные видны только после входа'],
    sent: ['Проверьте почту', 'Письмо может прийти через минуту-другую'],
  }
  const icons: Record<Mode, ReactNode> = {
    login: <LockKeyhole className="h-5 w-5" aria-hidden />,
    register: <UserPlus className="h-5 w-5" aria-hidden />,
    forgot: <KeyRound className="h-5 w-5" aria-hidden />,
    owner: <LockKeyhole className="h-5 w-5" aria-hidden />,
    sent: <MailCheck className="h-5 w-5" aria-hidden />,
  }
  const withEmail = mode === 'login' || mode === 'register' || mode === 'forgot'
  const withPassword = mode === 'login' || mode === 'register' || mode === 'owner'

  return (
    <div className="mx-auto mt-10 max-w-sm">
      <form
        onSubmit={submit}
        className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
            {icons[mode]}
          </span>
          <div>
            <h1 className="font-semibold">{titles[mode][0]}</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">{titles[mode][1]}</p>
          </div>
        </div>

        {mode === 'sent' && <p className="text-sm text-slate-700 dark:text-slate-300">{sentText}</p>}

        {(mode === 'login' || mode === 'register') && providers.length > 0 && (
          <>
            <div className="space-y-2">
              {providers.map(([id, title]) => (
                <ProviderButton key={id} id={id} title={title} />
              ))}
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-400">
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
              или по почте
              <span className="h-px flex-1 bg-slate-200 dark:bg-slate-800" />
            </div>
          </>
        )}

        {withEmail && (
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium">Почта</span>
            <input
              type="email"
              autoComplete="email"
              autoFocus
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={INPUT}
            />
          </label>
        )}
        {withPassword && (
          <label className="block">
            <span className="mb-1.5 flex items-baseline justify-between text-sm font-medium">
              Пароль
              {mode === 'login' && (
                <button type="button" onClick={() => switchTo('forgot')} className="text-xs font-normal text-indigo-600 hover:underline dark:text-indigo-400">
                  Забыли пароль?
                </button>
              )}
            </span>
            <input
              type="password"
              autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
              autoFocus={mode === 'owner'}
              required
              minLength={mode === 'register' ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={INPUT}
            />
            {mode === 'register' && <span className="mt-1 block text-xs text-slate-500">Не короче 8 символов</span>}
          </label>
        )}
        {mode === 'register' && (
          <label className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input
              type="checkbox"
              required
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-indigo-600"
            />
            <span>
              Согласна(-ен) на обработку персональных данных по{' '}
              <a href="#/privacy" target="_blank" className="text-indigo-600 underline dark:text-indigo-400">
                политике конфиденциальности
              </a>
            </span>
          </label>
        )}

        {error && <p className="text-sm text-rose-600">{error}</p>}

        {mode !== 'sent' && (
          <Button type="submit" variant="primary" className="w-full" disabled={busy || (withPassword && !password)}>
            {busy && <Spinner />}{' '}
            {{ login: 'Войти', register: 'Зарегистрироваться', forgot: 'Прислать ссылку', owner: 'Войти', sent: '' }[mode]}
          </Button>
        )}

        <div className="space-y-1.5 text-center text-sm text-slate-500">
          {mode === 'login' && (
            <button type="button" onClick={() => switchTo('register')} className="hover:text-slate-800 dark:hover:text-slate-200">
              Нет аккаунта? <span className="text-indigo-600 dark:text-indigo-400">Зарегистрироваться</span>
            </button>
          )}
          {(mode === 'register' || mode === 'forgot' || mode === 'sent') && registration && (
            <button type="button" onClick={() => switchTo('login')} className="block w-full hover:text-slate-800 dark:hover:text-slate-200">
              Уже есть аккаунт? <span className="text-indigo-600 dark:text-indigo-400">Войти</span>
            </button>
          )}
          {mode === 'owner' && registration && (
            <button type="button" onClick={() => switchTo('login')} className="block w-full hover:text-slate-800 dark:hover:text-slate-200">
              Вход для пользователей
            </button>
          )}
          {canGoBack && (
            <button type="button" onClick={onBack} className="block w-full hover:text-slate-800 dark:hover:text-slate-200">
              ← Вернуться к демо
            </button>
          )}
          {mode === 'login' && (
            <button type="button" onClick={() => switchTo('owner')} className="block w-full text-xs text-slate-400 hover:text-slate-600">
              Вход владельца
            </button>
          )}
        </div>
      </form>
    </div>
  )
}

// Цвета — по правилам оформления кнопок Яндекс ID и VK ID; ссылка ведёт на сервер, он отправит дальше.
const PROVIDER_STYLE: Record<string, { className: string; mark: string }> = {
  yandex: { className: 'bg-slate-900 text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100', mark: 'Я' },
  vk: { className: 'bg-[#0077FF] text-white hover:bg-[#0069e0]', mark: 'VK' },
}

function ProviderButton({ id, title }: { id: string; title: string }) {
  const style = PROVIDER_STYLE[id] ?? { className: 'bg-slate-100 text-slate-900', mark: '' }
  return (
    <a
      href={`/api/auth/oauth/${id}/start`}
      className={`flex w-full items-center justify-center gap-2 rounded-lg px-3 py-2.5 text-sm font-medium transition ${style.className}`}
    >
      {style.mark && (
        <span
          className={`flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[11px] font-bold ${
            id === 'yandex' ? 'bg-[#FC3F1D] text-white' : 'bg-white text-[#0077FF]'
          }`}
          aria-hidden
        >
          {style.mark}
        </span>
      )}
      Войти через {title}
    </a>
  )
}

/** #/reset?token=… — ссылка из письма «Сброс пароля». */
export function ResetPasswordPage() {
  const token = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('token') ?? ''
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(token ? null : 'В ссылке нет кода — откройте её из письма ещё раз')

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.resetPassword(token, password)
      enter()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto mt-10 max-w-sm">
      <form
        onSubmit={submit}
        className="space-y-4 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      >
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300">
            <KeyRound className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <h1 className="font-semibold">Новый пароль</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">Старые входы на других устройствах закроются</p>
          </div>
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Пароль</span>
          <input
            type="password"
            autoComplete="new-password"
            autoFocus
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={INPUT}
          />
          <span className="mt-1 block text-xs text-slate-500">Не короче 8 символов</span>
        </label>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <Button type="submit" variant="primary" className="w-full" disabled={busy || !token || !password}>
          {busy && <Spinner />} Сохранить и войти
        </Button>
      </form>
    </div>
  )
}
