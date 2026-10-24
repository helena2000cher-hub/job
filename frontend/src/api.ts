// Типы и вызовы backend API (FastAPI, backend/app/api/main.py)

export type Mark = 'saved' | 'hidden' | null

export type Stage =
  | 'interesting'
  | 'applied'
  | 'no_response'
  | 'questionnaire'
  | 'test_task'
  | 'interview'
  | 'offer'
  | 'rejected'

export type Tone = 'business' | 'friendly'

export interface Application {
  stage: Stage
  notes: string
  contact: string
  applied_at: string | null
  cover_letter: string
  cover_letter_subject: string
  cover_letter_tone: string | null
  updated_at: string
  stage_changed_at: string | null
}

export interface FeedItem {
  id: string
  title: string
  company: string | null
  region: string | null
  salary_from: number | null
  salary_to: number | null
  currency: string
  is_remote: boolean
  source: string
  url: string
  published_at: string | null
  score: number | null
  similarity: number | null
  verdict: string
  matched_skills: string[]
  missing_skills: string[]
  red_flags: string[]
  mark: Mark
  stage: Stage | null
}

export interface TrackerItem extends FeedItem {
  application: Application
}

export interface VacancyDetail extends FeedItem {
  employment: string | null
  schedule: string | null
  experience_years: number | null
  education: string | null
  requirements: string | null
  duties: string | null
  conditions: string | null
  skills: string[]
  fetched_at: string
  application: Application | null
}

export interface Feed {
  items: FeedItem[]
  total_vacancies: number
  scored: number
  sources: Record<string, number>
  profile_ready: boolean
  last_fetched_at: string | null
}

export interface Preferences {
  remote_only: boolean
  regions: string[]
  salary_min: number | null
  employment_types: string[]
  stop_words: string[]
}

export type CareerKind = 'core' | 'adjacent' | 'new_field'

export interface CareerOption {
  title: string
  field: string
  kind: CareerKind
  fit: number
  why: string
  transferable: string[]
  gaps: string[]
  queries: string[]
}

export interface CareerSuggestions {
  options: CareerOption[]
  generated_at: string
  skills_snapshot: string[]
  extra_snapshot: string
}

export interface Profile {
  name: string
  headline: string
  target_roles: string[]
  skills: string[]
  experience_years: number | null
  seniority: string | null
  industries: string[]
  education: string | null
  summary: string
  extra: string
  stories: string
  full_name: string
  contacts: string
  search_queries: string[]
  search_mode: 'professions' | 'skills' | 'both'
  search_skills: string[]
  preferences: Preferences
  careers: CareerSuggestions | null
}

export interface ResumeJob {
  company: string
  position: string
  start: string
  end: string
  description: string
}

export interface ResumeStudy {
  institution: string
  faculty: string
  specialty: string
  year: string
}

export interface ResumeCourse {
  name: string
  organization: string
  year: string
}

/** Анкета как на hh.ru. ФИО и контакты — в подписи профиля, здесь их нет. */
export interface ResumeForm {
  position: string
  city: string
  salary: string
  work_format: string
  about: string
  skills: string[]
  experience: ResumeJob[]
  education: ResumeStudy[]
  courses: ResumeCourse[]
  languages: string
}

export interface ResumeSource {
  kind: 'file' | 'link' | 'form'
  name: string
  updated_at: string
  chars: number
}

export interface ResumeInfo {
  source: ResumeSource | null
  form: ResumeForm | null
}

export interface ResumeResult {
  profile: Profile
  source: ResumeSource
}

export interface RefreshState {
  running: boolean
  started_at: string | null
  finished_at: string | null
  log: string[]
  error: string | null
  new_vacancies: number
  scored: number
  cost_dollars: number
}

export interface Me {
  role: 'owner' | 'user' | 'demo'
  auth_enabled: boolean
  demo_available: boolean
  internals?: boolean // личный режим: показывать стоимость и названия сервисов
  registration?: boolean // можно зарегистрироваться
  providers?: Record<string, string> // вход одной кнопкой: { yandex: 'Яндекс ID', vk: 'VK ID' }
  email?: string | null
  name?: string
}

// Платные действия пользователя за сегодня: поиск, письма, разбор резюме…
export type LimitAction = 'refresh' | 'letter' | 'resume' | 'careers' | 'advice' | 'manual'
export type Limits = Partial<Record<LimitAction, { used: number; limit: number }>>

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export interface RateRow {
  label: string
  sent: number
  positive: number
  rate: number
}

export interface Advice {
  summary: string
  resume: string[]
  letters: string[]
  search: string[]
  generated_at: string
  based_on_sent: number
}

export interface Analytics {
  total: number
  stages: Partial<Record<Stage, number>>
  sent: number
  sent_last_7_days: number
  positive: number
  rejected: number
  no_response: number
  waiting: number
  response_rate: number | null
  by_letter: RateRow[]
  by_score: RateRow[]
  by_source: RateRow[]
  top_gaps: { skill: string; count: number }[]
  no_response_days: number
  sent_list: SentItem[]
  advice: Advice | null
}

export interface SentItem {
  id: string
  title: string
  company: string | null
  url: string
  source: string
  score: number | null
  stage: Stage
  applied_at: string | null
  days_since: number | null
  has_letter: boolean
  notes: string
}

export interface ManualApplicationIn {
  url: string
  title: string
  company: string
  stage: Stage
  applied_at: string | null
  notes: string
}

export interface ManualApplicationOut {
  vacancy_id: string
  title: string
  company: string | null
  fetched: boolean
  application: Application
}

export type FeedView = 'all' | 'saved' | 'hidden'

export const OFFLINE_MESSAGE =
  'Нет связи с сервером. Скорее всего, он остановлен — запустите start.bat ещё раз и обновите страницу.'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    // fetch падает без ответа, только когда сервер недоступен
    throw new ApiError(0, OFFLINE_MESSAGE)
  }
  // 502/504 отдаёт прокси разработки (localhost:5173), когда сам сервер на :8000 выключен
  if (response.status === 502 || response.status === 504) {
    throw new ApiError(0, OFFLINE_MESSAGE)
  }
  if (!response.ok) {
    let message = `Ошибка ${response.status}`
    try {
      const body = await response.json()
      if (typeof body.detail === 'string') message = body.detail
    } catch {
      /* тело не JSON — оставляем код ошибки */
    }
    throw new ApiError(response.status, message)
  }
  return response.json() as Promise<T>
}

export const api = {
  me: () => request<Me>('/api/auth/me'),
  login: (password: string, email = '') =>
    request<Me>('/api/auth/login', { method: 'POST', body: JSON.stringify({ password, email }) }),
  logout: () => fetch('/api/auth/logout', { method: 'POST' }),
  register: (email: string, password: string, consent: boolean) =>
    request<{ status: string; email: string }>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, consent }),
    }),
  forgotPassword: (email: string) =>
    request<{ status: string }>('/api/auth/forgot', { method: 'POST', body: JSON.stringify({ email }) }),
  resetPassword: (token: string, password: string) =>
    request<Me>('/api/auth/reset', { method: 'POST', body: JSON.stringify({ token, password }) }),
  deleteAccount: async () => {
    const response = await fetch('/api/auth/account', { method: 'DELETE' })
    if (!response.ok) throw new ApiError(response.status, 'Не удалось удалить аккаунт')
  },
  limits: () => request<Limits>('/api/limits'),
  feed: (params: { minScore: number; source: string; view: FeedView }) => {
    const query = new URLSearchParams({ min_score: String(params.minScore), view: params.view })
    if (params.source) query.set('source', params.source)
    return request<Feed>(`/api/feed?${query}`)
  },
  vacancy: (id: string) => request<VacancyDetail>(`/api/vacancies/${encodeURIComponent(id)}`),
  mark: (id: string, status: Mark) =>
    request(`/api/vacancies/${encodeURIComponent(id)}/mark`, {
      method: 'PUT',
      body: JSON.stringify({ status }),
    }),
  applications: () => request<TrackerItem[]>('/api/applications'),
  updateApplication: (id: string, patch: Partial<Omit<Application, 'updated_at'>>) =>
    request<Application>(`/api/applications/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(patch),
    }),
  addManualApplication: (body: ManualApplicationIn) =>
    request<ManualApplicationOut>('/api/applications/manual', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  deleteApplication: (id: string) =>
    fetch(`/api/applications/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  coverLetter: (id: string, tone: Tone, wishes: string, mentionGaps = true) =>
    request<Application>(`/api/applications/${encodeURIComponent(id)}/cover-letter`, {
      method: 'POST',
      body: JSON.stringify({ tone, wishes, mention_gaps: mentionGaps }),
    }),
  analytics: () => request<Analytics>('/api/analytics'),
  makeAdvice: () => request<Advice>('/api/analytics/advice', { method: 'POST' }),
  profile: () => request<Profile>('/api/profile'),
  saveProfile: (profile: Profile) =>
    request<Profile>('/api/profile', { method: 'PUT', body: JSON.stringify(profile) }),
  suggestCareers: () => request<Profile>('/api/profile/careers', { method: 'POST' }),
  rebuildProfile: () => request<Profile>('/api/profile/rebuild', { method: 'POST' }),
  resume: () => request<ResumeInfo>('/api/resume'),
  uploadResume: (file: File) =>
    request<ResumeResult>(`/api/resume/file?filename=${encodeURIComponent(file.name)}`, {
      method: 'POST',
      body: file,
      headers: { 'Content-Type': 'application/octet-stream' },
    }),
  resumeByLink: (url: string) =>
    request<ResumeResult>('/api/resume/link', { method: 'POST', body: JSON.stringify({ url }) }),
  saveResumeForm: (form: ResumeForm) =>
    request<ResumeInfo>('/api/resume/form', { method: 'PUT', body: JSON.stringify(form) }),
  buildFromForm: (form: ResumeForm) =>
    request<ResumeResult>('/api/resume/form/build', { method: 'POST', body: JSON.stringify(form) }),
  prefillResumeForm: () => request<ResumeForm>('/api/resume/form/prefill', { method: 'POST' }),
  sources: () => request<Record<string, boolean>>('/api/sources'),
  refreshStatus: () => request<RefreshState>('/api/refresh'),
  refresh: (sources: string[]) =>
    request<RefreshState>('/api/refresh', { method: 'POST', body: JSON.stringify({ sources }) }),
}
