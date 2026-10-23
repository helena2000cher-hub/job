import { Sparkles } from 'lucide-react'
import type { Profile } from '../api'
import { MAX_SEARCH_SKILLS, effectiveQueries, norm, suggestSearchSkills, withSearch } from '../queries'
import type { SearchMode } from '../queries'
import { useInternals } from '../session'
import { QueryPlan } from './QueryPlan'

const MODES: { id: SearchMode; label: string; hint: string }[] = [
  { id: 'professions', label: 'По профессиям', hint: 'Точнее: вакансии с названиями выбранных профессий' },
  { id: 'skills', label: 'По навыкам', hint: 'Шире: находит вакансии с любыми названиями, где нужны ваши навыки' },
  { id: 'both', label: 'И так, и так', hint: 'Больше всего вакансий: профессии плюс навыки' },
]

/** «Что и где искать»: режим поиска, профессии с их запросами и навыки для поиска. */
export function SearchSettings({ profile, onChange }: { profile: Profile; onChange: (p: Profile) => void }) {
  const mode = profile.search_mode ?? 'professions'
  const chosen = profile.search_skills ?? []
  const internals = useInternals()
  const total = effectiveQueries(profile).length

  const setMode = (m: SearchMode) => {
    // впервые включили поиск по навыкам — сразу предложим ключевые
    const skills = m !== 'professions' && chosen.length === 0 ? suggestSearchSkills(profile) : chosen
    onChange(withSearch(profile, { search_mode: m, search_skills: skills }))
  }
  const toggleSkill = (skill: string) => {
    const on = chosen.some((s) => norm(s) === norm(skill))
    if (!on && chosen.length >= MAX_SEARCH_SKILLS) return
    const next = on ? chosen.filter((s) => norm(s) !== norm(skill)) : [...chosen, skill]
    onChange(withSearch(profile, { search_skills: next }))
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">Искать вакансии</p>
        <div className="grid gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Как искать вакансии">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              role="radio"
              aria-checked={mode === m.id}
              onClick={() => setMode(m.id)}
              className={`rounded-xl px-3 py-2.5 text-left ring-1 ring-inset transition ${
                mode === m.id
                  ? 'bg-indigo-50 ring-2 ring-indigo-500 dark:bg-indigo-500/10'
                  : 'ring-slate-200 hover:bg-slate-50 dark:ring-slate-700 dark:hover:bg-slate-800/60'
              }`}
            >
              <span className="block text-sm font-medium text-slate-900 dark:text-slate-100">{m.label}</span>
              <span className="mt-0.5 block text-xs text-slate-500 dark:text-slate-400">{m.hint}</span>
            </button>
          ))}
        </div>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          Всего запросов при поиске: {total}
          {internals && ` · ≈ $${(total * 0.06).toFixed(2)} за «Найти вакансии»`}. Оценка вакансий в любом
          режиме идёт по вашим навыкам.
        </p>
      </div>

      {mode !== 'skills' && (
        <div>
          <p className="mb-1.5 text-sm font-medium text-slate-700 dark:text-slate-300">Профессии и их запросы</p>
          <QueryPlan profile={profile} onRoles={(roles) => onChange(withSearch(profile, { target_roles: roles }))} />
        </div>
      )}

      {mode !== 'professions' && (
        <div>
          <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              Навыки для поиска · {chosen.length} из {MAX_SEARCH_SKILLS}
            </p>
            <button
              type="button"
              onClick={() => onChange(withSearch(profile, { search_skills: suggestSearchSkills(profile) }))}
              className="inline-flex items-center gap-1 text-xs font-medium text-indigo-700 hover:underline dark:text-indigo-300"
            >
              <Sparkles className="h-3.5 w-3.5" /> Предложить ключевые
            </button>
          </div>
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
            Лучше всего работают конкретные инструменты и технологии (n8n, RAG, BPMN). Общие навыки вроде
            «Аналитическое мышление» почти не встречаются в тексте вакансий.
          </p>
          <div className="flex flex-wrap gap-1.5">
            {profile.skills.map((skill) => {
              const on = chosen.some((s) => norm(s) === norm(skill))
              const full = !on && chosen.length >= MAX_SEARCH_SKILLS
              return (
                <button
                  key={skill}
                  type="button"
                  onClick={() => toggleSkill(skill)}
                  disabled={full}
                  aria-pressed={on}
                  className={`rounded-md px-2 py-1 text-sm transition disabled:cursor-not-allowed disabled:opacity-40 ${
                    on
                      ? 'bg-indigo-600 text-white hover:bg-indigo-500'
                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700'
                  }`}
                >
                  {skill}
                </button>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
