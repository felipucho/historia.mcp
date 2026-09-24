export const MAX_TEXT_CHARS = 1000
export const CLOSE_POLICY_VIOLATION = 1008

const EVENT_TYPES = new Set(['status', 'delta', 'response', 'error'])

export function chatSocketUrl() {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat`
}

/** Devuelve el evento si respeta el contrato del backend; null en cualquier otro caso. */
export function parseServerEvent(raw) {
  try {
    const event = JSON.parse(raw)
    return EVENT_TYPES.has(event?.type) ? event : null
  } catch {
    return null
  }
}

/**
 * Backoff exponencial con jitter (0.5s, 1s, 2s… tope 30s).
 * El jitter evita que todos los clientes reconecten en el mismo instante cuando vuelve el backend.
 */
export function reconnectDelay(attempt, baseMs = 500, maxMs = 30_000) {
  const ceiling = Math.min(maxMs, baseMs * 2 ** attempt)
  return ceiling / 2 + Math.random() * (ceiling / 2)
}
