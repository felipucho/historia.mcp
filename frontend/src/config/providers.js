import { Cloud, Cpu } from 'lucide-react'

// SOLID-O (abierto/cerrado): la presentación de cada proveedor (nombre, ícono) vive aquí.
// Agregar un proveedor es una entrada nueva. Los componentes que la leen no cambian.
// Presentación de cada proveedor del selector. Qué proveedores existen y cuáles están disponibles lo dice /api/modelos.
// Un proveedor nuevo en el backend (llm/catalog.py) necesita una entrada acá: sin ella el selector no lo muestra.
export const PROVIDERS = {
  local: { label: 'Local', icon: Cpu, badge: 'text-emerald-300 border-emerald-400/30' },
  cloud: { label: 'Nube', icon: Cloud, badge: 'text-sky-300 border-sky-400/30' },
}

export const DEFAULT_PROVIDER = 'local'

// Si /api/modelos falla, el selector igual ofrece el local: es el único que no depende de configuración.
export const FALLBACK_MODELS = [{ id: DEFAULT_PROVIDER, nombre: 'Local', disponible: true }]
