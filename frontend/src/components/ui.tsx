import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { scoreTone } from '../format'
import { buttonClass } from './styles'
import type { ButtonVariant } from './styles'

const TONE_CLASSES = {
  great: 'bg-emerald-100 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-400/30',
  good: 'bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-400/30',
  weak: 'bg-slate-100 text-slate-600 ring-slate-500/20 dark:bg-slate-500/15 dark:text-slate-400 dark:ring-slate-400/30',
}

export function ScoreBadge({ score, size = 'md' }: { score: number | null; size?: 'md' | 'lg' }) {
  const sizing = size === 'lg' ? 'h-14 w-14 text-xl' : 'h-11 w-11 text-base'
  return (
    <div
      className={`${sizing} ${TONE_CLASSES[scoreTone(score)]} flex shrink-0 items-center justify-center rounded-xl font-semibold tabular-nums ring-1 ring-inset`}
      title="Насколько вакансия подходит, 0–100"
    >
      {score ?? '—'}
    </div>
  )
}

type ChipTone = 'match' | 'missing' | 'neutral'

const CHIP_CLASSES: Record<ChipTone, string> = {
  match: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300',
  missing: 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300',
  neutral: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
}

export function Chip({ children, tone = 'neutral' }: { children: ReactNode; tone?: ChipTone }) {
  return (
    <span className={`${CHIP_CLASSES[tone]} inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium`}>
      {children}
    </span>
  )
}

export function Button({
  variant = 'secondary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      type="button"
      className={buttonClass(variant, className)}
      {...props}
    />
  )
}

export function Spinner({ className = 'h-4 w-4' }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin`} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 px-6 py-14 text-center dark:border-slate-700">
      <p className="font-medium text-slate-800 dark:text-slate-200">{title}</p>
      {children && <div className="mt-2 text-sm text-slate-500 dark:text-slate-400">{children}</div>}
    </div>
  )
}
