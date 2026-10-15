import { useCallback } from 'react'

import { MOBILE_QUERY } from '../constants.js'

// SOLID-S (responsabilidad única): solo navega a un documento (scroll, foco, cierre del índice en móvil).
// App usa el hook y no conoce los detalles del scroll.
/** Salta al documento del lector: scroll (salto directo con reduce-motion), foco sin mover la página y cierre del índice en móvil. */
export function useDocNavigation(setSidebarOpen) {
  return useCallback(
    (id) => {
      const target = document.getElementById(id)
      if (!target) return
      const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
      target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
      target.focus({ preventScroll: true })
      if (window.matchMedia(MOBILE_QUERY).matches) setSidebarOpen(false)
    },
    [setSidebarOpen],
  )
}
