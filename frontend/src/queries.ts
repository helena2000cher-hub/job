// Поиск идёт только по отмеченным профессиям. Те же правила, что Profile.query_plan на сервере.
import type { Profile } from './api'

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

export function effectiveQueries(profile: Profile): string[] {
  const result: string[] = []
  for (const row of queryPlan(profile)) {
    for (const q of row.queries) if (!result.some((x) => norm(x) === norm(q))) result.push(q)
  }
  return result.length > 0 ? result : profile.search_queries
}

/** Новый список профессий — и запросы сразу пересчитываются под него. */
export function withRoles(profile: Profile, roles: string[]): Profile {
  const next = { ...profile, target_roles: roles }
  return { ...next, search_queries: roles.length > 0 ? effectiveQueries(next) : profile.search_queries }
}
