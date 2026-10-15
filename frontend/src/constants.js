// SOLID-D (inversión de dependencias): módulo neutral, sin imports.
// Componentes y hooks toman constantes de aquí, no de los servicios de transporte.
export const MAX_TEXT_CHARS = 1000

// Mismo breakpoint que `md` de Tailwind: por debajo, el índice y el chat ocupan toda la pantalla.
export const MOBILE_QUERY = '(max-width: 767px)'
