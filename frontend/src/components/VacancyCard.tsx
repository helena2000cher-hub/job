import { Bookmark, BookmarkCheck, EyeOff, Eye, House, MapPin, ExternalLink } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FeedItem, Mark } from '../api'
import { formatDate, formatSalary, sourceLabel } from '../format'
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
        <ScoreBadge score={item.score} />

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

          {(item.matched_skills.length > 0 || item.missing_skills.length > 0) && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {item.matched_skills.slice(0, 5).map((skill) => (
                <Chip key={`m-${skill}`} tone="match">✓ {skill}</Chip>
              ))}
              {item.missing_skills.slice(0, 3).map((skill) => (
                <Chip key={`x-${skill}`} tone="missing">✗ {skill}</Chip>
              ))}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-1 text-xs text-slate-400">
            <span>{sourceLabel(item.source)}</span>
            {item.published_at && <span>· {formatDate(item.published_at)}</span>}
            <div className="ml-auto flex items-center gap-1">
              <IconButton
                label={saved ? 'Убрать из сохранённых' : 'Сохранить'}
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
