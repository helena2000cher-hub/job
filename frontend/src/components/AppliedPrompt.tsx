import { Check } from 'lucide-react'
import { useState } from 'react'
import { api } from '../api'
import type { Application } from '../api'
import { Spinner } from './ui'

/**
 * Вопрос после перехода на сайт работодателя: отправить отклик сайт сам не может узнать,
 * поэтому спрашиваем одним кликом — и вакансия встаёт в трекер с сегодняшней датой.
 */
export function AppliedPrompt({
  vacancyId,
  onAnswered,
}: {
  vacancyId: string
  onAnswered: (application: Application | null) => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const confirm = async () => {
    setBusy(true)
    setError(null)
    try {
      onAnswered(await api.updateApplication(vacancyId, { stage: 'applied' }))
    } catch (e) {
      setError((e as Error).message)
      setBusy(false)
    }
  }

  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-2 rounded-xl border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-900 dark:border-indigo-500/30 dark:bg-indigo-500/10 dark:text-indigo-100"
    >
      <span className="mr-auto">Отправили отклик на этот сайт?</span>
      <button
        type="button"
        onClick={confirm}
        disabled={busy}
        className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1 text-xs font-medium text-white hover:bg-indigo-500"
      >
        {busy ? <Spinner className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" />} Да, отправлен
      </button>
      <button
        type="button"
        onClick={() => onAnswered(null)}
        className="rounded-lg px-2 py-1 text-xs text-indigo-700 hover:bg-indigo-100 dark:text-indigo-300 dark:hover:bg-indigo-500/20"
      >
        Пока нет
      </button>
      {error && <span className="w-full text-xs text-rose-600">{error}</span>}
    </div>
  )
}

