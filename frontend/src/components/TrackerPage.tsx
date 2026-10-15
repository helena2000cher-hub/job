import { Mail } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import type { DragEvent } from 'react'
import { api } from '../api'
import type { Application, Mark, Stage, TrackerItem } from '../api'
import { formatDate } from '../format'
import { STAGES } from '../stages'
import { EmptyState, ScoreBadge, Spinner } from './ui'
import { VacancyDrawer } from './VacancyDrawer'

export function TrackerPage({ onGoToFeed }: { onGoToFeed: () => void }) {
  const [items, setItems] = useState<TrackerItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState<Stage | null>(null)

  useEffect(() => {
    api
      .applications()
      .then(setItems)
      .catch((e: Error) => setError(e.message))
  }, [])

  const applyChange = useCallback((id: string, application: Application | null) => {
    setItems((list) =>
      (list ?? [])
        .map((i) => (i.id === id && application ? { ...i, application, stage: application.stage } : i))
        .filter((i) => i.id !== id || application !== null),
    )
  }, [])

  const move = async (id: string, stage: Stage) => {
    const item = items?.find((i) => i.id === id)
    if (!item || item.application.stage === stage) return
    applyChange(id, { ...item.application, stage }) // сразу двигаем карточку
    try {
      applyChange(id, await api.updateApplication(id, { stage }))
    } catch (e) {
      applyChange(id, item.application) // откат
      setError((e as Error).message)
    }
  }

  const onDrop = (stage: Stage) => (e: DragEvent) => {
    e.preventDefault()
    setDragOver(null)
    const id = e.dataTransfer.getData('text/plain')
    if (id) void move(id, stage)
  }

  // Скрытие из карточки трекера не убирает отклик — просто синхронизируем ленту на сервере
  const mark = useCallback((id: string, status: Mark) => {
    api.mark(id, status).catch((e: Error) => setError(e.message))
  }, [])
  const closeDrawer = useCallback(() => setOpenId(null), [])

  if (!items && !error) {
    return (
      <div className="flex justify-center py-20 text-slate-400">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }

  const total = items?.length ?? 0
  const sentThisWeek =
    items?.filter((i) => i.application.applied_at && daysAgo(i.application.applied_at) < 7).length ?? 0

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">Отклики</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Перетаскивайте карточки между колонками. В карточке — заметки и сопроводительное письмо.
          </p>
        </div>
        {total > 0 && (
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Всего: {total} · отправлено за неделю: {sentThisWeek}
          </p>
        )}
      </div>

      {error && (
        <p className="rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">
          {error}
        </p>
      )}

      {total === 0 ? (
        <EmptyState title="Трекер пока пуст">
          Добавляйте вакансии из{' '}
          <button type="button" className="text-indigo-600 underline dark:text-indigo-400" onClick={onGoToFeed}>
            ленты
          </button>{' '}
          значком закладки или выбором этапа в карточке вакансии.
        </EmptyState>
      ) : (
        <div className="-mx-4 overflow-x-auto px-4 pb-2">
          <div className="grid min-w-[60rem] grid-cols-5 gap-3">
            {STAGES.map((stage) => {
              const column = items!.filter((i) => i.application.stage === stage.id)
              return (
                <section
                  key={stage.id}
                  aria-label={stage.label}
                  onDragOver={(e) => {
                    e.preventDefault()
                    setDragOver(stage.id)
                  }}
                  onDragLeave={() => setDragOver((s) => (s === stage.id ? null : s))}
                  onDrop={onDrop(stage.id)}
                  className={`flex min-h-[16rem] flex-col rounded-2xl p-2 transition-colors ${
                    dragOver === stage.id
                      ? 'bg-indigo-100 ring-2 ring-indigo-400 dark:bg-indigo-500/15'
                      : 'bg-slate-100 dark:bg-slate-900/60'
                  }`}
                >
                  <h2 className="flex items-center gap-2 px-2 py-1.5 text-sm font-semibold text-slate-700 dark:text-slate-200">
                    <span className={`h-2 w-2 rounded-full ${stage.dot}`} aria-hidden />
                    {stage.label}
                    <span className="ml-auto text-xs font-normal text-slate-500">{column.length}</span>
                  </h2>
                  <div className="flex flex-1 flex-col gap-2">
                    {column.map((item) => (
                      <TrackerCard
                        key={item.id}
                        item={item}
                        onOpen={() => setOpenId(item.id)}
                        onMove={(s) => move(item.id, s)}
                      />
                    ))}
                  </div>
                </section>
              )
            })}
          </div>
        </div>
      )}

      {openId && (
        <VacancyDrawer
          key={openId}
          id={openId}
          onClose={closeDrawer}
          onMark={mark}
          onApplicationChange={applyChange}
        />
      )}
    </div>
  )
}

function TrackerCard({
  item,
  onOpen,
  onMove,
}: {
  item: TrackerItem
  onOpen: () => void
  onMove: (stage: Stage) => void
}) {
  const a = item.application
  return (
    <article
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', item.id)
        e.dataTransfer.effectAllowed = 'move'
      }}
      className="cursor-grab rounded-xl border border-slate-200 bg-white p-3 shadow-sm active:cursor-grabbing dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex gap-2">
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={onOpen}
            className="text-left text-sm font-semibold leading-snug hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            {item.title}
          </button>
          <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
            {item.company ?? 'Компания не указана'}
          </p>
        </div>
        {item.score !== null && (
          <div className="scale-75 origin-top-right">
            <ScoreBadge score={item.score} />
          </div>
        )}
      </div>

      {a.notes && <p className="mt-2 line-clamp-2 text-xs text-slate-600 dark:text-slate-300">{a.notes}</p>}

      <div className="mt-2 flex items-center gap-2 text-[11px] text-slate-500">
        {a.applied_at && <span>отклик {formatDate(a.applied_at)}</span>}
        {a.cover_letter && (
          <span className="inline-flex items-center gap-0.5" title="Есть сопроводительное письмо">
            <Mail className="h-3 w-3" /> письмо
          </span>
        )}
        <select
          value={a.stage}
          onChange={(e) => onMove(e.target.value as Stage)}
          aria-label="Перенести в колонку"
          className="ml-auto rounded-md border-0 bg-transparent py-0.5 pl-1 pr-5 text-[11px] text-slate-500 ring-1 ring-inset ring-slate-200 dark:ring-slate-700"
        >
          {STAGES.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </div>
    </article>
  )
}

function daysAgo(isoDate: string): number {
  return (Date.now() - new Date(isoDate).getTime()) / 86_400_000
}
