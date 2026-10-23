import { authorizationHeaders, RequestError } from '../api/client'
import { sources, samePrincipal, type Classes, type Conversation, type Draft, type Evidence, type Final, type PlanRequest, type Principal, type Source, type SourceState } from './types'

const base = `${(import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')}/api/instruct/v1`
export type Progress = { source: Source; state: SourceState; reason: string | null }
async function checked(response: Response) {
  if (!response.ok) {
    let message = `Request failed (${response.status}).`
    try {
      const body = await response.json()
      if (body.schemaVersion === 'instruct.error.v1') message = `${body.error.message} [${body.error.code}; request ${body.requestId}]`
    } catch { /* A gateway may return a non-JSON error. */ }
    throw new RequestError(message, response.status)
  }
  return response
}
export async function getClasses(token: string | null, signal?: AbortSignal): Promise<Classes> {
  const body = await (await checked(await fetch(`${base}/classes`, { headers: authorizationHeaders(token), signal }))).json()
  if (body.schemaVersion !== 'instruct.classes.v1' || !body.principal || !Array.isArray(body.classes)) throw Error('Invalid classes response.')
  return body
}
export async function converse(context: PlanRequest, message: string, draft: Draft | null, principal: Principal, token: string | null, signal: AbortSignal): Promise<Conversation> {
  const artifact = draft ? { planId: draft.scope.planId, baselineSha256: draft.baselineSha256, edits: draft.edits } : null
  const body = await (await checked(await fetch(`${base}/conversation`, {
    method: 'POST', headers: { ...authorizationHeaders(token), 'Content-Type': 'application/json' },
    body: JSON.stringify({ schemaVersion: 'instruct.conversation.request.v1', context, message, artifact }), signal,
  }))).json() as Conversation
  if (body.schemaVersion !== 'instruct.conversation.v1' || !samePrincipal(body.principal, principal) || body.classId !== context.classId || body.assessmentId !== context.assessmentId || body.mode !== 'bounded_commands' || typeof body.message !== 'string' || !Array.isArray(body.evidenceRefs) || !Array.isArray(body.followups)) throw Error('Conversation scope mismatch.')
  if (body.plan) assertFinal(body.plan, context, principal)
  if (body.proposal && (!draft || body.proposal.planId !== draft.scope.planId || body.proposal.baselineSha256 !== draft.baselineSha256 || body.proposal.editRevision !== draft.edits.length)) throw Error('Proposal scope mismatch.')
  return body
}
export async function getEvidence(token: string | null, principal: Principal, classId: string, planId: string, refId: string, signal?: AbortSignal): Promise<Evidence> {
  const path = [classId, planId, refId].map(encodeURIComponent)
  const body = await (await checked(await fetch(`${base}/classes/${path[0]}/plans/${path[1]}/evidence/${path[2]}`, { headers: authorizationHeaders(token), signal }))).json()
  if (body.schemaVersion !== 'instruct.evidence.v1' || !samePrincipal(body.principal, principal) || body.classId !== classId || body.planId !== planId || body.evidence.refId !== refId || body.evidence.classId !== classId) throw Error('Evidence scope mismatch.')
  return body.evidence
}
export function assertFinal(body: Final, request: PlanRequest, principal: Principal) {
  const p = body?.result
  if (body?.schemaVersion !== 'instruct.final.v1' || p?.schemaVersion !== 'instruct.plan.v1' || p.requestId !== body.requestId || p.classId !== request.classId || p.assessmentId !== request.assessmentId || !samePrincipal(p.principal, principal) || p.executionMode !== 'connected' || !['complete', 'partial', 'blocked'].includes(p.status) || p.sources.length !== 4 || sources.some(s => p.sources.filter(b => b.source === s).length !== 1) || p.sources.some(s => s.state === 'running')) throw Error('Invalid or out-of-scope final response.')
}
export async function streamPlan(request: PlanRequest, principal: Principal, token: string | null, onProgress: (p: Progress) => void, signal: AbortSignal): Promise<Final> {
  const response = await checked(await fetch(`${base}/plan/stream`, {
    method: 'POST', headers: { ...authorizationHeaders(token), 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(request), signal,
  }))
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) throw Error('Expected an instructional event stream.')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = '', sequence = 0, requestId = ''
  let final: Final | undefined
  const states = new Map<Source, SourceState>()
  const transitions: Partial<Record<SourceState, SourceState[]>> = { running: ['succeeded', 'failed', 'unavailable'] }
  const frame = (text: string) => {
    const lines = text.split(/\r?\n/)
    const data = lines.filter(l => l.startsWith('data:')).map(l => l.slice(5).trimStart()).join('\n')
    if (!data) return
    const event = JSON.parse(data)
    const name = lines.find(l => l.startsWith('event:'))?.slice(6).trim()
    if (final || event.schemaVersion !== 'instruct.event.v1' || event.type !== name || event.sequence !== sequence++ || (requestId && event.requestId !== requestId)) throw Error('Invalid stream sequence.')
    if (event.sequence === 0) {
      if (event.type !== 'started') throw Error('Stream did not start correctly.')
      requestId = event.requestId
    } else if (event.type === 'source') {
      const prior = states.get(event.source)
      if (!sources.includes(event.source) || (prior ? !transitions[prior]?.includes(event.state) : !['not_requested', 'disabled', 'unavailable', 'running'].includes(event.state))) throw Error('Invalid source lifecycle.')
      states.set(event.source, event.state)
      onProgress(event)
    } else if (event.type === 'final') {
      assertFinal(event.payload, request, principal)
      if (event.payload.requestId !== requestId || states.size !== 4 || event.payload.result.sources.some((s: Progress) => states.get(s.source) !== s.state)) throw Error('Final source states do not match progress.')
      final = event.payload
    } else if (event.type === 'error') {
      throw Error(event.payload?.error?.message ?? 'Planning failed.')
    } else throw Error('Unexpected stream event.')
  }
  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += done ? decoder.decode() : decoder.decode(value, { stream: true })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() ?? ''
      frames.forEach(frame)
      if (done) break
    }
    if (buffer.trim()) frame(buffer)
    if (!final) throw Error('Planning stream interrupted before a final result. Retry explicitly.')
    return final
  } finally {
    await reader.cancel().catch(() => {})
    reader.releaseLock()
  }
}
