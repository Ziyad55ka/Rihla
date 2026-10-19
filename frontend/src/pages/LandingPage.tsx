import { Brand } from '../components/Brand'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../lib/language'
import '../auth.css'
import '../landing.css'

interface LandingPageProps {
  onAction: (action: 'create' | 'join') => void
  onLogin: () => void
}

function Arrow({ diagonal = false }: { diagonal?: boolean }) {
  return <svg viewBox="0 0 24 24" fill="none" width="17" height="17" aria-hidden="true"><path d={diagonal ? 'M6 18 18 6M6 6h12v12' : 'M4 12h15m-6-6 6 6-6 6'} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
}

function JourneyArtwork() {
  const { t } = useLanguage()
  return <div className="landing-artwork" aria-hidden="true">
    <svg className="landing-route-lines" viewBox="0 0 600 570" fill="none">
      <path d="M5 120h140c30 0 30 49 60 49h175c33 0 33 80 66 80h150M0 140h135c30 0 30 49 60 49h172c35 0 35 80 75 80h158M98 0v88c0 22 75 22 75 44v230c0 24 80 24 80 48v160M118 0v78c0 22 75 22 75 44v230c0 24 80 24 80 48v170M0 460h92c24 0 24-44 48-44h292c24 0 24-44 48-44h120" stroke="currentColor" />
      <circle cx="98" cy="35" r="5" fill="currentColor" /><circle cx="570" cy="249" r="5" fill="currentColor" /><circle cx="37" cy="460" r="5" fill="currentColor" /><circle cx="273" cy="532" r="5" fill="currentColor" />
    </svg>

    <div className="landing-ticket-card">
      <div className="landing-ticket-top"><span className="landing-mini-mark">↗</span><span>{t("THE NEXT CHAPTER")}</span><span>01</span></div>
      <p>{t("Somewhere")}<br />{t("worth sharing.")}</p>
      <div className="landing-ticket-map">
        <svg viewBox="0 0 270 115" fill="none"><path d="m-15 95 70-52 52 23 60-50 49 44 78-24M-10 109l72-50 48 23 62-49 42 43 83-25" stroke="currentColor" opacity=".22" /><path d="M38 80c38-9 42-32 73-25s44 15 67-13 41-17 59-13" stroke="currentColor" strokeWidth="1.3" strokeDasharray="3 5" /><circle cx="38" cy="80" r="5" stroke="currentColor" /><circle cx="237" cy="29" r="5" fill="currentColor" /><path d="m137 57 13-17 3 13-16 4Z" fill="currentColor" /></svg>
      </div>
      <div className="landing-ticket-bottom"><span>{t("YOUR PEOPLE. YOUR POSSIBILITIES.")}</span><span>↗</span></div>
    </div>

    <div className="landing-people-card">
      <span className="landing-card-label">{t("GOOD COMPANY COMES FIRST")}</span>
      <div className="landing-people-row"><div className="landing-avatar landing-avatar--one">A</div><div className="landing-avatar landing-avatar--two">S</div><div className="landing-avatar landing-avatar--three">N</div><span className="landing-people-plus">+</span></div>
      <p>{t("Bring your people.")}<br /><span>{t("Find your common ground.")}</span></p>
      <div className="landing-card-footnote"><span className="landing-mini-dot" /> {t("One group. One place to plan.")}</div>
    </div>

    <div className="landing-dates-card">
      <span className="landing-dates-icon"><svg width="19" height="19" viewBox="0 0 24 24" fill="none"><rect x="4" y="6" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="1.4" /><path d="M8 3v6m8-6v6M4 11h16m-11 5 2 2 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" /></svg></span>
      <div><span className="landing-card-label">{t("LESS BACK AND FORTH")}</span><p>{t("A little planning.")}<br /><span>{t("A lot to look forward to.")}</span></p></div>
    </div>
    <span className="landing-orbit landing-orbit--one">✦</span><span className="landing-orbit landing-orbit--two">✳</span>
    <span className="landing-artwork-caption">{t("A JOURNEY TAKES SHAPE, TOGETHER.")}</span>
  </div>
}

const steps = [
  { number: '01', title: 'Bring your people.', text: 'Create a trip and share an invitation. Your group has one place to get started.', icon: 'people' },
  { number: '02', title: 'Make room for everyone.', text: 'Add your dates, budget, and travel preferences. Your detailed inputs stay private.', icon: 'preferences' },
  { number: '03', title: 'Find your common ground.', text: 'See when your group is ready and which travel dates work for everyone.', icon: 'dates' },
]

function StepIcon({ icon }: { icon: string }) {
  return <svg viewBox="0 0 32 32" fill="none" width="29" height="29" aria-hidden="true">
    {icon === 'people' ? <><circle cx="13" cy="11" r="4" /><path d="M5 26v-3a8 8 0 0 1 16 0v3m0-20a4 4 0 0 1 0 8m6 12v-3a8 8 0 0 0-4-7" /></>
      : icon === 'preferences' ? <><path d="M6 8h20M6 16h20M6 24h20" /><circle cx="12" cy="8" r="3" /><circle cx="22" cy="16" r="3" /><circle cx="11" cy="24" r="3" /></>
      : <><rect x="5" y="7" width="22" height="22" rx="3" /><path d="M11 3v8m10-8v8M5 14h22m-15 6 3 3 6-6" /></>}
  </svg>
}

export function LandingPage({ onAction, onLogin }: LandingPageProps) {
  const { t } = useLanguage()
  return <div className="landing-page">
    <a className="auth-skip-link" href="#main">{t("Skip to content")}</a>
    <div className="landing-main-panel">
      <header className="landing-header rihla-navbar">
        <Brand />
        <nav className="landing-nav rihla-navbar-links" aria-label={t("Main navigation")}><a href="/" aria-current="page">{t('Home')}</a><a href="#about">{t('About Rihla')}</a></nav>
        <div className="rihla-navbar-actions"><button className="landing-signup rihla-navbar-action" type="button" onClick={onLogin}>{t('Login / Sign up')} <Arrow diagonal /></button><LanguageSwitcher /></div>
      </header>

      <main id="main">
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <p className="landing-eyebrow"><span /> {t('YOUR NEXT JOURNEY STARTS WITH YOUR PEOPLE')}</p>
            <h1 id="landing-title">{t('Good company.')}<br /><span>{t('Great journeys.')}</span></h1>
            <p className="landing-hero-description">{t("Turn “we should go somewhere” into a plan.")}<br className="landing-desktop-break" /> {t("Bring everyone’s dates, budgets, and ideas together.")}<br className="landing-desktop-break" /> {t("Make space for a journey you’ll share.")}</p>
            <div className="landing-hero-actions"><button className="landing-action landing-action--primary" type="button" onClick={() => onAction('create')}>{t('Create a trip')} <Arrow /></button><button className="landing-action landing-action--secondary" type="button" onClick={() => onAction('join')}>{t('Join a trip')} <Arrow diagonal /></button></div>
            <p className="landing-hero-note"><span className="landing-note-symbol" aria-hidden="true">✧</span> {t("A little less organizing. A lot more looking forward.")}</p>
          </div>
          <JourneyArtwork />
        </section>

        <section id="about" className="landing-about" aria-labelledby="landing-about-title">
          <div className="landing-about-intro"><p className="landing-eyebrow"><span /> {t('THIS IS RIHLA')}</p><h2 id="landing-about-title">{t('Different people.')}<br /><span>{t('One shared adventure.')}</span></h2><p>{t('A group trip starts with a lot of moving parts. Rihla brings them into one calm place, helping your group find dates that overlap and a starting point that works for everyone.')}</p></div>
          <div className="landing-steps">{steps.map((step) => <article className="landing-step" key={step.number}><div className="landing-step-top"><StepIcon icon={step.icon} /><span>{step.number}</span></div><h3>{t(step.title)}</h3><p>{t(step.text)}</p></article>)}</div>
        </section>

        <section className="landing-closing" aria-labelledby="landing-closing-title"><div><p className="landing-eyebrow">{t("START WITH THE PEOPLE. THE REST COMES TOGETHER.")}</p><h2 id="landing-closing-title">{t("Your next chapter")}<br /><span>{t("is a shared one.")}</span></h2></div><button className="landing-action landing-action--primary" type="button" onClick={() => onAction('create')}>{t("Let’s plan a trip")} <Arrow /></button><svg aria-hidden="true" viewBox="0 0 650 230" fill="none"><path d="M0 180h120c35 0 35-100 70-100h150c35 0 35 100 70 100h240M0 197h130c35 0 35-100 70-100h130c35 0 35 100 70 100h250" stroke="currentColor" /><circle cx="507" cy="180" r="5" fill="currentColor" /></svg></section>
      </main>

      <footer className="landing-footer"><Brand /><span>{t("Good company. Great journeys.")}</span><span>رحلة <span aria-hidden="true">/</span> {t("A journey worth sharing.")}</span></footer>
    </div>
  </div>
}
