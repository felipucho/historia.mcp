import { useCallback, useEffect, useRef, useState } from 'react'

import { CLOSE_POLICY_VIOLATION, parseServerEvent, reconnectDelay } from '../services/ws.js'

/**
 * Conexión WebSocket persistente con reconexión por backoff.
 * status: 'connecting' | 'open' | 'reconnecting' | 'rejected'
 */
export function useWebSocket(url, { onEvent, onClose }) {
  const [status, setStatus] = useState('connecting')
  const socketRef = useRef(null)
  const handlersRef = useRef({ onEvent, onClose })

  // Handlers siempre actuales sin reabrir el socket en cada render.
  useEffect(() => {
    handlersRef.current = { onEvent, onClose }
  })

  useEffect(() => {
    let attempt = 0
    let timer = null
    let disposed = false

    const connect = () => {
      const socket = new WebSocket(url)
      socketRef.current = socket

      socket.onopen = () => {
        attempt = 0
        setStatus('open')
      }
      socket.onmessage = (message) => {
        const event = parseServerEvent(message.data)
        if (event) handlersRef.current.onEvent(event)
      }
      socket.onclose = (close) => {
        // Un socket descartado (StrictMode, unmount) cierra tarde: no debe pisar la ref del socket vivo.
        if (socketRef.current === socket) socketRef.current = null
        if (disposed) return
        handlersRef.current.onClose?.()
        if (close.code === CLOSE_POLICY_VIOLATION) {
          setStatus('rejected') // origen no permitido: reintentar no lo arregla
          return
        }
        setStatus('reconnecting')
        timer = setTimeout(connect, reconnectDelay(attempt++))
      }
    }

    connect()
    return () => {
      // Sin este flag, el onclose del cleanup reprogramaría una reconexión fantasma.
      disposed = true
      clearTimeout(timer)
      socketRef.current?.close(1000)
    }
  }, [url])

  const send = useCallback((payload) => {
    const socket = socketRef.current
    if (socket?.readyState !== WebSocket.OPEN) return false
    socket.send(JSON.stringify(payload))
    return true
  }, [])

  return { status, send }
}
