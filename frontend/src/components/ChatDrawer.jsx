import { BookOpen, Cloud, Cpu, Loader2, Send, Sparkles, TriangleAlert, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { MAX_TEXT_CHARS } from '../services/ws.js'

const AGENT_LABEL = {
  sending: 'Enviando…',
  thinking: 'Pensando…',
  tool_call: 'Consultando base histórica…',
}

const CONNECTION = {
  connecting: { label: 'Conectando…', dot: 'bg-amber-400' },
  open: { label: 'En línea', dot: 'bg-green-500 animate-pulse' },
  reconnecting: { label: 'Reconectando…', dot: 'bg-amber-400 animate-pulse' },
  rejected: { label: 'Conexión rechazada por el servidor', dot: 'bg-red-500' },
}

const PROVIDER = {
  local: { label: 'Local', icon: Cpu, badge: 'text-emerald-300 border-emerald-400/30' },
  cloud: { label: 'Nube', icon: Cloud, badge: 'text-sky-300 border-sky-400/30' },
}

// Marcas de cita que algunos modelos meten en el texto (【debates_origen_01】). Las citas ya van como botones.
// El `$` borra también una marca a medio llegar durante el stream.
const CITATION_MARK = /【[^】]*(】|$)/g
const HEADING = /^#{1,6}\s+(.*)$/gm
// **negrita** o *cursiva*. El grupo de captura hace que split deje los fragmentos marcados en índices impares.
const EMPHASIS = /(\*\*[^*]+?\*\*|\*[^*\s][^*]*?\*)/g

/** Markdown mínimo: negrita, cursiva y títulos. Arma nodos de React, nunca HTML: la salida del LLM no es confiable. */
function AnswerText({ text }) {
  const clean = text.replace(CITATION_MARK, '').replace(HEADING, '**$1**')
  return clean.split(EMPHASIS).map((part, index) => {
    if (index % 2 === 0) return part
    if (part.startsWith('**')) {
      return (
        <strong key={index} className="font-semibold text-white">
          {part.slice(2, -2)}
        </strong>
      )
    }
    return <em key={index}>{part.slice(1, -1)}</em>
  })
}

function ModelToggle({ models, provider, onChange, disabled }) {
  return (
    <div role="radiogroup" aria-label="Modelo de lenguaje" className="flex rounded-xl border border-white/10 bg-slate-900 p-1">
      {models.map((model) => {
        const meta = PROVIDER[model.id]
        if (!meta) return null
        const Icon = meta.icon
        const active = model.id === provider
        return (
          <button
            key={model.id}
            type="button"
            role="radio"
            aria-checked={active}
            disabled={disabled || !model.disponible}
            onClick={() => onChange(model.id)}
            title={model.disponible ? model.nombre : `${model.nombre} — falta configurar GROQ_API_KEY en .env`}
            className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition disabled:cursor-not-allowed disabled:opacity-40 ${
              active ? 'bg-blue-600 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            <Icon className="size-3.5" aria-hidden />
            {meta.label}
          </button>
        )
      })}
    </div>
  )
}

function Sources({ ids, docsById, onOpen }) {
  const docs = ids.map((id) => docsById.get(id)).filter(Boolean)
  if (docs.length === 0) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {docs.map((doc) => (
        <button
          key={doc.id}
          type="button"
          onClick={() => onOpen(doc.id)}
          className="flex items-center gap-1.5 rounded-full border border-blue-400/30 bg-blue-500/10 px-3 py-1 text-xs text-blue-200 transition hover:bg-blue-500/20"
        >
          <BookOpen className="size-3.5 shrink-0" aria-hidden />
          <span className="truncate">{doc.metadata.fecha_clave}</span>
          <span className="sr-only">: abrir {doc.titulo}</span>
        </button>
      ))}
    </div>
  )
}

function Bubble({ message, docsById, onOpenSource }) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-3xl rounded-br-none bg-blue-600 px-5 py-3 text-[15px] leading-relaxed text-white">
          {message.content}
        </p>
      </div>
    )
  }
  const isError = message.role === 'error'
  const provider = PROVIDER[message.provider]
  return (
    <div className="flex flex-col items-start">
      {provider && (
        <span className={`mb-1.5 flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider ${provider.badge}`}>
          <provider.icon className="size-3" aria-hidden />
          {provider.label}
        </span>
      )}
      {/* La salida del LLM no es confiable: AnswerText arma nodos de React y nunca se inyecta como HTML. */}
      <p
        className={`flex max-w-[85%] gap-2 whitespace-pre-wrap break-words rounded-3xl rounded-bl-none border px-5 py-3 text-[15px] leading-relaxed ${
          isError ? 'border-red-500/30 bg-red-500/10 text-red-200' : 'border-white/10 bg-slate-800/50 text-slate-200'
        }`}
      >
        {isError && <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden />}
        <span>
          {isError ? message.content : <AnswerText text={message.content} />}
          {message.streaming && <span className="ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 animate-pulse bg-blue-400" aria-hidden />}
        </span>
      </p>
      {message.sources && <Sources ids={message.sources} docsById={docsById} onOpen={onOpenSource} />}
    </div>
  )
}

export default function ChatDrawer({
  open,
  onClose,
  messages,
  pending,
  agentState,
  tool,
  detail,
  streaming,
  streamingProvider,
  connection,
  onSend,
  models,
  provider,
  onProviderChange,
  docsById,
  onOpenSource,
}) {
  const [draft, setDraft] = useState('')
  const endRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, agentState, streaming])

  useEffect(() => {
    if (!open) return undefined
    inputRef.current?.focus()
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [open, onClose])

  const text = draft.trim()
  const canSend = !pending && connection === 'open' && text.length > 0 && text.length <= MAX_TEXT_CHARS
  const status = CONNECTION[connection]

  const submit = (event) => {
    event.preventDefault()
    if (canSend && onSend(text)) setDraft('')
  }

  return (
    <>
      {open && <div className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm" onClick={onClose} aria-hidden />}
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Chat con el asistente historiador"
        inert={!open}
        className={`fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-white/5 bg-slate-950 shadow-2xl transition-transform duration-300 sm:w-[440px] ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        <header className="flex flex-wrap items-center justify-between gap-y-4 border-b border-white/5 p-6">
          <div className="flex items-center gap-4">
            <div className="flex size-11 items-center justify-center rounded-2xl bg-linear-to-br from-blue-500 to-indigo-600">
              <Sparkles className="size-5" aria-hidden />
            </div>
            <div>
              <h3 className="text-lg font-bold">Asistente Varillas</h3>
              <p className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-slate-400">
                <span className={`size-1.5 rounded-full ${status.dot}`} aria-hidden />
                {status.label}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {/* Deshabilitado durante un turno: el modelo se elige por mensaje, cambiarlo a mitad no afecta la respuesta en curso. */}
            <ModelToggle models={models} provider={provider} onChange={onProviderChange} disabled={pending} />
            <button type="button" onClick={onClose} aria-label="Cerrar chat" className="rounded-xl p-2 text-slate-400 hover:bg-white/5 hover:text-white">
              <X className="size-6" />
            </button>
          </div>
        </header>

        {/* aria-busy: el lector de pantalla anuncia la respuesta cuando termina, no cada pedazo del stream. */}
        <div className="thin-scrollbar flex-1 space-y-5 overflow-y-auto p-6" aria-live="polite" aria-busy={pending}>
          {messages.map((message) => (
            <Bubble key={message.id} message={message} docsById={docsById} onOpenSource={onOpenSource} />
          ))}
          {pending && streaming && (
            <Bubble message={{ role: 'assistant', content: streaming, provider: streamingProvider, streaming: true }} />
          )}
          {pending && !streaming && (
            <div className="flex items-center gap-3 text-xs font-semibold italic text-slate-400" role="status">
              <Loader2 className="size-5 animate-spin text-blue-400" aria-hidden />
              {AGENT_LABEL[agentState] ?? 'Pensando…'}
              {agentState === 'tool_call' && detail && <span className="not-italic text-slate-300">«{detail}»</span>}
              {agentState === 'tool_call' && tool && <code className="not-italic text-slate-500">{tool}</code>}
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form onSubmit={submit} className="border-t border-white/5 p-4">
          <div className="glass flex items-end gap-2 rounded-3xl p-2 focus-within:border-blue-500/40">
            <textarea
              ref={inputRef}
              rows={2}
              maxLength={MAX_TEXT_CHARS}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) submit(event)
              }}
              placeholder="Preguntá sobre la historia de Las Varillas…"
              aria-label="Mensaje"
              className="thin-scrollbar max-h-40 flex-1 resize-none bg-transparent px-3 py-2 text-[15px] outline-none placeholder:text-slate-500"
            />
            <button
              type="submit"
              disabled={!canSend}
              aria-label="Enviar"
              className="rounded-2xl bg-blue-600 p-3 transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Send className="size-5" />
            </button>
          </div>
          <p className="mt-2 text-right text-[11px] text-slate-500">
            {draft.length}/{MAX_TEXT_CHARS}
          </p>
        </form>
      </aside>
    </>
  )
}
