import { useEffect, useRef, useState } from 'react';

/** Toggles a "visible" flag the first time the element scrolls into view, for a one-shot
 *  fade/slide-in effect on marketing pages (Landing) — not used on app pages, where content
 *  should just be there, not animate in every time. */
export function useScrollReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, isVisible };
}
