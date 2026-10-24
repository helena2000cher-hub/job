import { Plus, X } from 'lucide-react'
import { useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

// Общие кусочки форм профиля и анкеты резюме

export const INPUT =
  'w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500 dark:bg-slate-950 dark:ring-slate-700'

export function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div>
        <h2 className="font-semibold">{title}</h2>
        {subtitle && <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
      </div>
      {children}
    </section>
  )
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">{label}</p>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  )
}

export function TagEditor({
  values,
  onChange,
  placeholder,
  tone = 'neutral',
}: {
  values: string[]
  onChange: (values: string[]) => void
  placeholder: string
  tone?: 'neutral' | 'danger'
}) {
  const [draft, setDraft] = useState('')

  const add = () => {
    const value = draft.trim()
    if (value && !values.some((v) => v.toLowerCase() === value.toLowerCase())) onChange([...values, value])
    setDraft('')
  }

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault()
      add()
    } else if (e.key === 'Backspace' && draft === '' && values.length > 0) {
      onChange(values.slice(0, -1))
    }
  }

  const tagClass =
    tone === 'danger'
      ? 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300'
      : 'bg-indigo-50 text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300'

  return (
    <div className="flex flex-wrap gap-1.5 rounded-lg p-2 ring-1 ring-inset ring-slate-300 focus-within:ring-2 focus-within:ring-indigo-500 dark:ring-slate-700">
      {values.map((value) => (
        <span key={value} className={`${tagClass} inline-flex items-center gap-1 rounded-md py-0.5 pl-2 pr-1 text-sm`}>
          {value}
          <button
            type="button"
            onClick={() => onChange(values.filter((v) => v !== value))}
            className="rounded p-0.5 opacity-60 hover:opacity-100"
            aria-label={`Удалить «${value}»`}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
      <span className="inline-flex min-w-[10rem] flex-1 items-center gap-1">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={add}
          placeholder={placeholder}
          className="w-full bg-transparent px-1 py-0.5 text-sm outline-none placeholder:text-slate-400"
        />
        {draft && (
          <button type="button" onClick={add} className="text-indigo-600" aria-label="Добавить">
            <Plus className="h-4 w-4" />
          </button>
        )}
      </span>
    </div>
  )
}
