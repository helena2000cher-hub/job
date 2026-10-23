// Что ищет «Найти вакансии». Те же правила, что Profile.query_plan / effective_queries на сервере.
import type { Profile } from './api'

export type SearchMode = 'professions' | 'skills' | 'both'

export const MAX_SEARCH_SKILLS = 10

export const norm = (text: string) => text.toLowerCase().split(/\s+/).filter(Boolean).join(' ')

export interface PlanRow {
  role: string
  queries: string[]
  hasCard: boolean // есть карточка в «Кем я могу работать»; иначе роль из резюме или добавлена вручную
}

export function queryPlan(profile: Profile): PlanRow[] {
  const cards = new Map((profile.careers?.options ?? []).map((o) => [norm(o.title), o]))
  return profile.target_roles.map((role) => {
    const card = cards.get(norm(role))
    return card && card.queries.length > 0
      ? { role, queries: card.queries, hasCard: true }
      : { role, queries: [role], hasCard: Boolean(card) }
  })
}

function unique(items: string[]): string[] {
  const result: string[] = []
  for (const q of items) if (q.trim() && !result.some((x) => norm(x) === norm(q))) result.push(q.trim())
  return result
}

export function professionQueries(profile: Profile): string[] {
  return unique(queryPlan(profile).flatMap((r) => r.queries))
}

export function effectiveQueries(profile: Profile): string[] {
  const mode = profile.search_mode ?? 'professions'
  const items = [
    ...(mode !== 'skills' ? queryPlan(profile).flatMap((r) => r.queries) : []),
    ...(mode !== 'professions' ? (profile.search_skills ?? []) : []),
  ]
  const result = unique(items)
  return result.length > 0 ? result : profile.search_queries
}

/** Изменить профиль и сразу пересчитать запросы под новые профессии / навыки / режим. */
export function withSearch(profile: Profile, patch: Partial<Profile>): Profile {
  const next = { ...profile, ...patch }
  const hasSources = next.target_roles.length > 0 || (next.search_skills ?? []).length > 0
  return { ...next, search_queries: hasSources ? effectiveQueries(next) : profile.search_queries }
}

export function withRoles(profile: Profile, roles: string[]): Profile {
  return withSearch(profile, { target_roles: roles })
}

/**
 * Ключевые навыки для поиска: те, что чаще всего «пригодятся» в профессиях из подбора
 * (сначала в отмеченных). Только навыки из профиля — без выдумок.
 */
export function suggestSearchSkills(profile: Profile): string[] {
  const options = profile.careers?.options ?? []
  const chosen = options.filter((o) => profile.target_roles.some((r) => norm(r) === norm(o.title)))
  const counts = new Map<string, number>()
  for (const o of [...chosen, ...chosen, ...options]) {
    // отмеченные профессии считаем с весом 3 (два повтора + общий список)
    for (const skill of o.transferable) counts.set(norm(skill), (counts.get(norm(skill)) ?? 0) + 1)
  }
  const searchable = profile.skills.filter(isSearchable)
  const ranked = searchable
    .map((s) => ({ s, n: counts.get(norm(s)) ?? 0 }))
    .filter((x) => x.n > 0)
    .sort((a, b) => b.n - a.n)
    .map((x) => x.s)
  return (ranked.length > 0 ? ranked : searchable).slice(0, 8)
}

// Общие формулировки почти не встречаются в тексте вакансий дословно — по ним не ищем
const GENERIC = /презентац|мышлени|коммуникац|объ[её]м|информаци|документац|описани|декомпозиц|сбор и|анализ требований|работа с/i

/** Хороший запрос — короткое название инструмента или технологии: «n8n», «RAG», «BPMN». */
export function isSearchable(skill: string): boolean {
  return skill.trim().split(/\s+/).length <= 3 && !GENERIC.test(skill)
}
