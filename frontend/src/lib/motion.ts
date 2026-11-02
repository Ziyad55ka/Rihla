import { type RefObject, useEffect, useLayoutEffect, useRef, useState } from 'react'

const COUNT_MS = 900

/** Eases from one number to another, for progress between 0 and 1. */
export function countUpValue(from: number, to: number, progress: number): number {
  const eased = 1 - (1 - Math.min(Math.max(progress, 0), 1)) ** 3
  return from + (to - from) * eased
}

/**
 * A number that counts up when it scrolls into view, then glides to any new value.
 * Attach `ref` to the element showing it. Reduced motion is handled in the CSS only.
 */
export function useCountUp<T extends Element>(target: number): { value: number; ref: RefObject<T | null> } {
  const [value, setValue] = useState(target)
  const current = useRef(0)
  const ref = useRef<T>(null)
  const first = useRef(true)
  useLayoutEffect(() => { if (first.current && target > 0) setValue(0) }, [target])
  useEffect(() => {
    let frame = 0
    const run = () => {
      const from = current.current
      const start = performance.now()
      const step = (time: number) => {
        const progress = (time - start) / COUNT_MS
        current.current = progress >= 1 ? target : countUpValue(from, target, progress)
        setValue(current.current)
        if (progress < 1) frame = requestAnimationFrame(step)
      }
      frame = requestAnimationFrame(step)
    }
    const element = ref.current
    if (!first.current || !element || typeof IntersectionObserver === 'undefined') {
      first.current = false
      run()
      return () => cancelAnimationFrame(frame)
    }
    first.current = false
    const observer = new IntersectionObserver((entries) => {
      if (!entries.some((entry) => entry.isIntersecting)) return
      observer.disconnect()
      run()
    }, { threshold: 0.2 })
    observer.observe(element)
    return () => { observer.disconnect(); cancelAnimationFrame(frame) }
  }, [target])
  return { value, ref }
}

/** Each part of the page rises in as it scrolls into view, a little after the last. */
export function useSectionReveal(root: RefObject<HTMLElement | null>) {
  useLayoutEffect(() => {
    const element = root.current
    if (!element || typeof IntersectionObserver === 'undefined') return
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue
        entry.target.classList.remove('details-pending')
        observer.unobserve(entry.target)
      }
    }, { threshold: 0.05 })
    element.querySelectorAll<HTMLElement>(':scope>section').forEach((part, index) => {
      part.style.setProperty('--reveal-delay', `${Math.min(index, 3) * 90}ms`)
      part.classList.add('details-pending')
      observer.observe(part)
    })
    return () => observer.disconnect()
  }, [root])
}
