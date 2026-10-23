import { authorizationHeaders } from '../api/client'
import { samePrincipal, type Classes } from './types'

export type Chat = {
  schemaVersion: 'instruct.chat.v2'; sessionId: string; principal: Classes['principal']
  classId: string | null; model: string; message: string
  observations: { factId: string; kind: string; evidenceRefs: string[]; [key: string]: unknown }[]
  citations: { refId: string; title: string; source: string; locator: string; excerpt: string }[]
  observationCitations?: Chat['citations']
}
export const stages = ['model', 'fabric', 'foundry', 'work', 'validation'] as const
export type Stage = typeof stages[number]
export type ChatProgress = {
  stage: Stage
  state: 'running' | 'succeeded' | 'failed' | 'unavailable' | 'disabled'
  message: string
  durationMs: number | null
  evidenceCount: number | null
}
const base = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export function assertChat(data: Chat, catalog: Classes): void {
  if (data?.schemaVersion !== 'instruct.chat.v2' || !samePrincipal(data.principal, catalog.principal)
    || typeof data.sessionId !== 'string' || typeof data.message !== 'string'
    || typeof data.model !== 'string' || !data.model.startsWith('gpt-5.6')
    || !Array.isArray(data.observations) || !Array.isArray(data.citations)
    || (data.observationCitations !== undefined && !Array.isArray(data.observationCitations))
    || (data.classId !== null && !catalog.classes.some(c => c.classId === data.classId))) {
    throw Error('Invalid or out-of-scope chat response.')
  }
}

export async function streamChat(
  message: string, sessionId: string | null, catalog: Classes, token: string | null,
  onProgress: (event: ChatProgress) => void, signal: AbortSignal,
): Promise<Chat> {
  const response = await fetch(`${base}/api/instruct/v1/chat`, {
    method: 'POST',
    headers: { ...authorizationHeaders(token), 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ schemaVersion: 'instruct.chat.request.v2', message, sessionId }), signal,
  })
  if (!response.ok) {
    let message = `Chat unavailable (${response.status}). No simulated answer was used.`
    if (response.headers.get('content-type')?.includes('application/json')) {
      const body = await response.json()
      if (typeof body.error?.message === 'string') message = body.error.message
    }
    throw Error(message)
  }
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    throw Error('Expected live chat status. Refresh after the API has been updated.')
  }
  const reader = response.body.getReader(), decoder = new TextDecoder()
  let buffer = '', sequence = 0, requestId = ''
  let final: Chat | undefined
  const states = new Map<Stage, ChatProgress['state']>()
  function frame(text: string) {
    const lines = text.split(/\r?\n/)
    const json = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
    if (!json) return
    const event = JSON.parse(json)
    const name = lines.find(line => line.startsWith('event:'))?.slice(6).trim()
    if (final || event.schemaVersion !== 'instruct.chat.event.v1' || event.type !== name
      || event.sequence !== sequence++ || typeof event.requestId !== 'string' || !event.requestId
      || (requestId && event.requestId !== requestId)) throw Error('Invalid chat status sequence.')
    if (event.sequence === 0) {
      if (name !== 'started') throw Error('Chat status did not start correctly.')
      requestId = event.requestId
    } else if (name === 'progress') {
      const p = event.payload as ChatProgress
      if (!p || !stages.includes(p.stage) || typeof p.message !== 'string'
        || !['running', 'succeeded', 'failed', 'unavailable', 'disabled'].includes(p.state)
        || (p.durationMs !== null && (!Number.isFinite(p.durationMs) || p.durationMs < 0))
        || (p.evidenceCount !== null && (!Number.isInteger(p.evidenceCount) || p.evidenceCount < 0))
        || (p.state === 'running' ? states.get(p.stage) === 'running' : states.get(p.stage) !== 'running')) {
        throw Error('Invalid chat step lifecycle.')
      }
      states.set(p.stage, p.state)
      onProgress(p)
    } else if (name === 'final') {
      assertChat(event.payload, catalog)
      if (states.get('validation') !== 'succeeded' || [...states.values()].includes('running')) {
        throw Error('Chat ended before answer validation.')
      }
      final = event.payload
    } else if (name === 'error') {
      throw Error(typeof event.payload?.message === 'string' ? event.payload.message : 'Chat failed.')
    } else throw Error('Unexpected chat status event.')
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (signal.aborted) throw new DOMException('Cancelled', 'AbortError')
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() ?? ''
      frames.forEach(frame)
      if (done) break
    }
    if (buffer.trim()) frame(buffer)
    if (!final) throw Error('Chat status stream interrupted. No answer was accepted.')
    return final
  } finally {
    try { await reader.cancel() }
    catch { console.warn('Could not close the chat status stream reader.') }
    finally { reader.releaseLock() }
  }
}
