import { useEffect } from 'react'

// Observe new route content too, without delaying forms or interactive controls.
export function PageMotion() {
  useEffect(() => {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (reduced.matches || !('IntersectionObserver' in window)) return
    const selector = '.landing-about-intro, .landing-step, .landing-closing, .trip-card, .planning-member-card, .account-card, .trip-state-panel, .dashboard-note'
    const observed = new Set<Element>()
    const reveal = (element: Element) => { element.setAttribute('data-reveal', 'visible'); intersection.unobserve(element); observed.delete(element) }
    const intersection = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) reveal(entry.target)
    }, { threshold: 0.08 })
    function prepare(root: Element) {
      const elements = [...(root.matches(selector) ? [root] : []), ...root.querySelectorAll(selector)]
      for (const element of elements) {
        if (element.hasAttribute('data-reveal')) continue
        element.setAttribute('data-reveal', 'pending')
        observed.add(element)
        intersection.observe(element)
      }
    }
    prepare(document.body)
    const mutations = new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) if (node instanceof Element) prepare(node)
      // Detached cards should not be retained when navigating away from a page.
      for (const element of observed) if (!element.isConnected) { intersection.unobserve(element); observed.delete(element) }
    })
    mutations.observe(document.body, { childList: true, subtree: true })
    const stop = () => {
      mutations.disconnect(); intersection.disconnect()
      for (const element of observed) element.setAttribute('data-reveal', 'visible')
      observed.clear()
    }
    const onPreferenceChange = () => { if (reduced.matches) stop() }
    reduced.addEventListener('change', onPreferenceChange)
    return () => { stop(); reduced.removeEventListener('change', onPreferenceChange) }
  }, [])
  return null
}
