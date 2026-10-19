import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { Application, Feed, FeedView, Mark } from '../api'
import { formatDateTime, sourceLabel } from '../format'
import { EmptyState, Spinner } from './ui'
import { VacancyCard } from './VacancyCard'
import { VacancyDrawer } from './VacancyDrawer'

const SCORE_FILTERS = [
  { value: 0, label: 'Все баллы' },
  { value: 60, label: 'от 60' },
  { value: 80, label: 'от 80' },
]

const VIEWS: { value: FeedView; label: string }[] = [
  { value: 'all', label: 'Подобранные' },
  { value: 'saved', label: 'В трекере' },
  { value: 'hidden', label: 'Скрытые' },
]

interface Props {
  reloadKey: number // меняется после «Найти вакансии» — лента перезагружается
  onGoToProfile: () => void
}

export function FeedPage({ reloadKey, onGoToProfile }: Props) {
  const [minScore, setMinScore] = useState(() => Number(localStorageGet('minScore') ?? 0))
  const [source, setSource] = useState('')
  const [view, setView] = useState<FeedView>('all')
  const [feed, setFeed] = useState<Feed | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .feed({ minScore, source, view })
      .then((f) => {
        if (cancelled) return
        setFeed(f)
        setError(null)
      })
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [minScore, source, view, reloadKey])

  const changeMinScore = (value: number) => {
    setMinScore(value)
    localStorageSet('minScore', String(value))
  }

  const mark = useCallback(
    (id: string, status: Mark) => {
      // Сразу меняем ленту, не дожидаясь сервера: скрытая карточка исчезает из «Ленты» и т.п.
      setFeed((f) => {
        if (!f) return f
        const stays = (s: Mark) => (view === 'all' ? s !== 'hidden' : s === view)
        const items = f.items
          .map((i) => (i.id === id ? { ...i, mark: status } : i))
          .filter((i) => i.id !== id || stays(status))
        return { ...f, items }
      })
      api.mark(id, status).catch((e: Error) => setError(e.message))
    },
    [view],
  )

  const applicationChanged = useCallback(
    (id: string, application: Application | null) =>
      setFeed((f) => {
        if (!f) return f
        const items = f.items
          .map((i) =>
            i.id === id
              ? {
                  ...i,
                  stage: application?.stage ?? null,
                  mark: (i.mark === 'hidden' ? 'hidden' : application ? 'saved' : null) as Mark,
                }
              : i,
          )
          .filter((i) => !(view === 'saved' && i.id === id && !application))
        return { ...f, items }
      }),
    [view],
  )

  const closeDrawer = useCallback(() => setOpenId(null), [])

  const items = feed?.items ?? []
  const counts = {
    great: items.filter((i) => (i.score ?? 0) >= 80).length,
    good: items.filter((i) => (i.score ?? 0) >= 60 && (i.score ?? 0) < 80).length,
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Вакансии под ваш профиль</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Нейросеть сравнила каждую вакансию с вашими навыками: сверху — самые подходящие. Откройте
            вакансию, чтобы увидеть, чего не хватает, и создать сопроводительное письмо.
          </p>
        </div>
        {feed && (
          <p className="text-xs text-slate-500 dark:text-slate-400">
            В базе {feed.total_vacancies} · оценено {feed.scored} · сбор: {formatDateTime(feed.last_fetched_at)}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-slate-200 bg-white p-2 dark:border-slate-800 dark:bg-slate-900">
        <Segmented options={VIEWS} value={view} onChange={setView} label="Какие вакансии показать" />
        <Segmented options={SCORE_FILTERS} value={minScore} onChange={changeMinScore} label="Минимальный балл" />
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          aria-label="Источник"
          className="rounded-lg border-0 bg-slate-100 px-3 py-1.5 text-sm focus:ring-2 focus:ring-indigo-500 dark:bg-slate-800"
        >
          <option value="">Все сайты</option>
          {Object.entries(feed?.sources ?? {}).map(([name, count]) => (
            <option key={name} value={name}>
              {sourceLabel(name)} ({count})
            </option>
          ))}
        </select>
      </div>

      <section aria-live="polite" className="min-w-0">
        {error && (
          <p className="mb-4 rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
            {error}
          </p>
        )}

        {!feed && !error && (
          <div className="flex justify-center py-20 text-slate-400">
            <Spinner className="h-6 w-6" />
          </div>
        )}

        {feed && !feed.profile_ready && (
          <EmptyState title="Профиль ещё не создан">
            Положите резюме в <code>data/resume.pdf</code> и создайте профиль на вкладке{' '}
            <button type="button" className="text-indigo-600 underline dark:text-indigo-400" onClick={onGoToProfile}>
              «Профиль»
            </button>
            .
          </EmptyState>
        )}

        {feed?.profile_ready && items.length === 0 && (
          <EmptyState title={view === 'all' ? 'Подходящих вакансий пока нет' : 'Здесь пусто'}>
            {view === 'all' &&
              (feed.scored === 0
                ? 'Нажмите «Найти вакансии» справа вверху — сервис соберёт вакансии по вашим навыкам и оценит их.'
                : 'Попробуйте показать все баллы или выбрать другой сайт.')}
          </EmptyState>
        )}

        {items.length > 0 && (
          <>
            <p className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-slate-600 dark:text-slate-300">
              <span>
                {items.length} {plural(items.length, 'вакансия', 'вакансии', 'вакансий')}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-emerald-500" aria-hidden /> подходят: {counts.great}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-amber-500" aria-hidden /> можно откликнуться: {counts.good}
              </span>
            </p>
            <div className="space-y-3">
              {items.map((item) => (
                <VacancyCard
                  key={item.id}
                  item={item}
                  onOpen={() => setOpenId(item.id)}
                  onMark={(status) => mark(item.id, status)}
                  onApplicationChange={(application) => applicationChanged(item.id, application)}
                />
              ))}
            </div>
          </>
        )}
      </section>

      {openId && (
        <VacancyDrawer
          key={openId}
          id={openId}
          onClose={closeDrawer}
          onMark={mark}
          onApplicationChange={applicationChanged}
        />
      )}
    </div>
  )
}

function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div className="flex rounded-lg bg-slate-100 p-0.5 dark:bg-slate-800" role="radiogroup" aria-label={label}>
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1 text-sm font-medium transition ${
            o.value === value
              ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-950 dark:text-slate-100'
              : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10
  const mod100 = n % 100
  if (mod10 === 1 && mod100 !== 11) return one
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few
  return many
}

// localStorage может быть недоступен (приватный режим) — тогда просто не запоминаем фильтр
function localStorageGet(key: string): string | null {
  try {
    return localStorage.getItem(`jm.${key}`)
  } catch {
    return null
  }
}

function localStorageSet(key: string, value: string) {
  try {
    localStorage.setItem(`jm.${key}`, value)
  } catch {
    /* ignore */
  }
}
