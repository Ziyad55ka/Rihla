import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from 'react'

const COUNT_MS = 350

export function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion:reduce)').matches
}

/** Eases from one number to another, for progress between 0 and 1. */
export function countUpValue(from: number, to: number, progress: number): number {
  const eased = 1 - (1 - Math.min(Math.max(progress, 0), 1)) ** 3
  return from + (to - from) * eased
}

/** A number that glides to its new value, or jumps when motion is reduced. */
export function useCountUp(target: number): number {
  const [shown, setShown] = useState(target)
  const current = useRef(target)
  useEffect(() => {
    const from = current.current
    if (from === target) return
    if (prefersReducedMotion()) { current.current = target; setShown(target); return }
    const start = performance.now()
    let frame = 0
    const step = (time: number) => {
      const progress = (time - start) / COUNT_MS
      current.current = progress >= 1 ? target : countUpValue(from, target, progress)
      setShown(current.current)
      if (progress < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target])
  return shown
}

/** Each part of the page rises in as it scrolls into view, a little after the last. */
export function useSectionReveal(root: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const element = root.current
    if (!element || prefersReducedMotion() || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        entry.target.classList.remove('details-pending')
        observer.unobserve(entry.target)
      }
    }, { threshold: 0.05 })
    element.querySelectorAll<HTMLElement>(':scope>section,:scope>header').forEach((part, index) => {
      part.style.setProperty('--reveal-delay', `${Math.min(index, 3) * 50}ms`)
      part.classList.add('details-pending')
      observer.observe(part)
    })
    return () => observer.disconnect()
  }, [root])
}
