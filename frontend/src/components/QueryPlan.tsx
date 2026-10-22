import { Eraser, Plus, X } from 'lucide-react'
import { useState } from 'react'
import type { Profile } from '../api'
import { effectiveQueries, norm, queryPlan } from '../queries'
import { Button } from './ui'

/** Отмеченные профессии и запросы каждой — именно по ним «Найти вакансии» собирает вакансии. */
export function QueryPlan({ profile, onRoles }: { profile: Profile; onRoles: (roles: string[]) => void }) {
  const [draft, setDraft] = useState('')
  const plan = queryPlan(profile)
  const hasCards = (profile.careers?.options.length ?? 0) > 0
  const legacy = hasCards ? plan.filter((r) => !r.hasCard) : []
  const total = effectiveQueries(profile).length

  const add = () => {
    const role = draft.trim()
    if (role && !profile.target_roles.some((r) => norm(r) === norm(role))) onRoles([...profile.target_roles, role])
    setDraft('')
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {plan.length === 0
            ? 'Профессии не выбраны — отметьте «Искать эту работу» в подборе выше.'
            : `Поиск пойдёт по ${total} ${plural(total, 'запросу', 'запросам', 'запросам')} для ${plan.length} ${plural(plan.length, 'профессии', 'профессий', 'профессий')}.`}
        </p>
        {legacy.length > 0 && (
          <Button onClick={() => onRoles(plan.filter((r) => r.hasCard).map((r) => r.role))}>
            <Eraser className="h-4 w-4" /> Убрать старые из резюме ({legacy.length})
          </Button>
        )}
      </div>

      <ul className="divide-y divide-slate-100 rounded-xl ring-1 ring-inset ring-slate-200 dark:divide-slate-800 dark:ring-slate-700">
        {plan.map((row) => (
          <li key={row.role} className="flex flex-wrap items-start gap-x-3 gap-y-1.5 px-3 py-2.5">
            <div className="min-w-[10rem] flex-1">
              <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{row.role}</p>
              {!row.hasCard && hasCards && (
                <p className="text-[11px] text-amber-700 dark:text-amber-400">из резюме или добавлена вручную · ищется по названию</p>
              )}
            </div>
            <div className="flex flex-[2] flex-wrap gap-1.5">
              {row.queries.map((q) => (
                <span key={q} className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  {q}
                </span>
              ))}
            </div>
            <button
              type="button"
              onClick={() => onRoles(profile.target_roles.filter((r) => r !== row.role))}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800"
              aria-label={`Не искать «${row.role}»`}
              title="Не искать эту профессию"
            >
              <X className="h-4 w-4" />
            </button>
          </li>
        ))}
        <li className="flex items-center gap-2 px-3 py-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                add()
              }
            }}
            placeholder="Добавить профессию вручную (будет искаться по названию)"
            aria-label="Добавить профессию вручную"
            className="w-full bg-transparent py-0.5 text-sm outline-none placeholder:text-slate-400"
          />
          {draft && (
            <button type="button" onClick={add} className="text-indigo-600" aria-label="Добавить">
              <Plus className="h-4 w-4" />
            </button>
          )}
        </li>
      </ul>
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
