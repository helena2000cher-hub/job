import { ClipboardList, FileUp, Link2, Save, Sparkles, Wand2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { Profile, ResumeForm, ResumeResult, ResumeSource } from '../api'
import { formatDate } from '../format'
import { Card, INPUT } from './profileUi'
import { EMPTY_FORM } from '../resumeForm'
import { ResumeFormEditor } from './ResumeFormEditor'
import { Button, Spinner } from './ui'

type Method = 'file' | 'link' | 'form'

const METHODS: { id: Method; label: string; icon: typeof FileUp }[] = [
  { id: 'file', label: 'Загрузить файл', icon: FileUp },
  { id: 'link', label: 'Дать ссылку', icon: Link2 },
  { id: 'form', label: 'Заполнить анкету', icon: ClipboardList },
]

const ACCEPT = '.pdf,.docx,.odt,.rtf,.txt'

/**
 * «Резюме»: три способа дать системе резюме — файл, ссылка или анкета как на hh.ru.
 * Любой из них пересобирает профиль: навыки из резюме добавляются, ручные правки остаются.
 */
export function ResumeSources({
  hasProfile,
  disabledHint,
  onProfile,
}: {
  hasProfile: boolean
  disabledHint?: string
  onProfile: (profile: Profile, text: string) => void
}) {
  const [source, setSource] = useState<ResumeSource | null>(null)
  const [form, setForm] = useState<ResumeForm>(EMPTY_FORM)
  const [savedForm, setSavedForm] = useState(JSON.stringify(EMPTY_FORM))
  const [method, setMethod] = useState<Method>('file')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState<'file' | 'link' | 'build' | 'save' | 'prefill' | null>(null)
  const [error, setError] = useState('')
  const [dragOver, setDragOver] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const disabled = Boolean(disabledHint)

  useEffect(() => {
    api
      .resume()
      .then((info) => {
        setSource(info.source)
        if (info.form) {
          setForm({ ...EMPTY_FORM, ...info.form })
          setSavedForm(JSON.stringify({ ...EMPTY_FORM, ...info.form }))
        }
        if (info.source?.kind === 'form') setMethod('form')
        if (info.source?.kind === 'link') setUrl(info.source.name)
      })
      .catch(() => {}) // без резюме — просто пустой блок
  }, [])

  const run = async (kind: NonNullable<typeof busy>, call: () => Promise<ResumeResult>) => {
    if (hasProfile && !window.confirm('Обновить профиль по этому резюме? Навыки из резюме добавятся к вашим, выбранные профессии и настройки останутся.')) return
    setBusy(kind)
    setError('')
    try {
      const result = await call()
      setSource(result.source)
      onProfile(result.profile, resultText(result))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const upload = (file: File | undefined) => {
    if (file) void run('file', () => api.uploadResume(file))
  }

  const saveDraft = async () => {
    setBusy('save')
    setError('')
    try {
      await api.saveResumeForm(form)
      setSavedForm(JSON.stringify(form))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const build = () =>
    run('build', async () => {
      const result = await api.buildFromForm(form)
      setSavedForm(JSON.stringify(form))
      return result
    })

  const prefill = async () => {
    setBusy('prefill')
    setError('')
    try {
      setForm({ ...EMPTY_FORM, ...(await api.prefillResumeForm()) })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const formDirty = JSON.stringify(form) !== savedForm
  const formEmpty = JSON.stringify(form) === JSON.stringify(EMPTY_FORM)

  return (
    <Card
      title="Резюме"
      subtitle="Из резюме нейросеть берёт навыки, опыт и факты для писем. Выберите удобный способ — любой обновит профиль."
    >
      <SourceLine source={source} />

      <div className="grid gap-2 sm:grid-cols-3" role="tablist" aria-label="Способ добавить резюме">
        {METHODS.map((m) => (
          <button
            key={m.id}
            type="button"
            role="tab"
            aria-selected={method === m.id}
            onClick={() => setMethod(m.id)}
            className={`flex items-center gap-2 rounded-xl px-3 py-2.5 text-left text-sm font-medium ring-1 ring-inset transition ${
              method === m.id
                ? 'bg-indigo-50 text-indigo-800 ring-2 ring-indigo-500 dark:bg-indigo-500/10 dark:text-indigo-200'
                : 'text-slate-700 ring-slate-200 hover:bg-slate-50 dark:text-slate-300 dark:ring-slate-700 dark:hover:bg-slate-800/60'
            }`}
          >
            <m.icon className="h-4 w-4 shrink-0" /> {m.label}
          </button>
        ))}
      </div>

      {disabledHint && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">{disabledHint}</p>
      )}

      {method === 'file' && (
        <div>
          <button
            type="button"
            disabled={disabled || busy !== null}
            onClick={() => fileInput.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragOver(false)
              if (!disabled && busy === null) upload(e.dataTransfer.files[0])
            }}
            className={`flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition disabled:cursor-not-allowed disabled:opacity-60 ${
              dragOver
                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-500/10'
                : 'border-slate-300 hover:border-indigo-400 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/50'
            }`}
          >
            {busy === 'file' ? <Spinner className="h-6 w-6 text-indigo-600" /> : <FileUp className="h-6 w-6 text-indigo-600" />}
            <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
              {busy === 'file' ? 'Читаю резюме и обновляю профиль… (до минуты)' : 'Перетащите файл сюда или нажмите, чтобы выбрать'}
            </span>
            <span className="text-xs text-slate-500 dark:text-slate-400">PDF, Word (DOCX), OpenDocument (ODT), RTF или TXT, до 10 МБ</span>
          </button>
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            className="hidden"
            onChange={(e) => {
              upload(e.target.files?.[0])
              e.target.value = ''
            }}
          />
          <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
            Резюме с hh.ru: откройте его на сайте → «Скачать» → PDF или Word. Старый формат .doc пересохраните в .docx.
          </p>
        </div>
      )}

      {method === 'link' && (
        <div className="space-y-2">
          <div className="flex flex-col gap-2 sm:flex-row">
            <input
              className={INPUT}
              type="url"
              value={url}
              placeholder="https://hh.ru/resume/…"
              aria-label="Ссылка на резюме"
              disabled={disabled}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && url.trim()) void run('link', () => api.resumeByLink(url))
              }}
            />
            <Button
              variant="primary"
              className="shrink-0"
              disabled={disabled || busy !== null || !url.trim()}
              onClick={() => run('link', () => api.resumeByLink(url))}
            >
              {busy === 'link' ? <Spinner /> : <Link2 className="h-4 w-4" />} Прочитать резюме
            </Button>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            hh.ru, Хабр Карьера, Google Документ с доступом по ссылке или любая открытая страница. На hh.ru у резюме
            должна быть видимость «Видно всему интернету» — закрытое резюме по ссылке не прочитать, тогда скачайте его файлом.
          </p>
        </div>
      )}

      {method === 'form' && (
        <div className="space-y-4">
          {formEmpty && source && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-indigo-50 px-3 py-2.5 text-sm text-indigo-900 dark:bg-indigo-500/10 dark:text-indigo-200">
              <span>Не заполняйте с нуля: разложу текущее резюме по полям, останется поправить.</span>
              <Button disabled={disabled || busy !== null} onClick={prefill}>
                {busy === 'prefill' ? <Spinner /> : <Wand2 className="h-4 w-4" />} Заполнить из резюме
              </Button>
            </div>
          )}
          <fieldset disabled={disabled} className="disabled:opacity-80">
            <ResumeFormEditor form={form} onChange={setForm} />
          </fieldset>
          <div className="flex flex-wrap items-center justify-end gap-2 border-t border-slate-100 pt-4 dark:border-slate-800">
            {formDirty && <span className="mr-auto text-xs text-slate-500 dark:text-slate-400">Анкета не сохранена</span>}
            <Button disabled={disabled || busy !== null || !formDirty} onClick={saveDraft}>
              {busy === 'save' ? <Spinner /> : <Save className="h-4 w-4" />} Сохранить черновик
            </Button>
            <Button variant="primary" disabled={disabled || busy !== null || formEmpty} onClick={build}>
              {busy === 'build' ? <Spinner /> : <Sparkles className="h-4 w-4" />} Собрать профиль из анкеты
            </Button>
          </div>
        </div>
      )}

      {error && <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:bg-rose-500/10 dark:text-rose-300">{error}</p>}
    </Card>
  )
}

function resultText(result: ResumeResult): string {
  const how = { file: 'из файла', link: 'по ссылке', form: 'из анкеты' }[result.source.kind]
  return `Профиль обновлён ${how}: навыков теперь ${result.profile.skills.length}. Проверьте вкладку «Навыки и профессии».`
}

function SourceLine({ source }: { source: ResumeSource | null }) {
  if (!source) {
    return <p className="text-sm text-slate-600 dark:text-slate-300">Резюме пока нет.</p>
  }
  const what =
    source.kind === 'file' ? `файл «${source.name}»` : source.kind === 'link' ? 'по ссылке' : 'анкета'
  return (
    <p className="text-sm text-slate-600 dark:text-slate-300">
      Сейчас используется: <span className="font-medium text-slate-900 dark:text-slate-100">{what}</span>
      {source.kind === 'link' && (
        <>
          {' '}
          <a href={source.name} target="_blank" rel="noreferrer" className="break-all text-indigo-700 hover:underline dark:text-indigo-300">
            {source.name}
          </a>
        </>
      )}
      <span className="text-slate-500 dark:text-slate-400"> · {formatDate(source.updated_at)}</span>
    </p>
  )
}
