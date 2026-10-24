import { Save } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '../api'
import type { CareerOption, Profile } from '../api'
import { useIsDemo } from '../session'
import { withRoles } from '../queries'
import { CareerExplorer } from './CareerExplorer'
import { Card, Field, INPUT, TagEditor } from './profileUi'
import { ResumeSources } from './ResumeSources'
import { SearchSettings } from './SearchSettings'
import { Button, Spinner } from './ui'

type Section = 'resume' | 'skills' | 'search' | 'letters' | 'about'

const SECTIONS: { id: Section; label: string }[] = [
  { id: 'resume', label: 'Резюме' },
  { id: 'skills', label: 'Навыки и профессии' },
  { id: 'search', label: 'Что искать' },
  { id: 'letters', label: 'Для писем' },
  { id: 'about', label: 'Обо мне' },
]

const SECTION_KEY = 'profile-section'

function storedSection(): Section {
  try {
    const value = localStorage.getItem(SECTION_KEY)
    if (SECTIONS.some((s) => s.id === value)) return value as Section
  } catch {
    /* хранилище недоступно — открываем навыки */
  }
  return 'skills'
}

export function ProfilePage({ onSaved }: { onSaved: () => void }) {
  const [profile, setProfile] = useState<Profile | null>(null)
  const [saved, setSaved] = useState<string>('') // JSON последней сохранённой версии
  const [status, setStatus] = useState<'loading' | 'missing' | 'ready'>('loading')
  const [busy, setBusy] = useState<'save' | 'careers' | null>(null)
  const [section, setSectionState] = useState<Section>(storedSection)
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)
  const isDemo = useIsDemo()

  const load = (p: Profile) => {
    setProfile(p)
    setSaved(JSON.stringify(p))
    setStatus('ready')
  }

  useEffect(() => {
    api
      .profile()
      .then(load)
      .catch(() => setStatus('missing'))
  }, [])

  const dirty = profile !== null && JSON.stringify(profile) !== saved

  const setSection = (s: Section) => {
    setSectionState(s)
    try {
      localStorage.setItem(SECTION_KEY, s)
    } catch {
      /* не запомним — не страшно */
    }
  }

  const fromResume = (p: Profile, text: string) => {
    load(p)
    setMessage({ tone: 'ok', text })
    onSaved()
  }

  const save = async () => {
    if (!profile) return
    setBusy('save')
    setMessage(null)
    try {
      load(await api.saveProfile(profile))
      setMessage({ tone: 'ok', text: 'Сохранено. Нажмите «Найти вакансии» → снимите галочки → «Пересчитать оценки», чтобы лента учла изменения.' })
      onSaved()
    } catch (e) {
      setMessage({ tone: 'error', text: (e as Error).message })
    } finally {
      setBusy(null)
    }
  }

  const suggestCareers = async () => {
    setBusy('careers')
    setMessage(null)
    try {
      load(await api.suggestCareers())
    } catch (e) {
      setMessage({ tone: 'error', text: (e as Error).message })
    } finally {
      setBusy(null)
    }
  }

  // «Искать эту работу»: профессия попадает в выбранные (запросы пересчитываются), повторно — убираем
  const toggleCareer = (option: CareerOption) => {
    if (!profile) return
    const same = (r: string) => r.trim().toLowerCase() === option.title.trim().toLowerCase()
    const roles = profile.target_roles.some(same)
      ? profile.target_roles.filter((r) => !same(r))
      : [...profile.target_roles, option.title]
    setProfile(withRoles(profile, roles))
  }

  if (status === 'loading') {
    return (
      <div className="flex justify-center py-20 text-slate-400">
        <Spinner className="h-6 w-6" />
      </div>
    )
  }

  if (status === 'missing' || !profile) {
    return (
      <div className="mx-auto max-w-3xl space-y-6 pb-24">
        <div>
          <h1 className="text-2xl font-semibold">Создайте профиль</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Дайте резюме любым способом — нейросеть извлечёт навыки, опыт и подберёт профессии.
          </p>
        </div>
        <ResumeSources
          hasProfile={false}
          disabledHint={isDemo ? 'В демо резюме не загружается — это платный вызов нейросети.' : undefined}
          onProfile={fromResume}
        />
      </div>
    )
  }

  const set = <K extends keyof Profile>(key: K, value: Profile[K]) => setProfile({ ...profile, [key]: value })
  const setPref = <K extends keyof Profile['preferences']>(key: K, value: Profile['preferences'][K]) =>
    setProfile({ ...profile, preferences: { ...profile.preferences, [key]: value } })

  return (
    <div className="mx-auto max-w-3xl space-y-6 pb-24">
      <div>
        <h1 className="text-2xl font-semibold">Профиль</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Всё начинается с навыков: по ним подбираются профессии, а по выбранным профессиям — вакансии.
        </p>
      </div>

      <nav
        className="-mx-4 flex gap-1 overflow-x-auto px-4 shadow-[inset_0_-1px_0_var(--color-slate-200)] sm:mx-0 sm:px-0 dark:shadow-[inset_0_-1px_0_var(--color-slate-800)]"
        role="tablist"
        aria-label="Разделы профиля"
      >
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={section === s.id}
            onClick={() => setSection(s.id)}
            className={`shrink-0 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              section === s.id
                ? 'border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
                : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {s.label}
          </button>
        ))}
      </nav>

      {isDemo && (
        <p className="rounded-lg bg-slate-100 px-4 py-3 text-sm text-slate-600 dark:bg-slate-800 dark:text-slate-300">
          В демо профиль только для просмотра. Владелец сайта загружает резюме файлом, ссылкой или анкетой
          и правит здесь же: навыки, профессии, поиск, зарплату и стоп-слова.
        </p>
      )}

      {section === 'resume' && (
        <ResumeSources
          hasProfile
          disabledHint={
            isDemo
              ? 'В демо резюме не загружается — это платный вызов нейросети.'
              : dirty
                ? 'Сначала сохраните или отмените изменения профиля внизу экрана.'
                : undefined
          }
          onProfile={fromResume}
        />
      )}

      {section === 'skills' && (
        <>
          <fieldset disabled={isDemo} className="space-y-6 disabled:opacity-90">
            <Card title="Мои навыки" subtitle="Главное в профиле: по навыкам подбираются профессии, вакансии и письма.">
              <Field label={`Навыки (${profile.skills.length})`} hint="Добавляйте всё, что умеете: инструменты, методики, языки, предметные знания.">
                <TagEditor values={profile.skills} onChange={(v) => set('skills', v)} placeholder="Добавить навык" />
              </Field>
              <Field
                label="Что ещё умею (нет в резюме)"
                hint="Своими словами: где применяли и на каком уровне. Учитывается при подборе профессий, оценке вакансий и в письмах."
              >
                <textarea
                  rows={3}
                  className={INPUT}
                  value={profile.extra ?? ''}
                  placeholder="Например: Make — проходила на курсе; Google Таблицы и Документы — уверенно; CRM — как пользователь"
                  onChange={(e) => set('extra', e.target.value)}
                />
              </Field>
            </Card>
          </fieldset>

          <CareerExplorer
            careers={profile.careers}
            skills={profile.skills}
            extra={profile.extra ?? ''}
            selected={profile.target_roles}
            busy={busy === 'careers'}
            disabled={isDemo || dirty}
            disabledHint={
              isDemo
                ? 'В демо подбор недоступен — это платный вызов нейросети.'
                : dirty
                  ? 'Сохраните изменения, чтобы подбор учёл новые навыки.'
                  : undefined
            }
            onGenerate={suggestCareers}
            onToggle={toggleCareer}
          />
        </>
      )}

      {section === 'search' && (
        <fieldset disabled={isDemo} className="space-y-6 disabled:opacity-90">
          <Card title="Что и где искать" subtitle="По профессиям — точнее, по навыкам — шире. «Найти вакансии» ищет по выбранному варианту.">
            <SearchSettings profile={profile} onChange={setProfile} />
            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={profile.preferences.remote_only}
                onChange={(e) => setPref('remote_only', e.target.checked)}
                className="h-4 w-4 accent-indigo-600"
              />
              <span className="text-sm font-medium">Только удалённая работа</span>
            </label>
            {!profile.preferences.remote_only && (
              <Field label="Регионы, где подходит офис">
                <TagEditor values={profile.preferences.regions} onChange={(v) => setPref('regions', v)} placeholder="Например, Пермский край" />
              </Field>
            )}
            <Field label="Зарплата от, ₽ на руки" hint="Вакансии с потолком ниже отсеиваются">
              <input
                type="number"
                min={0}
                step={5000}
                className={`${INPUT} max-w-xs`}
                value={profile.preferences.salary_min ?? ''}
                onChange={(e) => setPref('salary_min', e.target.value === '' ? null : Number(e.target.value))}
              />
            </Field>
            <Field label="Стоп-слова" hint="Вакансии с этими словами в названии или обязанностях не показываются">
              <TagEditor values={profile.preferences.stop_words} onChange={(v) => setPref('stop_words', v)} placeholder="Добавить слово" tone="danger" />
            </Field>
          </Card>
        </fieldset>
      )}

      {section === 'letters' && (
        <fieldset disabled={isDemo} className="space-y-6 disabled:opacity-90">
          <Card
            title="Для сопроводительных писем"
            subtitle="Из этого нейросеть собирает пункты «Что уже сделано на практике». Чем конкретнее — тем сильнее письмо."
          >
            <Field
              label="Истории и достижения"
              hint="Проекты с цифрами, случаи, где вы нашли ошибку или улучшили процесс, принципы работы. Каждую историю — с новой строки. Берутся только отсюда, из резюме и «Что ещё умею»: нейросеть ничего не выдумывает."
            >
              <textarea
                rows={7}
                className={`${INPUT} leading-relaxed`}
                value={profile.stories ?? ''}
                placeholder={'Например:\n• Заметила, что метрика качества прогнозов завышена, и переделала оценку на сравнение со случайным выбором.\n• На приёмке ИИ-куратора нашла критичные баги, команда исправила их до сдачи.'}
                onChange={(e) => set('stories', e.target.value)}
              />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Подпись: имя и фамилия" hint="Добавляется в конец письма. Нейросети не передаётся.">
                <input
                  className={INPUT}
                  value={profile.full_name ?? ''}
                  placeholder="Имя Фамилия"
                  autoComplete="name"
                  onChange={(e) => set('full_name', e.target.value)}
                />
              </Field>
              <Field label="Подпись: контакты" hint="Телефон, Telegram, почта. Нейросети не передаются.">
                <input
                  className={INPUT}
                  value={profile.contacts ?? ''}
                  placeholder="+7 …, Telegram @…"
                  onChange={(e) => set('contacts', e.target.value)}
                />
              </Field>
            </div>
          </Card>
        </fieldset>
      )}

      {section === 'about' && (
        <fieldset disabled={isDemo} className="space-y-6 disabled:opacity-90">
          <Card title="Обо мне" subtitle="Контекст для оценки вакансий и писем.">
            <Field label="Как к вам обращаться" hint="Показывается в шапке сайта. Нейросети не передаётся.">
              <input
                className={`${INPUT} max-w-xs`}
                value={profile.name ?? ''}
                placeholder="Имя"
                autoComplete="given-name"
                onChange={(e) => set('name', e.target.value)}
              />
            </Field>
            <Field label="Кратко о себе одной строкой" hint="Используется в письмах и в меню профиля, например: «Аналитик и AI-разработчик»">
              <input className={INPUT} value={profile.headline} onChange={(e) => set('headline', e.target.value)} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Опыт, лет">
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  className={INPUT}
                  value={profile.experience_years ?? ''}
                  onChange={(e) => set('experience_years', e.target.value === '' ? null : Number(e.target.value))}
                />
              </Field>
              <Field label="Уровень">
                <select className={INPUT} value={profile.seniority ?? ''} onChange={(e) => set('seniority', e.target.value || null)}>
                  <option value="">не указан</option>
                  <option value="junior">Junior</option>
                  <option value="middle">Middle</option>
                  <option value="senior">Senior</option>
                </select>
              </Field>
            </div>
            <Field label="О себе (это видит нейросеть при оценке)">
              <textarea rows={3} className={INPUT} value={profile.summary} onChange={(e) => set('summary', e.target.value)} />
            </Field>
          </Card>
        </fieldset>
      )}

      {message && (
        <p
          className={`rounded-lg px-4 py-3 text-sm ${
            message.tone === 'ok'
              ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300'
              : 'bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300'
          }`}
        >
          {message.text}
        </p>
      )}

      {dirty && !isDemo && (
        <div className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 px-4 py-3 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
          <div className="mx-auto flex max-w-3xl items-center justify-between gap-3">
            <span className="text-sm text-slate-600 dark:text-slate-300">Есть несохранённые изменения</span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => setProfile(JSON.parse(saved))}>Отменить</Button>
              <Button variant="primary" onClick={save} disabled={busy !== null}>
                {busy === 'save' ? <Spinner /> : <Save className="h-4 w-4" />} Сохранить
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
