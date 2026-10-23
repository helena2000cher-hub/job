import { ExternalLink, FileText, Lightbulb, Mail, Search, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { Advice, Analytics, RateRow, SentItem, Stage } from '../api'
import { formatDate, formatDateTime, sourceLabel } from '../format'
import { useInternals, useIsDemo } from '../session'
import { STAGES } from '../stages'
import { AddApplicationButton } from './AddApplicationDialog'
import { Button, EmptyState, Spinner } from './ui'
import { VacancyDrawer } from './VacancyDrawer'

const RELIABLE_SAMPLE = 10 // столько отправленных откликов нужно, чтобы доли что-то значили

export function AnalyticsPage({ onGoToFeed }: { onGoToFeed: () => void }) {
  const [data, setData] = useState<Analytics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [openId, setOpenId] = useState<string | null>(null)
  const [reloadKey, setReloadKey] = useState(0)
  const isDemo = useIsDemo()

  useEffect(() => {
    api
      .analytics()
      .then(setData)
      .catch((e: Error) => setError(e.message))
  }, [reloadKey])

  const reload = useCallback(() => setReloadKey((k) => k + 1), [])
  const closeDrawer = useCallback(() => setOpenId(null), [])

  const changeStage = async (id: string, stage: Stage) => {
    try {
      await api.updateApplication(id, { stage })
      reload()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  if (error) return <p className="rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">{error}</p>
  if (!data) {
    return (
      <div className="flex justify-center py-20 text-slate-400">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }

  const rate = data.response_rate === null ? '—' : `${Math.round(data.response_rate * 100)}%`
  const few = data.sent < RELIABLE_SAMPLE

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Аналитика откликов</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Сколько откликов привели к приглашениям и что работает лучше. Отклики без ответа{' '}
          {data.no_response_days} дней сами переходят в «Без ответа».
        </p>
      </div>

      {data.sent === 0 ? (
        <EmptyState title="Отправленных откликов пока нет">
          Откройте вакансию в{' '}
          <button type="button" className="text-indigo-600 underline dark:text-indigo-400" onClick={onGoToFeed}>
            ленте
          </button>
          , перейдите на сайт и ответьте «Да, отправлен» — здесь появится статистика. Откликались напрямую
          на hh.ru? Добавьте такой отклик вручную.
          {!isDemo && (
            <div className="mt-4">
              <AddApplicationButton variant="primary" onAdded={reload} />
            </div>
          )}
        </EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Отправлено" value={data.sent} />
            <Stat label="Приглашений" value={data.positive} hint="анкета, тестовое, собеседование, оффер" />
            <Stat label="Доля приглашений" value={rate} />
            <Stat label="Ждут ответа" value={data.waiting} />
            <Stat label="Без ответа" value={data.no_response} />
            <Stat label="Отказы" value={data.rejected} />
          </div>

          {few && (
            <p className="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
              Откликов пока {data.sent} — сравнения ниже предварительные. Выводы станут надёжнее после{' '}
              {RELIABLE_SAMPLE}–15 откликов. За последнюю неделю отправлено: {data.sent_last_7_days}.
            </p>
          )}

          <Panel
            title={`Мои отклики (${data.sent_list.length})`}
            action={!isDemo && <AddApplicationButton onAdded={reload} />}
          >
            <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
              Пришёл ответ, прислали анкету или тестовое, позвали на собеседование — поменяйте этап, статистика
              обновится. Нажмите на название, чтобы открыть вакансию, письмо и заметки.
            </p>
            <SentList items={data.sent_list} onOpen={setOpenId} onStage={changeStage} />
          </Panel>

          <Panel title="Где сейчас отклики">
            <Funnel data={data} />
          </Panel>

          <div className="grid gap-4 lg:grid-cols-3">
            <Panel title="Сопроводительное письмо">
              <RateList rows={data.by_letter} />
            </Panel>
            <Panel title="Балл совпадения">
              <RateList rows={data.by_score} />
            </Panel>
            <Panel title="Сайт">
              <RateList rows={data.by_source.map((r) => ({ ...r, label: sourceLabel(r.label) }))} />
            </Panel>
          </div>
        </>
      )}

      {data.top_gaps.length > 0 && (
        <Panel title="Чего чаще всего не хватает в подходящих вакансиях">
          <p className="mb-3 text-xs text-slate-500 dark:text-slate-400">
            Если навык у вас есть — добавьте его в резюме и в профиль («Что ещё умею»). Если нет — это
            кандидаты на быстрое обучение.
          </p>
          <ul className="flex flex-wrap gap-2">
            {data.top_gaps.map((g) => (
              <li
                key={g.skill}
                className="inline-flex items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1 text-sm text-slate-800 dark:bg-slate-800 dark:text-slate-200"
              >
                {g.skill}
                <span className="text-xs tabular-nums text-slate-500 dark:text-slate-400">×{g.count}</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <AdviceBlock initial={data.advice} sent={data.sent} />

      {openId && (
        <VacancyDrawer
          key={openId}
          id={openId}
          onClose={closeDrawer}
          onMark={(id, status) => api.mark(id, status).catch(() => undefined)}
          onApplicationChange={reload}
        />
      )}
    </div>
  )
}

/** Отправленные отклики: дата, этап (меняется прямо здесь), письмо, ссылка на вакансию. */
function SentList({
  items,
  onOpen,
  onStage,
}: {
  items: SentItem[]
  onOpen: (id: string) => void
  onStage: (id: string, stage: Stage) => void
}) {
  return (
    <ul className="divide-y divide-slate-100 dark:divide-slate-800">
      {items.map((item) => (
        <li key={item.id} className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 first:pt-0 last:pb-0">
          <div className="min-w-[12rem] flex-1">
            <button
              type="button"
              onClick={() => onOpen(item.id)}
              className="text-left text-sm font-medium text-slate-900 hover:text-indigo-600 dark:text-slate-100 dark:hover:text-indigo-400"
            >
              {item.title}
            </button>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {item.company ?? 'Компания не указана'} · {sourceLabel(item.source)}
              {item.score !== null && ` · ${item.score} баллов`}
            </p>
            {item.notes && <p className="mt-0.5 line-clamp-1 text-xs text-slate-600 dark:text-slate-300">{item.notes}</p>}
          </div>
          <span className="w-28 text-xs tabular-nums text-slate-500 dark:text-slate-400">
            {item.applied_at ? formatDate(item.applied_at) : '—'}
            {item.days_since !== null && <span className="block">{daysAgo(item.days_since)}</span>}
          </span>
          <select
            value={item.stage}
            onChange={(e) => onStage(item.id, e.target.value as Stage)}
            aria-label={`Этап: ${item.title}`}
            className="rounded-lg border-0 bg-slate-100 py-1.5 pl-2 pr-7 text-sm dark:bg-slate-800"
          >
            {STAGES.filter((s) => s.id !== 'interesting').map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <span className="flex w-16 items-center justify-end gap-1 text-slate-400">
            {item.has_letter && <Mail className="h-4 w-4" aria-label="Есть сопроводительное письмо" />}
            {item.url && (
            <a
              href={item.url}
              target="_blank"
              rel="noreferrer"
              className="rounded-lg p-1 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
              aria-label="Открыть вакансию на сайте"
              title="Открыть вакансию на сайте"
            >
              <ExternalLink className="h-4 w-4" />
            </a>
            )}
          </span>
        </li>
      ))}
    </ul>
  )
}

function daysAgo(days: number): string {
  if (days === 0) return 'сегодня'
  if (days === 1) return 'вчера'
  const mod10 = days % 10
  const mod100 = days % 100
  const word = mod10 === 1 && mod100 !== 11 ? 'день' : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 'дня' : 'дней'
  return `${days} ${word} назад`
}

function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-slate-100">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-slate-400">{hint}</p>}
    </div>
  )
}

function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

/** Сколько откликов на каждом этапе: одна горизонтальная полоса на этап, длина — количество. */
function Funnel({ data }: { data: Analytics }) {
  const rows = STAGES.filter((s) => s.id !== 'interesting').map((s) => ({
    ...s,
    count: data.stages[s.id] ?? 0,
  }))
  const max = Math.max(1, ...rows.map((r) => r.count))
  return (
    <ul className="space-y-2">
      {rows.map((r) => (
        <li key={r.id} className="grid grid-cols-[8.5rem_1fr_2rem] items-center gap-3 text-sm">
          <span className="inline-flex items-center gap-2 text-slate-700 dark:text-slate-300">
            <span className={`h-2 w-2 rounded-full ${r.dot}`} aria-hidden />
            {r.label}
          </span>
          <span className="h-3 rounded-r-[4px] bg-slate-100 dark:bg-slate-800" title={`${r.label}: ${r.count}`}>
            <span
              className="block h-full rounded-r-[4px] bg-indigo-500 dark:bg-indigo-400"
              style={{ width: `${(r.count / max) * 100}%` }}
            />
          </span>
          <span className="text-right tabular-nums text-slate-700 dark:text-slate-300">{r.count}</span>
        </li>
      ))}
    </ul>
  )
}

/** Доля приглашений по группам: полоса — процент, рядом «N из M». */
function RateList({ rows }: { rows: RateRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-slate-500">Пока нет данных</p>
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.label} title={`${r.label}: приглашений ${r.positive} из ${r.sent}`}>
          <div className="flex items-baseline justify-between gap-2 text-sm">
            <span className="truncate text-slate-700 dark:text-slate-300">{r.label}</span>
            <span className="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">
              {r.positive} из {r.sent} · <span className="font-medium text-slate-800 dark:text-slate-200">{Math.round(r.rate * 100)}%</span>
            </span>
          </div>
          <div className="mt-1 h-2 rounded-r-[4px] bg-slate-100 dark:bg-slate-800">
            <div
              className="h-full rounded-r-[4px] bg-emerald-500 dark:bg-emerald-400"
              style={{ width: `${Math.max(r.rate * 100, r.positive ? 4 : 0)}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  )
}

function AdviceBlock({ initial, sent }: { initial: Advice | null; sent: number }) {
  const [advice, setAdvice] = useState<Advice | null>(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isDemo = useIsDemo()
  const internals = useInternals()

  const generate = async () => {
    setBusy(true)
    setError(null)
    try {
      setAdvice(await api.makeAdvice())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-5 dark:border-indigo-500/30 dark:bg-indigo-500/5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold text-slate-900 dark:text-slate-100">
            <Lightbulb className="h-4 w-4 text-indigo-600 dark:text-indigo-400" aria-hidden /> Советы, как получать
            больше приглашений
          </h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Нейросеть смотрит на статистику откликов и частые пробелы и подсказывает, что поправить в резюме
            и письмах{internals ? ' (≈ 0,05 ₽)' : ''}.
            {advice && ` Последние советы: ${formatDateTime(advice.generated_at)}, по ${advice.based_on_sent} откликам.`}
          </p>
        </div>
        {!isDemo && (
          <Button variant={advice ? 'secondary' : 'primary'} onClick={generate} disabled={busy}>
            {busy ? <Spinner /> : <Sparkles className="h-4 w-4" />}
            {advice ? 'Обновить советы' : 'Получить советы'}
          </Button>
        )}
      </div>

      {isDemo && !advice && (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">В демо советы недоступны: это платный вызов нейросети.</p>
      )}
      {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
      {advice && sent > advice.based_on_sent && !busy && (
        <p className="mt-3 text-xs text-indigo-700 dark:text-indigo-300">
          С тех пор отправлено ещё {sent - advice.based_on_sent} — советы можно обновить.
        </p>
      )}

      {advice && (
        <div className="mt-4 space-y-4">
          {advice.summary && <p className="text-sm font-medium text-slate-800 dark:text-slate-100">{advice.summary}</p>}
          <div className="grid gap-4 md:grid-cols-3">
            <AdviceList icon={<FileText className="h-4 w-4" />} title="Резюме" items={advice.resume} />
            <AdviceList icon={<Mail className="h-4 w-4" />} title="Сопроводительные письма" items={advice.letters} />
            <AdviceList icon={<Search className="h-4 w-4" />} title="Поиск и отклики" items={advice.search} />
          </div>
        </div>
      )}
    </section>
  )
}

function AdviceList({ icon, title, items }: { icon: ReactNode; title: string; items: string[] }) {
  if (items.length === 0) return null
  return (
    <div className="rounded-xl bg-white p-4 dark:bg-slate-900">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
        <span className="text-indigo-600 dark:text-indigo-400" aria-hidden>
          {icon}
        </span>
        {title}
      </h3>
      <ul className="list-disc space-y-1.5 pl-4 text-sm text-slate-700 marker:text-slate-400 dark:text-slate-300">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  )
}
