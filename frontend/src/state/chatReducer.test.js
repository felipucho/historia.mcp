import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { chatReducer, initialChat } from './chatReducer.js'

const sent = (chat, text = 'hola', provider = 'local') => chatReducer(chat, { type: 'sent', text, provider })

describe('chatReducer', () => {
  it('enviar agrega la pregunta y deja el turno pendiente', () => {
    const next = sent(initialChat, 'hola', 'cloud')
    assert.equal(next.messages.at(-1).role, 'user')
    assert.equal(next.messages.at(-1).content, 'hola')
    assert.equal(next.pending, true)
    assert.equal(next.agentState, 'sending')
    assert.equal(next.streamingProvider, 'cloud')
  })

  it('delta solo se acumula durante un turno pendiente', () => {
    assert.equal(chatReducer(initialChat, { type: 'delta', content: 'x' }), initialChat)
    const streaming = chatReducer(sent(initialChat), { type: 'delta', content: 'Hola' })
    assert.equal(chatReducer(streaming, { type: 'delta', content: ' mundo' }).streaming, 'Hola mundo')
  })

  it('tool_call descarta el texto escrito antes como preámbulo', () => {
    const pending = chatReducer(sent(initialChat), { type: 'delta', content: 'Voy a buscar' })
    const next = chatReducer(pending, { type: 'status', state: 'tool_call', tool: 'consultar_fundacion_las_varillas', detail: 'tren' })
    assert.equal(next.streaming, '')
    assert.equal(next.agentState, 'tool_call')
    assert.equal(next.tool, 'consultar_fundacion_las_varillas')
    assert.equal(next.detail, 'tren')
  })

  it('status idle no cambia el estado', () => {
    const pending = sent(initialChat)
    assert.equal(chatReducer(pending, { type: 'status', state: 'idle' }), pending)
  })

  it('response cierra el turno, agrega la respuesta con sus fuentes y limpia el streaming', () => {
    const streaming = chatReducer(sent(initialChat), { type: 'delta', content: 'parcial' })
    const next = chatReducer(streaming, { type: 'response', content: 'Final', provider: 'local', sources: ['debates_origen_01'] })
    assert.equal(next.pending, false)
    assert.equal(next.streaming, '')
    assert.deepEqual(next.messages.at(-1), {
      id: next.messages.length - 1,
      role: 'assistant',
      content: 'Final',
      provider: 'local',
      sources: ['debates_origen_01'],
    })
  })

  it('response sin sources deja la lista vacía', () => {
    const next = chatReducer(sent(initialChat), { type: 'response', content: 'Ok', provider: 'local' })
    assert.deepEqual(next.messages.at(-1).sources, [])
  })

  it('error busy agrega el aviso sin cortar el turno en curso', () => {
    const next = chatReducer(sent(initialChat), { type: 'error', code: 'busy', message: 'Todavía estoy respondiendo' })
    assert.equal(next.pending, true)
    assert.equal(next.messages.at(-1).role, 'error')
  })

  it('otro error cierra el turno', () => {
    const next = chatReducer(sent(initialChat), { type: 'error', code: 'llm_unavailable', message: 'Sin modelo' })
    assert.equal(next.pending, false)
    assert.equal(next.messages.at(-1).content, 'Sin modelo')
  })

  it('cerrar la conexión con un turno en curso avisa y cierra el turno', () => {
    const next = chatReducer(sent(initialChat), { type: 'closed' })
    assert.equal(next.pending, false)
    assert.match(next.messages.at(-1).content, /Se perdió la conexión/)
  })

  it('cerrar la conexión sin turno en curso no cambia nada', () => {
    assert.equal(chatReducer(initialChat, { type: 'closed' }), initialChat)
  })

  it('offline agrega el aviso sin tocar el turno', () => {
    const next = chatReducer(initialChat, { type: 'offline' })
    assert.equal(next.messages.at(-1).role, 'error')
    assert.equal(next.pending, false)
  })

  it('una acción desconocida devuelve el mismo estado', () => {
    assert.equal(chatReducer(initialChat, { type: 'nada' }), initialChat)
  })
})
