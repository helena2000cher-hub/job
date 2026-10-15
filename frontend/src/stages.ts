import type { Stage } from './api'

export const STAGES: { id: Stage; label: string; dot: string }[] = [
  { id: 'interesting', label: 'Интересно', dot: 'bg-slate-400' },
  { id: 'applied', label: 'Отклик отправлен', dot: 'bg-indigo-500' },
  { id: 'interview', label: 'Собеседование', dot: 'bg-amber-500' },
  { id: 'offer', label: 'Оффер', dot: 'bg-emerald-500' },
  { id: 'rejected', label: 'Отказ', dot: 'bg-rose-500' },
]

export function stageLabel(stage: Stage): string {
  return STAGES.find((s) => s.id === stage)?.label ?? stage
}
