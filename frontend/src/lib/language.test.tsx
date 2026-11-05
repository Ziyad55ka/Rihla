import { afterEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { ReactNode } from 'react'
import { LanguageProvider, translate, type Language } from './language'
import { LandingPage } from '../pages/LandingPage'
import { AuthForm } from '../components/AuthForm'
import { JoinTripForm } from '../components/TripForms'
import { PlanningPanel } from '../components/PlanningPanel'
import type { TripDetail } from '../types/trips'

vi.mock('./supabase', () => ({ supabase: null, supabaseConfiguration: { state: 'not-configured', message: '' } }))
afterEach(() => vi.unstubAllGlobals())

function render(language: Language, children: ReactNode) {
  vi.stubGlobal('localStorage', { getItem: () => language })
  return renderToStaticMarkup(<LanguageProvider>{children}</LanguageProvider>)
}

describe('Arabic and English UI', () => {
  it('renders the whole landing page in Arabic, including the artwork and account action', () => {
    const markup = render('ar', <LandingPage onAction={() => {}} onLogin={() => {}} />)
    for (const text of ['رحلتك القادمة تبدأ مع من تحب', 'الرفقة الجميلة أولًا', 'دخول / إنشاء حساب', 'EN']) expect(markup).toContain(text)
    for (const text of ['Bring your people.', 'THE NEXT CHAPTER', 'Turn “we should go somewhere” into a plan.', 'Login / Sign up']) expect(markup).not.toContain(text)
    expect(markup.match(/class="landing-signup /g)).toHaveLength(1)
    expect(markup).not.toContain('landing-login')
  })
  it('renders English copy with the AR switch', () => {
    const markup = render('en', <LandingPage onAction={() => {}} onLogin={() => {}} />)
    expect(markup).toContain('Login / Sign up')
    expect(markup).toContain('Switch to Arabic')
    expect(markup).toContain('>AR</button>')
  })
  it('translates signup hints, button labels and invitation help', () => {
    const signup = render('ar', <AuthForm initialMode="signup" />)
    expect(signup).toContain('تأكيد كلمة المرور')
    expect(signup).toContain('إنشاء حسابي')
    expect(signup).not.toContain('Create my account')
    expect(signup).not.toContain('At least 8 characters')
    const join = render('ar', <JoinTripForm initialInvitation={null} onJoined={() => {}} onBack={() => {}} />)
    expect(join).toContain('رمز الدعوة')
    expect(join.match(/trip-code-box/g)).toHaveLength(6)
    expect(join).toContain('one-time-code')
    expect(join).not.toContain('Invitations are valid')
    const link = render('en', <JoinTripForm initialInvitation={'https://rihla.example/#invite=' + 'a'.repeat(64)} onJoined={() => {}} onBack={() => {}} />)
    expect(link).toContain('Invitation link')
    expect(link).not.toContain('trip-code-box')
  })
  it('translates trip controls without translating user-entered trip/member names', () => {
    const trip = { id: 'demo', title: 'My London trip', description: '', role: 'administrator', member_count: 1,
      members: [{ user_id: 'demo-user', display_name: 'Ibrahim', role: 'administrator' }] } as TripDetail
    const markup = render('ar', <PlanningPanel trip={trip} revision={0} onRefresh={() => {}} onPreferences={() => {}} />)
    expect(markup).toContain('My London trip')
    expect(markup).toContain('Ibrahim')
    expect(markup).toContain('دعوة أعضاء')
    expect(markup).not.toContain('Different people. One adventure.')
    expect(markup).not.toContain('Unavailable')
  })
  it('interpolates dates/counts and translates errors from stored English messages', () => {
    expect(translate('ar', 'Saved {date}', { date: '١٨ أكتوبر' })).toBe('تم الحفظ في ١٨ أكتوبر')
    expect(translate('en', '{count} days together', { count: 5 })).toBe('5 days together')
    expect(translate('ar', 'The passwords do not match.')).toBe('كلمتا المرور غير متطابقتين.')
    expect(translate('en', 'The passwords do not match.')).toBe('The passwords do not match.')
    expect(translate('ar', 'The request failed (HTTP 422). Check your input and try again.')).toContain('422')
    expect(translate('ar', '__proto__')).toBe('__proto__')
  })
})
