import { Check, RefreshCw, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { RefreshState } from '../api'
import { Button, Spinner } from './ui'

const SOURCES = [
  { id: 'exa', label: 'hh.ru, Хабр Карьера, сайты компаний', hint: 'через Exa · ≈ $0.5 за обновление' },
  { id: 'trudvsem', label: 'Работа России', hint: 'бесплатно · медленно, 3–6 минут' },
]

export function RefreshButton({ onDone }: { onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState<string[]>(['exa'])
  const [state, setState] = useState<RefreshState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pollRun, setPollRun] = useState(0) // +1 при каждом запуске — перезапускает опрос
  const wasRunning = useRef(false)
  const onDoneRef = useRef(onDone)
  const panel = useRef<HTMLDivElement>(null)

  useEffect(() => {
    onDoneRef.current = onDone
  }, [onDone])

  // Опрашиваем статус, пока идёт обновление (и один раз при открытии страницы —
  // вдруг обновление уже запущено). По завершении перезагружаем ленту.
  useEffect(() => {
    let timer: number | undefined
    let cancelled = false
    const poll = async () => {
      try {
        const s = await api.refreshStatus()
        if (cancelled) return
        setState(s)
        if (wasRunning.current && !s.running) onDoneRef.current()
        wasRunning.current = s.running
        if (s.running) timer = window.setTimeout(poll, 2000)
      } catch (e) {
        if (!cancelled) setError((e as Error).message)
      }
    }
    poll()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [pollRun])

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (panel.current && !panel.current.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onClick)
    window.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onClick)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const start = async () => {
    setError(null)
    try {
      const s = await api.refresh(selected)
      wasRunning.current = true
      setState(s)
      setPollRun((n) => n + 1)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  const running = state?.running ?? false

  return (
    <div className="relative" ref={panel}>
      <Button
        variant="primary"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={running ? 'Обновляется' : 'Обновить'}
      >
        {running ? <Spinner /> : <RefreshCw className="h-4 w-4" aria-hidden />}
        <span className="hidden sm:inline">{running ? 'Обновляется…' : 'Обновить'}</span>
      </Button>

      {open && (
        <div className="absolute right-0 z-30 mt-2 w-[min(22rem,calc(100vw-2rem))] rounded-2xl border border-slate-200 bg-white p-4 shadow-xl dark:border-slate-800 dark:bg-slate-900">
          {!running && (
            <>
              <p className="text-sm font-semibold">Где искать новые вакансии</p>
              <div className="mt-3 space-y-2">
                {SOURCES.map((s) => (
                  <label
                    key={s.id}
                    className="flex cursor-pointer gap-3 rounded-lg p-2 hover:bg-slate-50 dark:hover:bg-slate-800/60"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(s.id)}
                      onChange={() => toggle(s.id)}
                      className="mt-0.5 h-4 w-4 accent-indigo-600"
                    />
                    <span>
                      <span className="block text-sm font-medium">{s.label}</span>
                      <span className="block text-xs text-slate-500 dark:text-slate-400">{s.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                {selected.length === 0
                  ? 'Ничего не выбрано — только пересчитаем оценки под текущий профиль.'
                  : 'После сбора лучшие совпадения оценит нейросеть.'}
              </p>
              <Button variant="primary" className="mt-3 w-full" onClick={start}>
                {selected.length === 0 ? 'Пересчитать оценки' : 'Начать'}
              </Button>
            </>
          )}

          {state && (running || state.finished_at) && (
            <div className={running ? '' : 'mt-4 border-t border-slate-200 pt-3 dark:border-slate-800'}>
              <p className="flex items-center gap-2 text-sm font-medium">
                {running ? (
                  <>
                    <Spinner /> Идёт обновление
                  </>
                ) : state.error ? (
                  <>
                    <X className="h-4 w-4 text-rose-600" /> Ошибка
                  </>
                ) : (
                  <>
                    <Check className="h-4 w-4 text-emerald-600" /> Последнее обновление: +{state.new_vacancies} вакансий,
                    оценено {state.scored}
                  </>
                )}
              </p>
              {state.error && <p className="mt-1 text-xs text-rose-600">{state.error}</p>}
              <ol className="scroll-thin mt-2 max-h-40 space-y-0.5 overflow-y-auto font-mono text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                {state.log.slice(-12).map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ol>
              {state.cost_dollars > 0 && (
                <p className="mt-2 text-xs text-slate-500">Стоимость Exa: ${state.cost_dollars.toFixed(2)}</p>
              )}
            </div>
          )}

          {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
        </div>
      )}
    </div>
  )
}
