import { LockKeyhole } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../api'
import { Button, Spinner } from './ui'

export function LoginPage({ canGoBack, onBack }: { canGoBack: boolean; onBack: () => void }) {
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.login(password)
      // Полная перезагрузка: все экраны заново получат данные уже владельца
      window.location.hash = '#/feed'
      window.location.reload()
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
            <LockKeyhole className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <h1 className="font-semibold">Вход владельца</h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">Личные данные видны только после входа</p>
          </div>
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm font-medium">Пароль</span>
          <input
            type="password"
            autoComplete="current-password"
            autoFocus
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-indigo-500 dark:bg-slate-950 dark:ring-slate-700"
          />
        </label>
        {error && <p className="text-sm text-rose-600">{error}</p>}
        <Button type="submit" variant="primary" className="w-full" disabled={busy || !password}>
          {busy && <Spinner />} Войти
        </Button>
        {canGoBack && (
          <button type="button" onClick={onBack} className="w-full text-center text-sm text-slate-500 hover:text-slate-800 dark:hover:text-slate-200">
            ← Вернуться к демо
          </button>
        )}
      </form>
    </div>
  )
}
