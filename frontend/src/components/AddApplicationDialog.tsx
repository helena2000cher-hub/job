import { Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { api } from '../api'
import type { ManualApplicationOut, Stage } from '../api'
import { useInternals } from '../session'
import { STAGES } from '../stages'
import { Button, Spinner } from './ui'

const INPUT =
  'w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500 dark:bg-slate-950 dark:ring-slate-700'

function today(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Кнопка «Добавить отклик» + окно: отклик, отправленный мимо сайта (например, прямо на hh.ru). */
export function AddApplicationButton({
  onAdded,
  variant = 'secondary',
}: {
  onAdded: (result: ManualApplicationOut) => void
  variant?: 'primary' | 'secondary'
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <Button variant={variant} onClick={() => setOpen(true)}>
        <Plus className="h-4 w-4" /> Добавить отклик
      </Button>
      {open && (
        <AddApplicationDialog
          onClose={() => setOpen(false)}
          onAdded={(r) => {
            setOpen(false)
            onAdded(r)
          }}
        />
      )}
    </>
  )
}

function AddApplicationDialog({
  onClose,
  onAdded,
}: {
  onClose: () => void
  onAdded: (result: ManualApplicationOut) => void
}) {
  const [url, setUrl] = useState('')
  const [title, setTitle] = useState('')
  const [company, setCompany] = useState('')
  const [stage, setStage] = useState<Stage>('applied')
  const [appliedAt, setAppliedAt] = useState(today)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const titleRef = useRef<HTMLInputElement>(null)
  const internals = useInternals()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !busy && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [busy, onClose])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onAdded(await api.addManualApplication({ url, title, company, stage, applied_at: appliedAt || null, notes }))
    } catch (err) {
      const message = (err as Error).message
      setError(message)
      if (message.includes('название')) titleRef.current?.focus()
      setBusy(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center" role="dialog" aria-modal="true" aria-label="Добавить отклик">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={() => !busy && onClose()} />
      <form
        onSubmit={submit}
        className="relative max-h-[92vh] w-full max-w-lg space-y-4 overflow-y-auto rounded-t-2xl bg-white p-5 shadow-2xl sm:rounded-2xl dark:bg-slate-900"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="font-semibold">Добавить отклик</h2>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              Для откликов, отправленных напрямую — например, на hh.ru. Вакансия попадёт в «Мои отклики» и
              статистику.
            </p>
          </div>
          <button type="button" onClick={onClose} className="rounded-lg p-1 text-slate-400 hover:text-slate-700" aria-label="Закрыть">
            <X className="h-5 w-5" />
          </button>
        </div>

        <Labeled label="Ссылка на вакансию" hint={`Название, компания и описание подтянутся сами${internals ? ' (≈ 0,1 ₽)' : ''}`}>
          <input
            type="url"
            inputMode="url"
            autoFocus
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://hh.ru/vacancy/…"
            className={INPUT}
          />
        </Labeled>

        <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-800/50">
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">Ссылки нет или она не загрузится — укажите вручную:</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <input ref={titleRef} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Название вакансии" aria-label="Название вакансии" className={INPUT} />
            <input value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Компания" aria-label="Компания" className={INPUT} />
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Labeled label="Этап">
            <select value={stage} onChange={(e) => setStage(e.target.value as Stage)} className={INPUT}>
              {STAGES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </Labeled>
          <Labeled label="Дата отклика">
            <input type="date" value={appliedAt} onChange={(e) => setAppliedAt(e.target.value)} className={INPUT} />
          </Labeled>
        </div>

        <Labeled label="Заметка (необязательно)">
          <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Например: прислали анкету в чате hh.ru" className={INPUT} />
        </Labeled>

        {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">{error}</p>}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Отмена
          </Button>
          <Button type="submit" variant="primary" disabled={busy || (!url.trim() && !title.trim())}>
            {busy && <Spinner />}
            {busy ? (url.trim() ? 'Загружаю вакансию…' : 'Добавляю…') : 'Добавить'}
          </Button>
        </div>
      </form>
    </div>
  )
}

function Labeled({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">{hint}</span>}
    </label>
  )
}
