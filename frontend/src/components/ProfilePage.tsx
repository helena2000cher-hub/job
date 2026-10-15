import { FileText, Plus, Save, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'
import { api } from '../api'
import type { Profile } from '../api'
import { useIsDemo } from '../session'
import { Button, EmptyState, Spinner } from './ui'

export function ProfilePage({ onSaved }: { onSaved: () => void }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [saved, setSaved] = useState<string>('') // JSON последней сохранённой версии
  const [status, setStatus] = useState<'loading' | 'missing' | 'ready'>('loading')
  const [busy, setBusy] = useState<'save' | 'rebuild' | null>(null)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const isDemo = useIsDemo()

  const load = (p: Profile) => {
    setProfile(p)
    setSaved(JSON.stringify(p))
    setStatus('ready')
  }

  useEffect(() => {
    api
      .profile()
      .then(load)
      .catch(() => setStatus('missing'))
  }, [])

  const dirty = profile !== null && JSON.stringify(profile) !== saved

  const save = async () => {
    if (!profile) return
    setBusy('save')
    setMessage(null)
    try {
      load(await api.saveProfile(profile))
      setMessage({ tone: 'ok', text: 'Сохранено. Нажмите «Обновить» → «Пересчитать оценки», чтобы лента учла изменения.' })
      onSaved()
    } catch (e) {
      setMessage({ tone: 'error', text: (e as Error).message })
    } finally {
      setBusy(null)
    }
  }

  const rebuild = async () => {
    if (status === 'ready' && !window.confirm('Пересобрать профиль из резюме? Навыки и роли заменятся, настройки поиска сохранятся.')) return
    setBusy('rebuild')
    setMessage(null)
    try {
      load(await api.rebuildProfile())
      setMessage({ tone: 'ok', text: 'Профиль собран из резюме.' })
      onSaved()
    } catch (e) {
      setMessage({ tone: 'error', text: (e as Error).message })
    } finally {
      setBusy(null)
    }
  }

  if (status === 'loading') {
    return (
      <div className="flex justify-center py-20 text-slate-400">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }

  if (status === 'missing' || !profile) {
    return (
      <EmptyState title="Профиль ещё не создан">
        <p>Положите резюме в <code>data/resume.pdf</code> — нейросеть извлечёт из него навыки и роли.</p>
        <Button variant="primary" className="mt-4" onClick={rebuild} disabled={busy !== null}>
          {busy === 'rebuild' ? <Spinner /> : <FileText className="h-4 w-4" />} Создать из резюме
        </Button>
        {message && <p className="mt-3 text-rose-600">{message.text}</p>}
      </EmptyState>
    )
  }

  const set = <K extends keyof Profile>(key: K, value: Profile[K]) => setProfile({ ...profile, [key]: value })
  const setPref = <K extends keyof Profile['preferences']>(key: K, value: Profile['preferences'][K]) =>
    setProfile({ ...profile, preferences: { ...profile.preferences, [key]: value } })

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-24">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Профиль</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            По нему подбираются и оцениваются вакансии. Всё можно поправить вручную.
          </p>
        </div>
        {!isDemo && (
          <Button onClick={rebuild} disabled={busy !== null}>
            {busy === 'rebuild' ? <Spinner /> : <FileText className="h-4 w-4" />} Пересобрать из резюме
          </Button>
        )}
      </div>

      {isDemo && (
        <p className="rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          В демо профиль только для просмотра. Владелец сайта собирает его из своего резюме нейросетью
          и правит здесь же: навыки, роли, поисковые запросы, зарплату и стоп-слова.
        </p>
      )}

      <fieldset disabled={isDemo} className="space-y-6 disabled:opacity-90">
      <Card title="Кто я">
        <Field label="Желаемая должность">
          <input className={INPUT} value={profile.headline} onChange={(e) => set('headline', e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Опыт, лет">
            <input
              type="number"
              min={0}
              step={0.5}
              className={INPUT}
              value={profile.experience_years ?? ''}
              onChange={(e) => set('experience_years', e.target.value === '' ? null : Number(e.target.value))}
            />
          </Field>
          <Field label="Уровень">
            <select className={INPUT} value={profile.seniority ?? ''} onChange={(e) => set('seniority', e.target.value || null)}>
              <option value="">не указан</option>
              <option value="junior">Junior</option>
              <option value="middle">Middle</option>
              <option value="senior">Senior</option>
            </select>
          </Field>
        </div>
        <Field label="О себе (это видит нейросеть при оценке)">
          <textarea
            rows={3}
            className={INPUT}
            value={profile.summary}
            onChange={(e) => set('summary', e.target.value)}
          />
        </Field>
      </Card>

      <Card title="Роли и навыки">
        <Field label="Целевые роли">
          <TagEditor values={profile.target_roles} onChange={(v) => set('target_roles', v)} placeholder="Добавить роль" />
        </Field>
        <Field label={`Навыки (${profile.skills.length})`}>
          <TagEditor values={profile.skills} onChange={(v) => set('skills', v)} placeholder="Добавить навык" />
        </Field>
      </Card>

      <Card title="Что и где искать">
        <Field label="Поисковые запросы" hint="По ним собираются вакансии при «Обновить»">
          <TagEditor values={profile.search_queries} onChange={(v) => set('search_queries', v)} placeholder="Добавить запрос" />
        </Field>
        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={profile.preferences.remote_only}
            onChange={(e) => setPref('remote_only', e.target.checked)}
            className="h-4 w-4 accent-indigo-600"
          />
          <span className="text-sm font-medium">Только удалённая работа</span>
        </label>
        {!profile.preferences.remote_only && (
          <Field label="Регионы, где подходит офис">
            <TagEditor values={profile.preferences.regions} onChange={(v) => setPref('regions', v)} placeholder="Например, Пермский край" />
          </Field>
        )}
        <Field label="Зарплата от, ₽ на руки" hint="Вакансии с потолком ниже отсеиваются">
          <input
            type="number"
            min={0}
            step={5000}
            className={`${INPUT} max-w-xs`}
            value={profile.preferences.salary_min ?? ''}
            onChange={(e) => setPref('salary_min', e.target.value === '' ? null : Number(e.target.value))}
          />
        </Field>
        <Field label="Стоп-слова" hint="Вакансии с этими словами в названии или обязанностях не показываются">
          <TagEditor values={profile.preferences.stop_words} onChange={(v) => setPref('stop_words', v)} placeholder="Добавить слово" tone="danger" />
        </Field>
      </Card>

      </fieldset>

      {message && (
        <p
          className={`rounded-lg px-4 py-3 text-sm ${
            message.tone === 'ok'
              ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300'
              : 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300'
          }`}
        >
          {message.text}
        </p>
      )}

      {dirty && !isDemo && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
            <span className="text-sm text-slate-600 dark:text-slate-300">Есть несохранённые изменения</span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setProfile(JSON.parse(saved))}>Отменить</Button>
              <Button variant="primary" onClick={save} disabled={busy !== null}>
                {busy === 'save' ? <Spinner /> : <Save className="h-4 w-4" />} Сохранить
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const INPUT =
  'w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 placeholder:text-slate-400 focus:ring-2 focus:ring-indigo-500 dark:bg-slate-950 dark:ring-slate-700'

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <h2 className="font-semibold">{title}</h2>
      {children}
    </section>
  )
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">{label}</p>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  )
}

function TagEditor({
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
