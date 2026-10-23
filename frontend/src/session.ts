import { createContext, useContext } from 'react'
import type { Me } from './api'

// Кто смотрит сайт: владелец или гость в демо. Нужен, чтобы прятать платные действия в демо.
export const SessionContext = createContext<Me>({ role: 'owner', auth_enabled: false, demo_available: false })

export function useSession(): Me {
  return useContext(SessionContext)
}

/** Показывать «внутреннюю кухню»: стоимость, названия сервисов. Для клиентов — скрыто. */
export function useInternals(): boolean {
  return useSession().internals !== false
}

export function useIsDemo(): boolean {
  return useSession().role === 'demo'
}
