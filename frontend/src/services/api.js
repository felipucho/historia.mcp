/** GET /api/fundacion → { raw, full_text }. Ruta relativa: en dev la resuelve el proxy de Vite. */
export async function fetchFundacion(signal) {
  const response = await fetch('/api/fundacion', { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) {
    throw new Error(`el backend respondió ${response.status}`)
  }
  const data = await response.json()
  if (!Array.isArray(data?.raw)) {
    throw new Error('respuesta inesperada de /api/fundacion')
  }
  return data
}

/** GET /api/modelos → [{ id: 'local' | 'cloud', nombre, disponible }]. */
export async function fetchModelos(signal) {
  const response = await fetch('/api/modelos', { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) {
    throw new Error(`el backend respondió ${response.status}`)
  }
  const data = await response.json()
  if (!Array.isArray(data)) {
    throw new Error('respuesta inesperada de /api/modelos')
  }
  return data
}
