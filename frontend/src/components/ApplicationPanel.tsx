import { Check, Copy, Sparkles, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { Application, Stage, Tone } from '../api'
import { useIsDemo } from '../session'
import { STAGES } from '../stages'
import { Button, Spinner } from './ui'

interface Props {
  vacancyId: string
  application: Application | null
  onChange: (application: Application | null) => void
}

const INPUT =
  'w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500 dark:bg-slate-950 dark:ring-slate-700'

/** Вакансия в трекере откликов: этап, дата, контакт, заметки. */
export function ApplicationPanel({ vacancyId, application, onChange }: Props) {
  const [error, setError] = useState<string | null>(null)

  const update = async (patch: Partial<Omit<Application, 'updated_at'>>) => {
    setError(null)
    try {
      onChange(await api.updateApplication(vacancyId, patch))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const remove = async () => {
    if (!window.confirm('Убрать вакансию из трекера? Заметки и письмо удалятся.')) return
    await api.deleteApplication(vacancyId)
    onChange(null)
  }

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Трекер откликов</h3>
        {application && (
          <button
            type="button"
            onClick={remove}
            className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-rose-600"
          >
            <Trash2 className="h-3.5 w-3.5" /> убрать из трекера
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Этап отклика">
        {STAGES.map((s) => {
          const active = application?.stage === s.id
          return (
            <button
              key={s.id}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => update({ stage: s.id as Stage })}
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ring-1 ring-inset transition ${
                active
                  ? 'bg-white text-slate-900 ring-indigo-500 dark:bg-slate-900 dark:text-slate-100'
                  : 'text-slate-600 ring-slate-300 hover:bg-white dark:text-slate-400 dark:ring-slate-700 dark:hover:bg-slate-900'
              }`}
            >
              <span className={`h-2 w-2 rounded-full ${s.dot}`} aria-hidden />
              {s.label}
            </button>
          )
        })}
      </div>

      {!application && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Выберите этап, чтобы добавить вакансию в трекер откликов.
        </p>
      )}

      {application && (
        <div className="grid gap-3 sm:grid-cols-2">
          <Labeled label="Дата отклика">
            <input
              type="date"
              className={INPUT}
              value={application.applied_at ?? ''}
              onChange={(e) => update({ applied_at: e.target.value || null })}
            />
          </Labeled>
          <Labeled label="Контакт">
            <BlurInput
              value={application.contact}
              placeholder="HR, телеграм, почта"
              onCommit={(contact) => update({ contact })}
            />
          </Labeled>
          <div className="sm:col-span-2">
            <Labeled label="Заметки">
              <BlurInput
                multiline
                value={application.notes}
                placeholder="Что обсуждали, следующие шаги…"
                onCommit={(notes) => update({ notes })}
              />
            </Labeled>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-rose-600">{error}</p>}
    </section>
  )
}

/** Сопроводительное письмо под вакансию: генерация, правка, копирование. */
export function CoverLetter({ vacancyId, application, onChange }: Props) {
  const [tone, setTone] = useState<Tone>('business')
  const [wishes, setWishes] = useState('')
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const letter = application?.cover_letter ?? ''
  const isDemo = useIsDemo()

  const generate = async () => {
    setBusy(true)
    setError(null)
    try {
      onChange(await api.coverLetter(vacancyId, tone, wishes))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(letter)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      setError('Не удалось скопировать — выделите текст и нажмите Ctrl+C')
    }
  }

  const save = async (text: string) => {
    try {
      onChange(await api.updateApplication(vacancyId, { cover_letter: text }))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <section className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 dark:border-indigo-500/30 dark:bg-indigo-500/5">
      <div>
        <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">Сопроводительное письмо</h3>
        {!letter && !isDemo && (
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            Нейросеть напишет письмо под эту вакансию по вашему резюме — с акцентом на сильные стороны, чтобы пригласили на собеседование.
          </p>
        )}
      </div>

      {isDemo && !letter && (
        <p className="text-xs text-slate-500 dark:text-slate-400">
          В демо генерация писем отключена (это платный вызов нейросети). Пример письма — у вакансии
          на этапе «Собеседование».
        </p>
      )}

      <div className={isDemo ? 'hidden' : 'space-y-2'}>
        <div className="flex flex-wrap gap-2">
          <select
            value={tone}
            onChange={(e) => setTone(e.target.value as Tone)}
            className={`${INPUT} w-auto`}
            aria-label="Тон письма"
          >
            <option value="business">Деловой тон</option>
            <option value="friendly">Дружелюбный тон</option>
          </select>
          <input
            value={wishes}
            onChange={(e) => setWishes(e.target.value)}
            placeholder="Пожелания (необязательно): упомянуть проект, короче…"
            aria-label="Пожелания к письму"
            className={`${INPUT} min-w-[12rem] flex-1`}
          />
        </div>
        <Button
          variant={letter ? 'secondary' : 'primary'}
          onClick={generate}
          disabled={busy}
          className="w-full sm:w-auto"
        >
          {busy ? <Spinner /> : <Sparkles className="h-4 w-4" />}
          {letter ? 'Написать заново' : 'Создать сопроводительное письмо'}
        </Button>
      </div>
      {busy && <p className="text-xs text-slate-500">Нейросеть пишет письмо, это займёт до минуты…</p>}

      {letter && !busy && (
        <div className="space-y-2">
          {application?.cover_letter_subject && (
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Тема: <span className="text-slate-700 dark:text-slate-300">{application.cover_letter_subject}</span>
            </p>
          )}
          <BlurInput multiline rows={10} value={letter} onCommit={save} />
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-slate-500">Можно править — сохранится автоматически</span>
            <Button onClick={copy}>
              {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
              {copied ? 'Скопировано' : 'Копировать'}
            </Button>
          </div>
        </div>
      )}
      {error && <p className="text-xs text-rose-600">{error}</p>}
    </section>
  )
}

/** Поле, которое сохраняет значение при уходе фокуса, а не на каждую букву. */
function BlurInput({
  value,
  onCommit,
  placeholder,
  multiline = false,
  rows = 3,
}: {
  value: string
  onCommit: (value: string) => void
  placeholder?: string
  multiline?: boolean
  rows?: number
}) {
  const [draft, setDraft] = useState(value)
  const [synced, setSynced] = useState(value)
  if (value !== synced) {
    // значение поменялось снаружи (например, новое письмо) — подхватываем
    setSynced(value)
    setDraft(value)
  }
  const commit = () => draft !== value && onCommit(draft)

  return multiline ? (
    <textarea
      rows={rows}
      value={draft}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      className={`${INPUT} leading-relaxed`}
    />
  ) : (
    <input
      value={draft}
      placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      className={INPUT}
    />
  )
}

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">{label}</span>
      {children}
    </label>
  )
}
