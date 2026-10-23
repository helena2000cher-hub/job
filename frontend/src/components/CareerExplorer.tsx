import { Check, Compass, Plus, Sparkles } from 'lucide-react'
import type { CareerKind, CareerOption, CareerSuggestions } from '../api'
import { useInternals } from '../session'
import { Button, Spinner } from './ui'

const GROUPS: { kind: CareerKind; title: string; hint: string }[] = [
  { kind: 'core', title: 'По основным навыкам', hint: 'Можно откликаться уже сейчас' },
  { kind: 'adjacent', title: 'Смежные профессии', hint: 'Большая часть навыков переносится' },
  { kind: 'new_field', title: 'Другие сферы', hint: 'Где ваши навыки неожиданно ценны' },
]

interface Props {
  careers: CareerSuggestions | null
  skills: string[]
  extra: string
  selected: string[] // выбранные профессии (= целевые роли профиля)
  busy: boolean
  disabled: boolean // в демо или есть несохранённые изменения
  disabledHint?: string
  onGenerate: () => void
  onToggle: (option: CareerOption) => void
}

/** «Кем я могу работать»: профессии, подобранные по навыкам, с процентом совпадения. */
export function CareerExplorer({ careers, skills, extra, selected, busy, disabled, disabledHint, onGenerate, onToggle }: Props) {
  const internals = useInternals()
  const isSelected = (title: string) => selected.some((s) => s.trim().toLowerCase() === title.trim().toLowerCase())
  const stale =
    careers !== null &&
    (careers.extra_snapshot !== extra ||
      careers.skills_snapshot.length !== skills.length ||
      careers.skills_snapshot.some((s, i) => s !== skills[i]))

  return (
    <section className="space-y-4 rounded-2xl border border-indigo-200 bg-indigo-50/40 p-5 shadow-sm dark:border-indigo-500/30 dark:bg-indigo-500/5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 font-semibold">
            <Compass className="h-4 w-4 text-indigo-600 dark:text-indigo-400" aria-hidden /> Кем я могу работать
          </h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Нейросеть смотрит только на навыки — не на прошлую должность — и подбирает профессии, в том числе в
            других сферах. Отметьте «Ищу эту работу», и по ней начнётся поиск вакансий.
          </p>
        </div>
        <Button variant={careers ? 'secondary' : 'primary'} onClick={onGenerate} disabled={busy || disabled} title={disabled ? disabledHint : undefined}>
          {busy ? <Spinner /> : <Sparkles className="h-4 w-4" />}
          {careers ? 'Обновить подбор' : 'Подобрать профессии'}
        </Button>
      </div>

      {disabled && disabledHint && <p className="text-xs text-slate-500 dark:text-slate-400">{disabledHint}</p>}
      {busy && <p className="text-xs text-slate-500">Подбираю профессии по навыкам, это займёт до 30 секунд{internals ? ' (≈ 0,05 ₽)' : ''}…</p>}
      {stale && !busy && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-500/10 dark:text-amber-200">
          Навыки изменились после подбора — нажмите «Обновить подбор», чтобы список их учёл.
        </p>
      )}

      {careers &&
        GROUPS.map((group) => {
          const options = careers.options.filter((o) => o.kind === group.kind)
          if (options.length === 0) return null
          return (
            <div key={group.kind}>
              <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {group.title} <span className="font-normal text-slate-500 dark:text-slate-400">· {group.hint}</span>
              </h3>
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                {options.map((o) => (
                  <CareerCard key={o.title} option={o} selected={isSelected(o.title)} disabled={disabled} onToggle={() => onToggle(o)} />
                ))}
              </div>
            </div>
          )
        })}
    </section>
  )
}

function CareerCard({
  option,
  selected,
  disabled,
  onToggle,
}: {
  option: CareerOption
  selected: boolean
  disabled: boolean
  onToggle: () => void
}) {
  return (
    <article
      className={`flex flex-col rounded-xl border bg-white p-4 dark:bg-slate-900 ${
        selected ? 'border-indigo-400 ring-1 ring-indigo-400 dark:border-indigo-500 dark:ring-indigo-500' : 'border-slate-200 dark:border-slate-800'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium leading-snug text-slate-900 dark:text-slate-100">{option.title}</p>
          {option.field && <p className="text-xs text-slate-500 dark:text-slate-400">{option.field}</p>}
        </div>
        <span className="shrink-0 text-lg font-semibold tabular-nums text-slate-900 dark:text-slate-100" title="Какая доля ключевых навыков профессии у вас уже есть">
          {option.fit}%
        </span>
      </div>
      <div className="mt-2 h-1.5 rounded-r-[4px] bg-slate-100 dark:bg-slate-800" aria-hidden>
        <div className="h-full rounded-r-[4px] bg-indigo-500 dark:bg-indigo-400" style={{ width: `${option.fit}%` }} />
      </div>
      {option.why && <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">{option.why}</p>}
      {option.transferable.length > 0 && (
        <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
          <span className="font-medium text-emerald-700 dark:text-emerald-400">Пригодится: </span>
          {option.transferable.join(', ')}
        </p>
      )}
      {option.gaps.length > 0 && (
        <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
          <span className="font-medium text-rose-700 dark:text-rose-400">Подтянуть: </span>
          {option.gaps.join(', ')}
        </p>
      )}
      <div className="mt-3 flex flex-1 items-end">
        <button
          type="button"
          onClick={onToggle}
          disabled={disabled}
          aria-pressed={selected}
          className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${
            selected
              ? 'bg-indigo-600 text-white hover:bg-indigo-500'
              : 'bg-indigo-50 text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-500/10 dark:text-indigo-300 dark:hover:bg-indigo-500/20'
          }`}
        >
          {selected ? <Check className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {selected ? 'Ищу эту работу' : 'Искать эту работу'}
        </button>
      </div>
    </article>
  )
}
