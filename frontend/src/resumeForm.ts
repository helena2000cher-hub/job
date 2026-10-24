import type { ResumeForm } from './api'

/** Пустая анкета резюме — с неё начинают, если резюме ещё не разобрано по полям. */
export const EMPTY_FORM: ResumeForm = {
  position: '',
  city: '',
  salary: '',
  work_format: '',
  about: '',
  skills: [],
  experience: [],
  education: [],
  courses: [],
  languages: '',
}
