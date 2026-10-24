import { Plus, Trash2 } from 'lucide-react'
import type { ReactNode } from 'react'
import type { ResumeCourse, ResumeForm, ResumeJob, ResumeStudy } from '../api'
import { Field, INPUT, TagEditor } from './profileUi'

const NEW_JOB: ResumeJob = { company: '', position: '', start: '', end: '', description: '' }
const NEW_STUDY: ResumeStudy = { institution: '', faculty: '', specialty: '', year: '' }
const NEW_COURSE: ResumeCourse = { name: '', organization: '', year: '' }

/** Анкета резюме по разделам, как на hh.ru: общее, опыт, образование, курсы, навыки, о себе. */
export function ResumeFormEditor({ form, onChange }: { form: ResumeForm; onChange: (f: ResumeForm) => void }) {
  const set = <K extends keyof ResumeForm>(key: K, value: ResumeForm[K]) => onChange({ ...form, [key]: value })

  return (
    <div className="space-y-6">
      <Section title="Общая информация">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Желаемая должность">
            <input className={INPUT} value={form.position} placeholder="Бизнес-аналитик" onChange={(e) => set('position', e.target.value)} />
          </Field>
          <Field label="Город">
            <input className={INPUT} value={form.city} placeholder="Пермь" onChange={(e) => set('city', e.target.value)} />
          </Field>
          <Field label="Зарплата">
            <input className={INPUT} value={form.salary} placeholder="от 120 000 ₽ на руки" onChange={(e) => set('salary', e.target.value)} />
          </Field>
          <Field label="Формат работы">
            <input className={INPUT} value={form.work_format} placeholder="удалённо, полный день" onChange={(e) => set('work_format', e.target.value)} />
          </Field>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Имя и контакты указываются во вкладке «Для писем» — в нейросеть они не передаются.
        </p>
      </Section>

      <Section title="Опыт работы" hint="С последнего места. Обязанности и достижения пишите с цифрами — из них собираются письма.">
        <Rows
          items={form.experience}
          onChange={(v) => set('experience', v)}
          blank={NEW_JOB}
          addLabel="Добавить место работы"
          render={(job, patch) => (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <input className={INPUT} value={job.company} placeholder="Компания" aria-label="Компания" onChange={(e) => patch({ company: e.target.value })} />
                <input className={INPUT} value={job.position} placeholder="Должность" aria-label="Должность" onChange={(e) => patch({ position: e.target.value })} />
                <input className={INPUT} value={job.start} placeholder="Начало, например 03.2019" aria-label="Начало работы" onChange={(e) => patch({ start: e.target.value })} />
                <input className={INPUT} value={job.end} placeholder="Окончание (пусто — работаю сейчас)" aria-label="Окончание работы" onChange={(e) => patch({ end: e.target.value })} />
              </div>
              <textarea
                rows={4}
                className={`${INPUT} mt-3 leading-relaxed`}
                value={job.description}
                placeholder="Обязанности и достижения: что делали, какими инструментами, какой результат"
                aria-label="Обязанности и достижения"
                onChange={(e) => patch({ description: e.target.value })}
              />
            </>
          )}
        />
      </Section>

      <Section title="Образование">
        <Rows
          items={form.education}
          onChange={(v) => set('education', v)}
          blank={NEW_STUDY}
          addLabel="Добавить учебное заведение"
          render={(s, patch) => (
            <div className="grid gap-3 sm:grid-cols-2">
              <input className={INPUT} value={s.institution} placeholder="Учебное заведение" aria-label="Учебное заведение" onChange={(e) => patch({ institution: e.target.value })} />
              <input className={INPUT} value={s.faculty} placeholder="Факультет" aria-label="Факультет" onChange={(e) => patch({ faculty: e.target.value })} />
              <input className={INPUT} value={s.specialty} placeholder="Специальность" aria-label="Специальность" onChange={(e) => patch({ specialty: e.target.value })} />
              <input className={INPUT} value={s.year} placeholder="Год окончания" aria-label="Год окончания" onChange={(e) => patch({ year: e.target.value })} />
            </div>
          )}
        />
      </Section>

      <Section title="Курсы и повышение квалификации">
        <Rows
          items={form.courses}
          onChange={(v) => set('courses', v)}
          blank={NEW_COURSE}
          addLabel="Добавить курс"
          render={(c, patch) => (
            <div className="grid gap-3 sm:grid-cols-[2fr_2fr_1fr]">
              <input className={INPUT} value={c.name} placeholder="Название курса" aria-label="Название курса" onChange={(e) => patch({ name: e.target.value })} />
              <input className={INPUT} value={c.organization} placeholder="Кто проводил" aria-label="Кто проводил" onChange={(e) => patch({ organization: e.target.value })} />
              <input className={INPUT} value={c.year} placeholder="Год" aria-label="Год" onChange={(e) => patch({ year: e.target.value })} />
            </div>
          )}
        />
      </Section>

      <Section title="Ключевые навыки">
        <TagEditor values={form.skills} onChange={(v) => set('skills', v)} placeholder="Добавить навык — Enter" />
        <Field label="Языки">
          <input className={INPUT} value={form.languages} placeholder="Английский — B1" onChange={(e) => set('languages', e.target.value)} />
        </Field>
      </Section>

      <Section title="О себе">
        <textarea
          rows={4}
          className={`${INPUT} leading-relaxed`}
          value={form.about}
          placeholder="Пара предложений: в чём вы сильны и чем хотите заниматься"
          aria-label="О себе"
          onChange={(e) => set('about', e.target.value)}
        />
      </Section>
    </div>
  )
}

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h3>
        {hint && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
      </div>
      {children}
    </div>
  )
}

function Rows<T>({
  items,
  onChange,
  blank,
  addLabel,
  render,
}: {
  items: T[]
  onChange: (items: T[]) => void
  blank: T
  addLabel: string
  render: (item: T, patch: (p: Partial<T>) => void) => ReactNode
}) {
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={i} className="relative rounded-xl p-3 pr-10 ring-1 ring-inset ring-slate-200 dark:ring-slate-700">
          {render(item, (p) => onChange(items.map((x, j) => (j === i ? { ...x, ...p } : x))))}
          <button
            type="button"
            onClick={() => onChange(items.filter((_, j) => j !== i))}
            className="absolute right-2 top-2 rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-rose-600 dark:hover:bg-slate-800"
            aria-label="Удалить"
            title="Удалить"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...items, { ...blank }])}
        className="inline-flex items-center gap-1 text-sm font-medium text-indigo-700 hover:underline dark:text-indigo-300"
      >
        <Plus className="h-4 w-4" /> {addLabel}
      </button>
    </div>
  )
}
