// Markdown mínimo del asistente: negrita, cursiva y títulos. Devuelve segmentos planos; el render arma nodos de React.

// Marcas de cita que algunos modelos meten en el texto (【debates_origen_01】). Las citas ya van como botones.
// El `$` borra también una marca a medio llegar durante el stream.
const CITATION_MARK = /【[^】]*(】|$)/g
const HEADING = /^#{1,6}\s+(.*)$/gm
// **negrita** o *cursiva*. El grupo de captura hace que split deje los fragmentos marcados en índices impares.
const EMPHASIS = /(\*\*[^*]+?\*\*|\*[^*\s][^*]*?\*)/g

// SOLID-S (responsabilidad única): convierte el texto de la respuesta en partes, sin React ni HTML.
// Se prueba con node --test, sin renderizar nada.
/** Parte la respuesta en segmentos { type: 'text' | 'strong' | 'em', content }. No interpreta HTML. */
export function parseAnswer(text) {
  const clean = text.replace(CITATION_MARK, '').replace(HEADING, '**$1**')
  return clean.split(EMPHASIS).map((part, index) => {
    if (index % 2 === 0) return { type: 'text', content: part }
    if (part.startsWith('**')) return { type: 'strong', content: part.slice(2, -2) }
    return { type: 'em', content: part.slice(1, -1) }
  })
}
