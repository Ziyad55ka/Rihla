import { Brand } from '../components/Brand'
import { ProposalsView } from '../components/ProposalsPanel'
import { LanguageSwitcher } from '../components/LanguageSwitcher'
import { useLanguage } from '../lib/language'
import { mockSelectionStore } from '../lib/activities'
import data from '../data/activities.mock.json'
import type { ProposalSet, StoredProposals } from '../types/proposal'

const stored: StoredProposals = {
  ...(data as ProposalSet), version: 1, complete: true,
  generated_at: null, generating: false, needs_regeneration: false,
}
const store = mockSelectionStore({
  getItem: key => localStorage.getItem(key),
  setItem: (key, value) => localStorage.setItem(key, value),
})

export function ActivitiesDemo() {
  const { t } = useLanguage()
  const preview = { ...stored, proposals: stored.proposals.map(proposal => ({
    ...proposal,
    flights: proposal.flights.slice(0, 1),
    title: t(proposal.title.replace(/^MOCK: /, '')),
    destination: t(proposal.destination),
    cities: proposal.cities.map(city => ({
      ...city, city: t(city.city), activities: city.activities?.map(activity => ({
        ...activity,
        name: { ...activity.name, value: t(activity.name.value?.replace(/^MOCK: /, '').split(' — ')[0] ?? 'Not available') },
        description: { ...activity.description, value: t(activity.category === 'restaurant' ? 'A suggested local meal. The price is an estimate per person.' : 'A little time to explore, at your own pace.') },
        location: { ...activity.location, value: t(city.city) },
        duration: { ...activity.duration, value: t(activity.duration.value ?? 'Not available') },
      })),
    })),
  })) }
  return <div className="landing-page activities-experience"><div className="landing-main-panel">
    <header className="landing-header rihla-navbar">
      <Brand />
      <nav className="landing-nav rihla-navbar-links" aria-label={t('Main navigation')}><a href="/">{t('Home')}</a><a href="#activity-options" aria-current="page">{t('Activities')}</a></nav>
      <div className="rihla-navbar-actions"><a className="rihla-navbar-action" href="#activity-options">{t('Explore activities')} <span aria-hidden="true">↗</span></a><LanguageSwitcher /></div>
    </header>
    <main>
      <div className="activities-intro">
        <h1>{t('Choose the details of your journey.')}</h1>
        <p>{t('Choose the experiences that make this journey yours.')}</p>
      </div>
      <section id="activity-options" className="activities-options">
        <p className="activities-demo-notice" role="status"><span aria-hidden="true">◌</span>{t('Demo activities: synthetic data, saved only in this browser.')}</p>
        <ProposalsView isAdmin={false} conflicts={null} stored={preview} busy={false} error="" notice="" onGenerate={() => {}} selectionStore={store} />
      </section>
    </main>
    <footer className="landing-footer"><Brand /><span>{t('Rihla — a journey worth sharing.')}</span><span>{t('Plan together. Go further.')}</span></footer>
  </div></div>
}
