import { RefObject, useEffect } from 'react';

export function useClickOutside<T extends HTMLElement>(ref: RefObject<T>, onOutsideClick: () => void, active = true) {
  useEffect(() => {
    if (!active) return;
    function handler(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onOutsideClick();
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [ref, onOutsideClick, active]);
}
