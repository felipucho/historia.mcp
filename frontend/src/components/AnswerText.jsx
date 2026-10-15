import { parseAnswer } from '../lib/markdown.js'

// SOLID-S (responsabilidad única): solo dibuja las partes que devuelve parseAnswer.
// La interpretación del markdown está en lib/markdown.js.
/** Markdown mínimo como nodos de React. Nunca HTML: la salida del LLM no es confiable. */
export default function AnswerText({ text }) {
  return parseAnswer(text).map((segment, index) => {
    if (segment.type === 'strong') {
      return (
        <strong key={index} className="font-semibold text-white">
          {segment.content}
        </strong>
      )
    }
    if (segment.type === 'em') return <em key={index}>{segment.content}</em>
    return segment.content
  })
}
