import { useEffect, useRef, useState } from 'react'
import { Compass, X } from 'lucide-react'
import { useLanguage } from '../lib/language'
import { discoveryInterests, type DiscoveryAnswers } from '../lib/discovery'
import type { InterestFocus } from '../lib/preferences'

const questions = [
  { key: 'experience', title: 'What would make this trip memorable?', choices: [
    { value: 'culture', label: 'Culture, landmarks and local food' },
    { value: 'beach', label: 'Beaches and relaxing outdoors' },
    { value: 'adventure', label: 'Adventure and nature' },
    { value: 'surprise', label: 'Keep my options open' },
  ] },
  { key: 'pace', title: 'What pace feels right?', choices: [
    { value: 'relaxed', label: 'Slow days with time to unwind' },
    { value: 'balanced', label: 'A balance of exploring and rest' },
    { value: 'active', label: 'Plenty to explore each day' },
  ] },
  { key: 'reach', title: 'How far would you like to go?', choices: [
    { value: 'nearby', label: 'Prefer a shorter journey' },
    { value: 'anywhere', label: 'Open to anywhere that fits the group' },
  ] },
] as const

export function DestinationDiscovery({ onChoose }: { onChoose: (focus: InterestFocus[], notes: string) => void }) {
  const { t, locale } = useLanguage()
  const dialog = useRef<HTMLDialogElement>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const [step, setStep] = useState(0)
  const [answers, setAnswers] = useState<DiscoveryAnswers>({ experience: 'surprise', pace: 'balanced', reach: 'anywhere' })
  const question = questions[step]
  useEffect(() => { if (dialog.current?.open) heading.current?.focus() }, [step])
  return <div className="destination-discovery">
    <button type="button" className="trip-secondary" onClick={() => { setStep(0); dialog.current?.showModal() }}><Compass size={18} aria-hidden="true" /> {t('Not sure where to go?')}</button>
    <dialog ref={dialog} className="discovery-dialog" aria-labelledby="discovery-title" aria-describedby="discovery-note">
      <div className="discovery-top"><span>{t('Question {step} of {total}', { step: (step + 1).toLocaleString(locale), total: questions.length.toLocaleString(locale) })}</span><button type="button" className="discovery-close" aria-label={t('Close')} onClick={() => dialog.current?.close()}><X size={20} /></button></div>
      <h3 id="discovery-title" ref={heading} tabIndex={-1}>{t(question.title)}</h3>
      <p id="discovery-note">{t('Three quick choices to guide the planner. Your group’s limits still apply.')}</p>
      <div className="discovery-choices" role="group" aria-labelledby="discovery-title">
        {question.choices.map((choice) => <button key={choice.value} type="button" aria-pressed={answers[question.key] === choice.value} onClick={() => setAnswers((current) => ({ ...current, [question.key]: choice.value }))}>{t(choice.label)}</button>)}
      </div>
      <div className="discovery-actions">
        <button type="button" className="trip-secondary" onClick={() => step > 0 ? setStep(step - 1) : dialog.current?.close()}>{t(step > 0 ? 'Back' : 'Cancel')}</button>
        <button type="button" className="trip-primary" onClick={() => {
          if (step < questions.length - 1) { setStep(step + 1); return }
          const result = discoveryInterests(answers)
          onChoose(result.focus, result.notes.map((note) => t(note)).join(' '))
          dialog.current?.close()
        }}>{t(step < questions.length - 1 ? 'Next' : 'Use these preferences')}</button>
      </div>
      <p className="trip-field-note">{t('Review these choices, then save your preferences.')}</p>
    </dialog>
  </div>
}
