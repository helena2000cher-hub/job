import { useEffect, useState } from 'react'
import { api } from '../api'
import type { LimitAction } from '../api'
import { useSession } from '../session'

/** «Сегодня осталось: 3 из 5» у платной кнопки — только для пользователей (у владельца лимитов нет). */
export function LimitHint({ action, refreshKey = 0 }: { action: LimitAction; refreshKey?: unknown }) {
  const isUser = useSession().role === 'user'
  const [left, setLeft] = useState<{ left: number; limit: number } | null>(null)

  useEffect(() => {
    if (!isUser) return
    let cancelled = false
    api
      .limits()
      .then((limits) => {
        const l = limits[action]
        if (!cancelled && l) setLeft({ left: Math.max(0, l.limit - l.used), limit: l.limit })
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [isUser, action, refreshKey])

  if (!left) return null
  return (
    <span className={`text-xs ${left.left ? 'text-slate-500 dark:text-slate-400' : 'text-amber-700 dark:text-amber-300'}`}>
      {left.left ? `Сегодня осталось: ${left.left} из ${left.limit}` : 'Лимит на сегодня исчерпан — завтра снова можно'}
    </span>
  )
}
