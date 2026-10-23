import { afterEach, describe, expect, it, vi } from 'vitest'
import { streamChat, type Chat, type ChatProgress } from './chat'
import type { Classes } from './types'

const principal = { tenantId: 'tenant-test', subject: 'teacher-test' }
const catalog: Classes = {
  schemaVersion: 'instruct.classes.v1', requestId: 'classes-test', principal,
  classes: [{ classId: 'class-test', title: 'Science', assessmentIds: ['assessment-test'], studentCount: 24 }],
}
const answer: Chat = {
  schemaVersion: 'instruct.chat.v2', sessionId: 'session-test', principal, classId: 'class-test',
  model: 'gpt-5.6-luna', message: 'Consider a check-in.', observations: [], citations: [],
}
const progress = (stage: ChatProgress['stage'], state: ChatProgress['state']): ChatProgress => ({
  stage, state, message: `${stage} ${state}`, durationMs: state === 'running' ? null : 200, evidenceCount: null,
})
type TestEvent = {
  type: string; schemaVersion: string; requestId: string; sequence: number
  payload?: Chat | ChatProgress | { message: string }
}
function transcript(): TestEvent[] {
  return [
    { type: 'started' },
    ...[
      progress('model', 'running'), progress('model', 'succeeded'),
      progress('fabric', 'running'), { ...progress('fabric', 'succeeded'), evidenceCount: 2 },
      progress('work', 'running'), { ...progress('work', 'unavailable'), message: 'Work IQ needs setup.' },
      progress('model', 'running'), progress('model', 'succeeded'),
      progress('validation', 'running'), progress('validation', 'succeeded'),
    ].map(payload => ({ type: 'progress', payload })),
    { type: 'final', payload: structuredClone(answer) },
  ].map((event, sequence) => ({
    ...event, schemaVersion: 'instruct.chat.event.v1', requestId: 'request-test', sequence,
  }))
}
function encode(events: ReturnType<typeof transcript>) {
  return `: heartbeat\r\n\r\n${events.map(e => `event: ${e.type}\r\ndata: ${JSON.stringify(e)}\r\n\r\n`).join('')}`
}
function response(events = transcript(), chunkSize = 17) {
  const bytes = new TextEncoder().encode(encode(events))
  return new Response(new ReadableStream({
    start(controller) {
      for (let i = 0; i < bytes.length; i += chunkSize) controller.enqueue(bytes.slice(i, i + chunkSize))
      controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
}
const run = (onProgress = vi.fn(), signal = new AbortController().signal) =>
  streamChat('Help me understand.', null, catalog, 'test-token', onProgress, signal)
afterEach(() => vi.unstubAllGlobals())

describe('live chat transport', () => {
  it('delivers real provider states, timings and counts across split frames and repeated model calls', async () => {
    const fetch = vi.fn().mockResolvedValue(response(transcript(), 1)), update = vi.fn()
    vi.stubGlobal('fetch', fetch)
    expect(await run(update)).toEqual(answer)
    expect(update).toHaveBeenCalledTimes(10)
    expect(update.mock.calls[3][0]).toMatchObject({ stage: 'fabric', evidenceCount: 2, durationMs: 200 })
    expect(update.mock.calls[5][0]).toMatchObject({ stage: 'work', state: 'unavailable', message: 'Work IQ needs setup.' })
    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][1].headers.Accept).toBe('text/event-stream')
    expect(JSON.parse(fetch.mock.calls[0][1].body).sessionId).toBeNull()
  })
  it('publishes progress before the final answer is available', async () => {
    let controller!: ReadableStreamDefaultController<Uint8Array>
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({
      start(c) { controller = c },
    }), { headers: { 'Content-Type': 'text/event-stream' } })))
    const update = vi.fn(), completed = vi.fn(), pending = run(update).then(completed)
    const events = transcript()
    controller.enqueue(new TextEncoder().encode(encode(events.slice(0, 2))))
    await vi.waitFor(() => expect(update).toHaveBeenCalledOnce())
    expect(completed).not.toHaveBeenCalled()
    controller.enqueue(new TextEncoder().encode(encode(events.slice(2))))
    controller.close()
    await pending
    expect(completed).toHaveBeenCalledWith(answer)
  })
  it('accepts overlapping sources completing out of order', async () => {
    const events = transcript()
    const payloads = [
      progress('model', 'running'), progress('model', 'succeeded'),
      progress('fabric', 'running'), progress('foundry', 'running'), progress('work', 'running'),
      progress('foundry', 'succeeded'), progress('work', 'unavailable'), progress('fabric', 'succeeded'),
      progress('model', 'running'), progress('model', 'succeeded'),
      progress('validation', 'running'), progress('validation', 'succeeded'),
    ]
    const interleaved: TestEvent[] = [events[0],
      ...payloads.map(payload => ({ ...events[0], type: 'progress', payload })), events.at(-1)!,
    ].map((event, sequence) => ({ ...event, sequence }))
    const update = vi.fn()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(interleaved, 1)))
    expect(await run(update)).toEqual(answer)
    expect(update.mock.calls.map(([p]) => `${p.stage}:${p.state}`)).toEqual(
      payloads.map(p => `${p.stage}:${p.state}`),
    )
  })
  it.each(['sequence', 'request', 'scope', 'lifecycle', 'validation', 'duplicate', 'truncated'])('rejects %s corruption without retrying', async kind => {
    const events = transcript()
    if (kind === 'sequence') events[1].sequence = 30
    if (kind === 'request') events[1].requestId = 'crossed-request'
    if (kind === 'scope') (events.at(-1)!.payload as Chat).principal.subject = 'other-teacher'
    if (kind === 'lifecycle') (events[1].payload as ChatProgress).state = 'succeeded'
    if (kind === 'validation') (events.at(-2)!.payload as ChatProgress).state = 'failed'
    if (kind === 'duplicate') events.push(events.at(-1)!)
    if (kind === 'truncated') events.pop()
    const fetch = vi.fn().mockResolvedValue(response(events))
    vi.stubGlobal('fetch', fetch)
    await expect(run()).rejects.toThrow()
    expect(fetch).toHaveBeenCalledOnce()
  })
  it('surfaces terminal server and pre-stream authorization errors', async () => {
    const events = transcript().slice(0, 1)
    events.push({ schemaVersion: 'instruct.chat.event.v1', requestId: 'request-test', sequence: 1, type: 'error',
      payload: { message: 'Model is rate limited.' } })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(events)))
    await expect(run()).rejects.toThrow('Model is rate limited.')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: { message: 'Access denied.' } }),
      { status: 403, headers: { 'Content-Type': 'application/json' } })))
    await expect(run()).rejects.toThrow('Access denied.')
  })
  it('forwards cancellation and accepts no late answer', async () => {
    const abort = new AbortController(), update = vi.fn()
    const fetch = vi.fn().mockResolvedValue(response())
    vi.stubGlobal('fetch', fetch)
    abort.abort()
    await expect(run(update, abort.signal)).rejects.toThrow('Cancelled')
    expect(update).not.toHaveBeenCalled()
    expect(fetch.mock.calls[0][1].signal).toBe(abort.signal)
    expect(fetch).toHaveBeenCalledOnce()
  })
})
