import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { parseAnswer } from './markdown.js'

describe('parseAnswer', () => {
  it('separa negrita y cursiva en segmentos', () => {
    assert.deepEqual(parseAnswer('Hola **mundo** y *tú*'), [
      { type: 'text', content: 'Hola ' },
      { type: 'strong', content: 'mundo' },
      { type: 'text', content: ' y ' },
      { type: 'em', content: 'tú' },
      { type: 'text', content: '' },
    ])
  })

  it('convierte títulos en negrita', () => {
    assert.deepEqual(parseAnswer('# Fundación\ntexto'), [
      { type: 'text', content: '' },
      { type: 'strong', content: 'Fundación' },
      { type: 'text', content: '\ntexto' },
    ])
  })

  it('quita marcas de cita, también la que queda a medio llegar', () => {
    assert.deepEqual(parseAnswer('Dato【debates_origen_01】 final'), [{ type: 'text', content: 'Dato final' }])
    assert.deepEqual(parseAnswer('Dato【debates_ori'), [{ type: 'text', content: 'Dato' }])
  })

  it('un asterisco suelto no es cursiva', () => {
    assert.deepEqual(parseAnswer('2 * 3 * 4'), [{ type: 'text', content: '2 * 3 * 4' }])
  })

  it('no interpreta HTML: lo devuelve como texto', () => {
    assert.deepEqual(parseAnswer('<img src=x onerror=alert(1)>'), [{ type: 'text', content: '<img src=x onerror=alert(1)>' }])
  })
})
