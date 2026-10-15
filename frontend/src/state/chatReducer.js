// Estado del chat y su reducer. Sin React: se prueba directo con node --test.

export const initialChat = {
  messages: [{ id: 0, role: 'assistant', content: 'Hola, soy el asistente historiador de Las Varillas. Preguntame sobre su fundación.' }],
  pending: false,
  agentState: 'idle',
  tool: null,
  detail: null,
  // Texto que el modelo va generando en el turno en curso; el evento response lo reemplaza por el final.
  streaming: '',
  streamingProvider: null,
}

// Lista append-only: el índice sirve de id estable y el reducer queda puro.
const append = (chat, role, content, extra) => [...chat.messages, { id: chat.messages.length, role, content, ...extra }]
const settle = { pending: false, agentState: 'idle', tool: null, detail: null, streaming: '' }

// SOLID-S (responsabilidad única): estado del chat como función pura, sin React.
// Recibe estado y acción, devuelve el estado nuevo. Se prueba con node --test.
export function chatReducer(chat, action) {
  switch (action.type) {
    case 'sent':
      return {
        ...chat,
        messages: append(chat, 'user', action.text),
        pending: true,
        agentState: 'sending',
        tool: null,
        detail: null,
        streaming: '',
        streamingProvider: action.provider,
      }
    case 'status':
      if (action.state === 'idle') return chat
      // tool_call: lo escrito antes era un preámbulo del modelo, no la respuesta.
      return {
        ...chat,
        agentState: action.state,
        tool: action.tool ?? null,
        detail: action.detail ?? null,
        streaming: action.state === 'tool_call' ? '' : chat.streaming,
      }
    case 'delta':
      return chat.pending ? { ...chat, streaming: chat.streaming + action.content } : chat
    case 'response':
      return {
        ...chat,
        ...settle,
        messages: append(chat, 'assistant', action.content, { provider: action.provider, sources: action.sources ?? [] }),
      }
    case 'error':
      // busy: el turno anterior sigue en curso, el indicador no se corta.
      return action.code === 'busy'
        ? { ...chat, messages: append(chat, 'error', action.message) }
        : { ...chat, ...settle, messages: append(chat, 'error', action.message) }
    case 'closed':
      return chat.pending ? { ...chat, ...settle, messages: append(chat, 'error', 'Se perdió la conexión con el servidor. Reintentando…') } : chat
    case 'offline':
      return { ...chat, messages: append(chat, 'error', 'Sin conexión con el servidor. Esperá a que se reconecte.') }
    default:
      return chat
  }
}
