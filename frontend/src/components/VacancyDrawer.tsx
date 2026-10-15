import { AlertTriangle, ExternalLink, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { api } from '../api'
import type { Application, Mark, VacancyDetail } from '../api'
import { formatDate, formatSalary, sourceLabel } from '../format'
import { ApplicationPanel, CoverLetter } from './ApplicationPanel'
import { buttonClass } from './styles'
import { Button, Chip, ScoreBadge, Spinner } from './ui'

interface Props {
  id: string
  onClose: () => void
  onMark: (id: string, status: Mark) => void
  onApplicationChange?: (id: string, application: Application | null) => void
}

export function VacancyDrawer({ id, onClose, onMark, onApplicationChange }: Props) {
  const [vacancy, setVacancy] = useState<VacancyDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .vacancy(id)
      .then((v) => !cancelled && setVacancy(v))
      .catch((e: Error) => !cancelled && setError(e.message))
    return () => {
      cancelled = true
    }
  }, [id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const mark = (status: Mark) => {
    onMark(id, status)
    setVacancy((v) => (v ? { ...v, mark: status } : v))
  }

  const changeApplication = (application: Application | null) => {
    setVacancy((v) =>
      v
        ? {
            ...v,
            application,
            stage: application?.stage ?? null,
            mark: v.mark === 'hidden' ? 'hidden' : application ? 'saved' : null,
          }
        : v,
    )
    onApplicationChange?.(id, application)
  }

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-modal="true" aria-label="Вакансия">
      <div className="absolute inset-0 bg-slate-900/40 backdrop-blur-[2px]" onClick={onClose} />
      <aside className="scroll-thin relative flex h-full w-full max-w-2xl flex-col overflow-y-auto bg-white shadow-2xl dark:bg-slate-900">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/90 px-5 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/90">
          <span className="text-sm text-slate-500">{vacancy ? sourceLabel(vacancy.source) : 'Вакансия'}</span>
          <Button variant="ghost" onClick={onClose} aria-label="Закрыть" className="!p-2">
            <X className="h-5 w-5" />
          </Button>
        </div>

        {error && <p className="p-6 text-rose-600">{error}</p>}
        {!vacancy && !error && (
          <div className="flex flex-1 items-center justify-center text-slate-400">
            <Spinner className="h-6 w-6" />
          </div>
        )}

        {vacancy && (
          <div className="space-y-6 px-5 py-6 sm:px-7">
            <header className="flex gap-4">
              <ScoreBadge score={vacancy.score} size="lg" />
              <div className="min-w-0">
                <h2 className="text-xl font-semibold leading-tight">{vacancy.title}</h2>
                <p className="mt-1 text-slate-600 dark:text-slate-300">{vacancy.company ?? 'Компания не указана'}</p>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                  {formatSalary(vacancy.salary_from, vacancy.salary_to, vacancy.currency)}
                  {' · '}
                  {vacancy.is_remote ? 'удалённо' : (vacancy.region ?? 'регион не указан')}
                  {vacancy.published_at && ` · ${formatDate(vacancy.published_at)}`}
                </p>
              </div>
            </header>

            <div className="flex flex-wrap gap-2">
              <a href={vacancy.url} target="_blank" rel="noreferrer" className={buttonClass('primary')}>
                Открыть вакансию на сайте <ExternalLink className="h-4 w-4" />
              </a>
              <Button variant="ghost" onClick={() => mark(vacancy.mark === 'hidden' ? null : 'hidden')}>
                {vacancy.mark === 'hidden' ? 'Вернуть в ленту' : 'Скрыть'}
              </Button>
            </div>

            {vacancy.score !== null && (
              <section className="rounded-xl bg-slate-50 p-4 dark:bg-slate-800/50">
                <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-200">Почему такая оценка</h3>
                <p className="mt-1 text-sm text-slate-700 dark:text-slate-300">{vacancy.verdict}</p>
                <SkillList title="Совпало" items={vacancy.matched_skills} tone="match" />
                <SkillList title="Не хватает" items={vacancy.missing_skills} tone="missing" />
                {vacancy.red_flags.length > 0 && (
                  <div className="mt-3">
                    <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Обратить внимание</p>
                    <ul className="mt-1 space-y-1">
                      {vacancy.red_flags.map((flag) => (
                        <li key={flag} className="flex gap-2 text-sm text-amber-800 dark:text-amber-300">
                          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden /> {flag}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </section>
            )}

            <CoverLetter vacancyId={vacancy.id} application={vacancy.application} onChange={changeApplication} />

            <Section title="Обязанности">{vacancy.duties}</Section>
            <Section title="Требования">{vacancy.requirements}</Section>
            <Section title="Условия">{vacancy.conditions}</Section>
            {vacancy.skills.length > 0 && (
              <Section title="Навыки из вакансии">
                <div className="flex flex-wrap gap-1.5">
                  {vacancy.skills.map((s) => (
                    <Chip key={s}>{s}</Chip>
                  ))}
                </div>
              </Section>
            )}

            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 border-t border-slate-200 pt-4 text-sm sm:grid-cols-2 dark:border-slate-800">
              <Fact label="Занятость" value={vacancy.employment} />
              <Fact label="График" value={vacancy.schedule} />
              <Fact label="Опыт" value={vacancy.experience_years !== null ? `${vacancy.experience_years} лет` : null} />
              <Fact label="Образование" value={vacancy.education} />
            </dl>

            <ApplicationPanel vacancyId={vacancy.id} application={vacancy.application} onChange={changeApplication} />
          </div>
        )}
      </aside>
    </div>
  )
}

function SkillList({ title, items, tone }: { title: string; items: string[]; tone: 'match' | 'missing' }) {
  if (items.length === 0) return null
  return (
    <div className="mt-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{title}</p>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {items.map((s) => (
          <Chip key={s} tone={tone}>{s}</Chip>
        ))}
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  if (!children) return null
  return (
    <section>
      <h3 className="mb-1.5 text-sm font-semibold text-slate-700 dark:text-slate-200">{title}</h3>
      <div className="whitespace-pre-line text-sm leading-relaxed text-slate-700 dark:text-slate-300">{children}</div>
    </section>
  )
}

function Fact({ label, value }: { label: string; value: string | null }) {
  if (!value) return null
  return (
    <div className="flex gap-2">
      <dt className="text-slate-500">{label}:</dt>
      <dd className="text-slate-800 dark:text-slate-200">{value}</dd>
    </div>
  )
}
