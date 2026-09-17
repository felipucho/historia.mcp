import { ChevronLeft, ChevronRight, MessageSquare } from 'lucide-react'
import { useCallback, useEffect, useReducer, useState } from 'react'

import ChatDrawer from './components/ChatDrawer.jsx'
import Reader from './components/Reader.jsx'
import Sidebar from './components/Sidebar.jsx'
import { useWebSocket } from './hooks/useWebSocket.js'
import { fetchFundacion } from './services/api.js'
import { chatSocketUrl } from './services/ws.js'

const SOCKET_URL = chatSocketUrl()
const MOBILE_QUERY = '(max-width: 767px)'

const initialChat = {
  messages: [{ id: 0, role: 'assistant', content: 'Hola, soy el asistente historiador de Las Varillas. Preguntame sobre su fundación.' }],
  pending: false,
  agentState: 'idle',
  tool: null,
}

// Lista append-only: el índice sirve de id estable y el reducer queda puro.
const append = (chat, role, content) => [...chat.messages, { id: chat.messages.length, role, content }]
const settle = { pending: false, agentState: 'idle', tool: null }

function chatReducer(chat, action) {
  switch (action.type) {
    case 'sent':
      return { ...chat, messages: append(chat, 'user', action.text), pending: true, agentState: 'sending', tool: null }
    case 'status':
      return action.state === 'idle' ? chat : { ...chat, agentState: action.state, tool: action.tool ?? null }
    case 'response':
      return { ...chat, ...settle, messages: append(chat, 'assistant', action.content) }
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

export default function App() {
  const [docs, setDocs] = useState([])
  const [loadError, setLoadError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(() => !window.matchMedia(MOBILE_QUERY).matches)
  const [chatOpen, setChatOpen] = useState(false)
  const [chat, dispatch] = useReducer(chatReducer, initialChat)

  useEffect(() => {
    const controller = new AbortController()
    fetchFundacion(controller.signal)
      .then((data) => setDocs(data.raw))
      .catch((error) => {
        if (error.name !== 'AbortError') setLoadError(error.message)
      })
    return () => controller.abort()
  }, [])

  const { status: connection, send } = useWebSocket(SOCKET_URL, {
    // parseServerEvent solo deja pasar status/response/error: cada evento es una acción del reducer.
    onEvent: dispatch,
    onClose: () => dispatch({ type: 'closed' }),
  })

  const handleSend = useCallback(
    (text) => {
      if (!send({ text })) {
        dispatch({ type: 'offline' })
        return false
      }
      dispatch({ type: 'sent', text })
      return true
    },
    [send],
  )

  const navigate = useCallback((id) => {
    const target = document.getElementById(id)
    if (!target) return
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' })
    target.focus({ preventScroll: true })
    if (window.matchMedia(MOBILE_QUERY).matches) setSidebarOpen(false)
  }, [])

  const closeChat = useCallback(() => setChatOpen(false), [])

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar docs={docs} open={sidebarOpen} onNavigate={navigate} />
      {sidebarOpen && <div className="fixed inset-0 z-20 bg-black/50 md:hidden" onClick={() => setSidebarOpen(false)} aria-hidden />}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-white/5 bg-slate-950/40 px-4 backdrop-blur-xl md:h-20 md:px-10">
          <div className="flex min-w-0 items-center gap-3 md:gap-6">
            <button
              type="button"
              onClick={() => setSidebarOpen((value) => !value)}
              aria-label={sidebarOpen ? 'Ocultar índice' : 'Mostrar índice'}
              aria-expanded={sidebarOpen}
              className="rounded-xl p-2.5 text-slate-400 transition hover:bg-slate-800 hover:text-white"
            >
              {sidebarOpen ? <ChevronLeft className="size-5" /> : <ChevronRight className="size-5" />}
            </button>
            <div className="min-w-0">
              <h1 className="truncate text-xl font-bold md:text-2xl">
                Las Varillas <span className="text-blue-500">Digital</span>
              </h1>
              <p className="hidden text-[10px] font-bold uppercase tracking-[0.3em] text-slate-500 sm:block">Archivo histórico</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setChatOpen(true)}
            className="flex shrink-0 items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 font-semibold shadow-lg shadow-blue-600/20 transition hover:bg-blue-500"
          >
            <MessageSquare className="size-[18px]" aria-hidden />
            <span className="hidden sm:inline">Consultar agente</span>
          </button>
        </header>

        <Reader docs={docs} error={loadError} />
      </div>

      <ChatDrawer
        open={chatOpen}
        onClose={closeChat}
        messages={chat.messages}
        pending={chat.pending}
        agentState={chat.agentState}
        tool={chat.tool}
        connection={connection}
        onSend={handleSend}
      />
    </div>
  )
}
