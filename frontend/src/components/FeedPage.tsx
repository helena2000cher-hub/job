import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { Application, Feed, FeedView, Mark } from '../api'
import { formatDateTime, sourceLabel } from '../format'
import { EmptyState, Spinner } from './ui'
import { VacancyCard } from './VacancyCard'
import { VacancyDrawer } from './VacancyDrawer'

const SCORE_FILTERS = [
  { value: 0, label: 'Все' },
  { value: 60, label: '60+' },
  { value: 80, label: '80+' },
]

const VIEWS: { value: FeedView; label: string }[] = [
  { value: 'all', label: 'Лента' },
  { value: 'saved', label: 'В трекере' },
  { value: 'hidden', label: 'Скрытые' },
]

interface Props {
  reloadKey: number // меняется после «Обновить» — лента перезагружается
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

  return (
    <div className="grid gap-6 lg:grid-cols-[15rem_1fr]">
      <aside className="space-y-5 lg:sticky lg:top-20 lg:self-start">
        <FilterGroup label="Показать">
          <Segmented options={VIEWS} value={view} onChange={setView} />
        </FilterGroup>

        <FilterGroup label="Минимальный балл">
          <Segmented options={SCORE_FILTERS} value={minScore} onChange={changeMinScore} />
        </FilterGroup>

        <FilterGroup label="Источник">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value)}
            className="w-full rounded-lg border-0 bg-white px-3 py-2 text-sm ring-1 ring-inset ring-slate-300 focus:ring-2 focus:ring-indigo-500 dark:bg-slate-900 dark:ring-slate-700"
          >
            <option value="">Все источники</option>
            {Object.entries(feed?.sources ?? {}).map(([name, count]) => (
              <option key={name} value={name}>
                {sourceLabel(name)} ({count})
              </option>
            ))}
          </select>
        </FilterGroup>

        {feed && (
          <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
            Оценено {feed.scored} из {feed.total_vacancies} вакансий в базе.
            <br />
            Последний сбор: {formatDateTime(feed.last_fetched_at)}
          </p>
        )}
      </aside>

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

        {feed?.profile_ready && feed.items.length === 0 && (
          <EmptyState title={view === 'all' ? 'Подходящих вакансий пока нет' : 'Здесь пусто'}>
            {view === 'all' &&
              (feed.scored === 0
                ? 'Нажмите «Обновить», чтобы собрать и оценить вакансии под ваш профиль.'
                : 'Попробуйте снизить минимальный балл или выбрать другой источник.')}
          </EmptyState>
        )}

        {feed && feed.items.length > 0 && (
          <>
            <p className="mb-3 text-sm text-slate-500 dark:text-slate-400">
              {feed.items.length} {plural(feed.items.length, 'вакансия', 'вакансии', 'вакансий')}
            </p>
            <div className="space-y-3">
              {feed.items.map((item) => (
                <VacancyCard
                  key={item.id}
                  item={item}
                  onOpen={() => setOpenId(item.id)}
                  onMark={(status) => mark(item.id, status)}
                />
              ))}
            </div>
          </>
        )}
      </section>

      {openId && <VacancyDrawer
          key={openId}
          id={openId}
          onClose={closeDrawer}
          onMark={mark}
          onApplicationChange={applicationChanged}
        />}
    </div>
  )
}

function FilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      {children}
    </div>
  )
}

function Segmented<T extends string | number>({
  options,
  value,
  onChange,
}: {
  options: { value: T; label: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="flex rounded-lg bg-slate-200/70 p-0.5 dark:bg-slate-800" role="radiogroup">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`flex-1 rounded-md px-2 py-1.5 text-sm font-medium transition ${
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
