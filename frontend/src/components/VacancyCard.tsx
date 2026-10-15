import { Bookmark, BookmarkCheck, ExternalLink, Eye, EyeOff, House, MapPin, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FeedItem, Mark } from '../api'
import { fitLabel, formatDate, formatSalary, sourceLabel } from '../format'
import { STAGES } from '../stages'
import { Chip, ScoreBadge } from './ui'

interface Props {
  item: FeedItem
  onOpen: () => void
  onMark: (status: Mark) => void
}

export function VacancyCard({ item, onOpen, onMark }: Props) {
  const saved = item.mark === 'saved'
  const hidden = item.mark === 'hidden'

  return (
    <article className="group rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:border-indigo-300 hover:shadow-md sm:p-5 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-indigo-500/50">
      <div className="flex gap-4">
        <div className="flex w-16 shrink-0 flex-col items-center gap-1 text-center">
          <ScoreBadge score={item.score} />
          <span className="text-[11px] leading-tight text-slate-500 dark:text-slate-400">{fitLabel(item.score)}</span>
        </div>

        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={onOpen}
            className="text-left text-base font-semibold leading-snug text-slate-900 hover:text-indigo-600 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:text-slate-100 dark:hover:text-indigo-400"
          >
            {item.title}
          </button>

          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500 dark:text-slate-400">
            <span className="font-medium text-slate-700 dark:text-slate-300">{item.company ?? 'Компания не указана'}</span>
            {item.is_remote ? (
              <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400">
                <House className="h-3.5 w-3.5" aria-hidden /> удалённо
              </span>
            ) : (
              item.region && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="h-3.5 w-3.5" aria-hidden /> {item.region}
                </span>
              )
            )}
            <span className="tabular-nums">{formatSalary(item.salary_from, item.salary_to, item.currency)}</span>
          </div>

          {item.verdict && (
            <p className="mt-2 line-clamp-2 text-sm text-slate-600 dark:text-slate-300">{item.verdict}</p>
          )}

          {item.matched_skills.length > 0 && (
            <SkillRow label="Совпадает" tone="match" skills={item.matched_skills} max={6} />
          )}
          {item.missing_skills.length > 0 && (
            <SkillRow label="Не хватает" tone="missing" skills={item.missing_skills} max={4} />
          )}

          <div className="mt-3 flex flex-wrap items-center gap-1 text-xs text-slate-400">
            <span>{sourceLabel(item.source)}</span>
            {item.stage && <StagePill stage={item.stage} />}
            {item.published_at && <span>· {formatDate(item.published_at)}</span>}
            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                onClick={onOpen}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50 dark:text-indigo-300 dark:hover:bg-indigo-500/10"
              >
                <Sparkles className="h-3.5 w-3.5" aria-hidden /> Подробнее и письмо
              </button>
              <IconButton
                label={saved ? 'Убрать из трекера' : 'Добавить в трекер откликов'}
                active={saved}
                onClick={() => onMark(saved ? null : 'saved')}
              >
                {saved ? <BookmarkCheck className="h-4 w-4" /> : <Bookmark className="h-4 w-4" />}
              </IconButton>
              <IconButton
                label={hidden ? 'Вернуть в ленту' : 'Скрыть'}
                onClick={() => onMark(hidden ? null : 'hidden')}
              >
                {hidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
              </IconButton>
              <a
                href={item.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100 hover:text-slate-900 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                title="Открыть на сайте"
                aria-label="Открыть на сайте"
              >
                <ExternalLink className="h-4 w-4" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </article>
  )
}

function IconButton({
  label,
  active = false,
  onClick,
  children,
}: {
  label: string
  active?: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      aria-pressed={active}
      className={`inline-flex h-8 w-8 items-center justify-center rounded-lg transition-colors hover:bg-slate-100 dark:hover:bg-slate-800 ${
        active ? 'text-indigo-600 dark:text-indigo-400' : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-100'
      }`}
    >
      {children}
    </button>
  )
}

function StagePill({ stage }: { stage: string }) {
  const s = STAGES.find((x) => x.id === stage)
  if (!s) return null
  return (
    <span className="ml-1 inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} aria-hidden />
      {s.label}
    </span>
  )
}

function SkillRow({
  label,
  tone,
  skills,
  max,
}: {
  label: string
  tone: 'match' | 'missing'
  skills: string[]
  max: number
}) {
  const rest = skills.length - max
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5">
      <span className="w-[5.5rem] shrink-0 text-xs font-medium text-slate-500 dark:text-slate-400">{label}:</span>
      {skills.slice(0, max).map((skill) => (
        <Chip key={skill} tone={tone}>
          {skill}
        </Chip>
      ))}
      {rest > 0 && <span className="text-xs text-slate-400">и ещё {rest}</span>}
    </div>
  )
}
