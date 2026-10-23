/// <reference types="node" />
import { readFileSync } from 'node:fs'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'
import Workspace from './Workspace'
import { assertFinal, converse, getClasses, getEvidence, streamPlan } from './client'
import { applyProposal, inverseChanges } from './conversation'
import { canonical, digest, draftKey, editDraft, exportDraft, invalidatedClaims, listDrafts, loadDraft, markdown, newDraft, normalizePlan, replay, saveDraft, validateDraft } from './draft'
import { scenario, type Change, type Draft, type Final, type PlanRequest } from './types'

// Contract fixtures are test inputs only; production modules never import them.
function fixture<T>(name: string): T {
  return JSON.parse(readFileSync(new URL(`../../../../docs/contracts/examples/${name}.json`, import.meta.url), 'utf8'))
}
const principal = { tenantId: 'tenant-synthetic', subject: 'teacher-synthetic' }
const request: PlanRequest = { schemaVersion: 'instruct.request.v1', classId: 'class-science-7a', assessmentId: 'assessment-20261016', scenario, includeWork: false, includeWeb: false }
const connected = (name: string) => {
  const body = fixture<Final>(name)
  body.result.executionMode = 'connected'
  return body
}
function events(body: Final) {
  const initial = body.result.sources.map((s, i) => ({ type: 'source', schemaVersion: 'instruct.event.v1', requestId: body.requestId, sequence: i + 1, source: s.source, state: s.state === 'succeeded' || s.state === 'failed' ? 'running' : s.state, reason: s.reason }))
  const data: Record<string, unknown>[] = [{ type: 'started', schemaVersion: 'instruct.event.v1', requestId: body.requestId, sequence: 0 }, ...initial]
  for (const s of body.result.sources.filter(s => ['succeeded', 'failed'].includes(s.state))) data.push({ type: 'source', schemaVersion: 'instruct.event.v1', requestId: body.requestId, sequence: data.length, source: s.source, state: s.state, reason: s.reason })
  data.push({ type: 'final', schemaVersion: 'instruct.event.v1', requestId: body.requestId, sequence: data.length, payload: body })
  return data
}
function stream(data: Record<string, unknown>[], chunk = 53) {
  const text = `: heartbeat\r\n\r\n${data.map(e => `event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`).join('')}`
  const encoded = new TextEncoder().encode(text)
  return new Response(new ReadableStream({ start(c) { for (let i = 0; i < encoded.length; i += chunk) c.enqueue(encoded.slice(i, i + chunk)); c.close() } }), { headers: { 'Content-Type': 'text/event-stream' } })
}
const callStream = (onProgress = vi.fn()) => streamPlan(request, principal, 'test-token', onProgress, new AbortController().signal)
afterEach(() => vi.unstubAllGlobals())

describe('instructional authenticated transport', () => {
  it.each(['complete', 'partial', 'blocked'])('accepts %s finals without manufacturing missing sections', async name => {
    const body = connected(name), progress = vi.fn()
    const fetch = vi.fn().mockResolvedValue(stream(events(body)))
    vi.stubGlobal('fetch', fetch)
    expect(await callStream(progress)).toEqual(body)
    expect(progress).toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
    const init = fetch.mock.calls[0][1]
    expect(init.headers.Authorization).toBe('Bearer test-token')
    expect(JSON.parse(init.body)).toEqual(request)
    if (name === 'blocked') expect(body.result.package).toBeNull()
    if (name === 'partial') expect(body.result.groups.length).toBeGreaterThan(0)
  })
  it('preserves requested disabled/unavailable/not-requested source states', async () => {
    const body = connected('blocked'), progress = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream(events(body), 1)))
    await callStream(progress)
    expect(progress.mock.calls.map(([p]) => p.state)).toEqual(['disabled', 'unavailable', 'not_requested', 'not_requested'])
  })
  it('does not retry REST after an interrupted stream', async () => {
    const fetch = vi.fn().mockResolvedValue(stream(events(connected('blocked')).slice(0, -1)))
    vi.stubGlobal('fetch', fetch)
    await expect(callStream()).rejects.toThrow('interrupted')
    expect(fetch).toHaveBeenCalledOnce()
  })
  it('forwards cancellation without accepting a final or retrying', async () => {
    const abort = new AbortController(), progress = vi.fn()
    const fetch = vi.fn((_url: unknown, init: RequestInit) => {
      expect(init.signal).toBe(abort.signal)
      return Promise.reject(new DOMException('Cancelled', 'AbortError'))
    })
    vi.stubGlobal('fetch', fetch)
    abort.abort()
    await expect(streamPlan(request, principal, 'token', progress, abort.signal)).rejects.toThrow('Cancelled')
    expect(progress).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledOnce()
  })
  it.each(['sequence', 'scope', 'state', 'duplicate'])('rejects %s corruption', async kind => {
    const data = events(connected('blocked'))
    if (kind === 'sequence') data[1].sequence = 15
    if (kind === 'scope') (data.at(-1)!.payload as Final).result.classId = 'other-class'
    if (kind === 'state') data[1].state = 'succeeded'
    if (kind === 'duplicate') data.push(data.at(-1)!)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream(data)))
    await expect(callStream()).rejects.toThrow()
  })
  it('rejects terminal errors and sanitized pre-stream authorization failures', async () => {
    const data = events(connected('blocked')).slice(0, 1)
    data.push({ type: 'error', schemaVersion: 'instruct.event.v1', requestId: data[0].requestId, sequence: 1, payload: { error: { message: 'Composition failed.' } } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(stream(data)))
    await expect(callStream()).rejects.toThrow('Composition failed.')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ schemaVersion: 'instruct.error.v1', requestId: 'r1', error: { code: 'forbidden', message: 'Access denied.' } }), { status: 403 })))
    await expect(callStream()).rejects.toThrow('Access denied.')
  })
  it('rejects examples and crossed principals in production finals', () => {
    expect(() => assertFinal(fixture('complete'), request, principal)).toThrow()
    expect(() => assertFinal(connected('complete'), request, { ...principal, subject: 'other' })).toThrow()
  })
  it('resolves classes and evidence through scoped authorized routes', async () => {
    const evidence = fixture<Final>('complete').result.sources[0].evidence[0]
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({ schemaVersion: 'instruct.classes.v1', principal, classes: [] }))).mockResolvedValueOnce(new Response(JSON.stringify({ schemaVersion: 'instruct.evidence.v1', principal, classId: request.classId, planId: 'p1', evidence })))
    vi.stubGlobal('fetch', fetch)
    expect((await getClasses('token')).classes).toEqual([])
    expect(await getEvidence('token', principal, request.classId, 'p1', evidence.refId)).toEqual(evidence)
    expect(fetch.mock.calls[1][0]).toContain(`/classes/${request.classId}/plans/p1/evidence/${evidence.refId}`)
    fetch.mockResolvedValue(new Response(JSON.stringify({ schemaVersion: 'instruct.evidence.v1', principal: { ...principal, subject: 'other' }, classId: request.classId, planId: 'p1', evidence })))
    await expect(getEvidence('token', principal, request.classId, 'p1', evidence.refId)).rejects.toThrow('scope')
  })
})
function memoryStorage(): Storage {
  const data = new Map<string, string>()
  return { get length() { return data.size }, clear: () => data.clear(), key: n => [...data.keys()][n] ?? null, getItem: k => data.get(k) ?? null, setItem: (k, v) => { data.set(k, v) }, removeItem: k => { data.delete(k) } }
}
const change = (path: string, before: Change['before'], after: Change['after']): Change => ({ path, before, after, provenance: 'teacher_edit_unverified' })
describe('scoped browser drafts', () => {
  it('matches the Python canonical contract fixture hash and replays ordered edits', async () => {
    const d = fixture<Draft>('draft')
    d.baseline = normalizePlan(d.baseline)
    expect(await digest(d.baseline)).toBe(d.baselineSha256)
    await expect(validateDraft(d, principal, d.scope.classId, d.scope.planId)).resolves.toEqual(d)
    expect(replay(d).groups[0].scaffold.text).not.toBe(d.baseline.groups[0].scaffold.text)
    expect(canonical({ z: 'é', a: 1 })).toBe('{"a":1,"z":"é"}')
  })
  it('preserves baseline and exact revisions through edit, reload and lossless export', async () => {
    const storage = memoryStorage(), original = await newDraft(fixture<Final>('complete').result)
    const baseline = structuredClone(original.baseline), c = baseline.groups[0].rationale
    const first = editDraft(original, [change('/groups/0/rationale/text', c.text, 'Teacher interpretation')])
    const reviewed: Draft = { ...first, state: 'reviewed', review: { reviewer: principal, reviewedAt: new Date().toISOString(), editRevision: 1, meaning: 'teacher_review_only_not_published' } }
    const next = editDraft(reviewed, [change('/groups/0/rationale/text', 'Teacher interpretation', 'Revised interpretation')])
    expect(next.review).toBeNull()
    expect(next.state).toBe('edited')
    expect(next.baseline).toEqual(baseline)
    expect(invalidatedClaims(next).has(c.claimId)).toBe(true)
    saveDraft(storage, next)
    const loaded = await loadDraft(storage, principal, baseline.classId, baseline.planId)
    expect(loaded).toEqual(next)
    expect(replay(loaded).groups[0].rationale.text).toBe('Revised interpretation')
    expect(exportDraft(loaded, 'json').draft).toEqual(next)
    expect(exportDraft(loaded, 'json').markdown).toBeNull()
    expect(markdown(loaded)).toContain('generated citations no longer support this claim')
    expect(markdown(loaded)).toContain('Teacher review only; not published')
  })
  it('isolates class, plan, schema and principal storage keys', async () => {
    const storage = memoryStorage(), d = await newDraft(fixture<Final>('complete').result)
    saveDraft(storage, d)
    expect(listDrafts(storage, principal, d.scope.classId)).toEqual([d.scope.planId])
    expect(listDrafts(storage, { ...principal, subject: 'other' }, d.scope.classId)).toEqual([])
    expect(listDrafts(storage, principal, 'other-class')).toEqual([])
    await expect(loadDraft(storage, principal, 'other-class', d.scope.planId)).rejects.toThrow()
    await expect(loadDraft(storage, principal, d.scope.classId, 'other-plan')).rejects.toThrow()
    expect(draftKey({ tenantId: 'a:b', subject: 'c' }, 'd', 'e')).not.toBe(draftKey({ tenantId: 'a', subject: 'b:c' }, 'd', 'e'))
  })
  it.each(['hash', 'schema', 'scope', 'review', 'before', 'invalidation'])('fails safely on invalid %s', async kind => {
    let d = await newDraft(fixture<Final>('complete').result)
    d = editDraft(d, [change('/groups/0/scaffold/text', d.baseline.groups[0].scaffold.text, 'Changed scaffold')])
    if (kind === 'hash') d.baseline.planId = 'tampered'
    if (kind === 'schema') (d as unknown as { schemaVersion: string }).schemaVersion = 'instruct.draft.v2'
    if (kind === 'scope') d.scope.principal = { ...principal, subject: 'other' }
    if (kind === 'review') d.state = 'reviewed'
    if (kind === 'before') d.edits[0].changes[0].before = 'wrong'
    if (kind === 'invalidation') d.edits[0].invalidatedClaimIds = []
    await expect(validateDraft(d, principal, request.classId, 'plan-demo-001')).rejects.toThrow()
  })
  it('requires atomic membership+rationale edits and a complete nonempty roster partition', async () => {
    const d = await newDraft(fixture<Final>('complete').result), g = d.baseline.groups
    expect(() => editDraft(d, [change('/groups/0/studentIds', g[0].studentIds, ['student-02'])])).toThrow('rationale')
    expect(() => editDraft(d, [change('/groups/0/studentIds', g[0].studentIds, []), change('/groups/0/rationale/text', g[0].rationale.text, 'Changed')])).toThrow('empty')
    const swapped = editDraft(d, [change('/groups/0/studentIds', g[0].studentIds, g[1].studentIds), change('/groups/1/studentIds', g[1].studentIds, g[0].studentIds), change('/groups/0/rationale/text', g[0].rationale.text, 'Teacher reassigned to graph check'), change('/groups/1/rationale/text', g[1].rationale.text, 'Teacher reassigned to evidence check')])
    expect(replay(swapped).groups[0].studentIds).toEqual(g[1].studentIds)
    expect(invalidatedClaims(swapped).size).toBe(2)
  })
  it('restricts paths, text and total duration without claiming semantic approval', async () => {
    const d = await newDraft(fixture<Final>('complete').result), s = d.baseline.package!.segments[0]
    expect(() => editDraft(d, [change('/package/segments/0/minutes', s.minutes, s.minutes + 1)])).toThrow('35 minutes')
    expect(() => editDraft(d, [change('/groups/0/rationale/text', d.baseline.groups[0].rationale.text, ' ')])).toThrow()
    expect(() => editDraft(d, [change('/principal/subject', principal.subject, 'other')])).toThrow('not editable')
  })
})
describe('workspace entry', () => {
  it('renders pure general classroom chat without required selectors or a lesson canvas', () => {
    const html = renderToStaticMarkup(<Workspace />)
    expect(html).not.toContain('<select')
    expect(html).not.toContain('lesson-canvas')
    expect(html).toContain('Classroom conversation')
    expect(html).not.toContain('Start with a question')
    expect(html).not.toContain('Who has insufficient evidence?')
    expect(html).not.toContain('What did the team discuss?')
    expect(html).toContain('Message Instruct IQ')
    expect(html).not.toContain('renewal')
    expect(html).not.toContain('plan-demo')
    expect(html).toContain('Work and Web are not assumed available')
  })
  describe('conversation proposal safety', () => {
    it('sends only the bounded message and scoped artifact, checks class/principal and propagates expiry', async () => {
      const d = await newDraft(connected('complete').result)
      const response = { schemaVersion: 'instruct.conversation.v1', requestId: 'r1', principal, classId: request.classId, assessmentId: request.assessmentId, mode: 'bounded_commands', intent: 'explain', message: 'Authorized baseline.', evidenceRefs: [], followups: [], plan: null, proposal: null }
      const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(response)))
      vi.stubGlobal('fetch', fetch)
      expect((await converse(request, 'Explain grouping', d, principal, 'token', new AbortController().signal)).intent).toBe('explain')
      const body = JSON.parse(fetch.mock.calls[0][1].body)
      expect(body.artifact).toEqual({ planId: d.scope.planId, baselineSha256: d.baselineSha256, edits: [] })
      expect(body.artifact.baseline).toBeUndefined()
      expect(body.history).toBeUndefined()
      fetch.mockResolvedValueOnce(new Response(JSON.stringify({ ...response, classId: 'other-class' })))
      await expect(converse(request, 'Explain grouping', d, principal, 'token', new AbortController().signal)).rejects.toThrow('scope')
      fetch.mockResolvedValueOnce(new Response(JSON.stringify({ ...response, principal: { ...principal, subject: 'other' } })))
      await expect(converse(request, 'Explain grouping', d, principal, 'token', new AbortController().signal)).rejects.toThrow('scope')
      fetch.mockResolvedValueOnce(new Response(JSON.stringify({ schemaVersion: 'instruct.error.v1', requestId: 'expired', error: { code: 'not_found', message: 'Resource not found.' } }), { status: 404 }))
      await expect(converse(request, 'Explain grouping', d, principal, 'token', new AbortController().signal)).rejects.toThrow('Resource not found')
    })
    it('applies, resets review, invalidates citations and undoes as a fresh edit', async () => {
      const d = await newDraft(fixture<Final>('complete').result)
      d.state = 'reviewed'
      d.review = { reviewer: principal, reviewedAt: new Date().toISOString(), editRevision: 0, meaning: 'teacher_review_only_not_published' }
      const segments = d.baseline.package!.segments
      const changes = [change('/package/segments/0/minutes', segments[0].minutes, segments[0].minutes - 2), change('/package/segments/2/minutes', segments[2].minutes, segments[2].minutes + 2)]
      const proposal = { planId: d.scope.planId, baselineSha256: d.baselineSha256, editRevision: 0, changes }
      const next = applyProposal(d, proposal, canonical(d))
      expect(next.review).toBeNull()
      expect(next.state).toBe('edited')
      expect(invalidatedClaims(next).size).toBe(2)
      expect(replay(next).package!.segments.reduce((sum, s) => sum + s.minutes, 0)).toBe(35)
      const undone = editDraft(next, inverseChanges(changes))
      expect(replay(undone)).toEqual(replay(d))
      expect(undone.review).toBeNull()
      expect(undone.edits).toHaveLength(2)
    })
    it('rejects stale proposals after edits, review or scope changes', async () => {
      const d = await newDraft(fixture<Final>('complete').result), snapshot = canonical(d)
      const proposal = { planId: d.scope.planId, baselineSha256: d.baselineSha256, editRevision: 0, changes: [change('/package/segments/1/instruction/text', d.baseline.package!.segments[1].instruction.text, 'More graph scaffolds')] }
      const edited = editDraft(d, [change('/groups/0/scaffold/text', d.baseline.groups[0].scaffold.text, 'Teacher edit preserved')])
      expect(() => applyProposal(edited, proposal, snapshot)).toThrow('canvas changed')
      expect(() => applyProposal({ ...d, state: 'reviewed' }, proposal, snapshot)).toThrow('canvas changed')
      expect(() => applyProposal(d, { ...proposal, planId: 'another-plan' }, snapshot)).toThrow()
      expect(() => applyProposal(d, { ...proposal, changes: [change('/package/objective/text', d.baseline.package!.objective.text, 'forged objective')] }, snapshot)).toThrow('Unsupported')
      expect(replay(edited).groups[0].scaffold.text).toBe('Teacher edit preserved')
    })
  })
})
