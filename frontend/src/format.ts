const CURRENCY: Record<string, string> = { RUB: '₽', USD: '$', EUR: '€', KZT: '₸' }

const number = new Intl.NumberFormat('ru-RU')

export function formatSalary(from: number | null, to: number | null, currency = 'RUB'): string {
  const sign = CURRENCY[currency] ?? currency
  if (from && to && from !== to) return `${number.format(from)} – ${number.format(to)} ${sign}`
  if (from) return `от ${number.format(from)} ${sign}`
  if (to) return `до ${number.format(to)} ${sign}`
  return 'з/п не указана'
}

export type ScoreTone = 'great' | 'good' | 'weak'

export function scoreTone(score: number | null): ScoreTone {
  if (score !== null && score >= 80) return 'great'
  if (score !== null && score >= 60) return 'good'
  return 'weak'
}

export const SOURCE_LABELS: Record<string, string> = {
  trudvsem: 'Работа России',
  'hh.ru': 'hh.ru',
  'career.habr.com': 'Хабр Карьера',
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}

export function formatDate(value: string | null): string {
  if (!value) return ''
  return new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

export function formatDateTime(value: string | null): string {
  if (!value) return 'никогда'
  // сервер отдаёт UTC без зоны — добавляем Z, чтобы показать местное время
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(value) ? value : `${value}Z`)
  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function fitLabel(score: number | null): string {
  if (score === null) return 'не оценена'
  if (score >= 80) return 'подходит'
  if (score >= 60) return 'можно откликнуться'
  return 'слабое совпадение'
}
