// @vitest-environment jsdom
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AuthenticationContext } from '../authentication'
import Workspace from './Workspace'
import type { ChatProgress } from './chat'

let root: Root, container: HTMLDivElement
const principal = { tenantId: 'tenant-test', subject: 'teacher-test' }
const catalog = {
  schemaVersion: 'instruct.classes.v1', principal,
  classes: [{ classId: 'science-test', title: 'Authorized science', studentCount: 24, assessmentIds: ['assessment-test'] }],
}
let controller: ReadableStreamDefaultController<Uint8Array>, sequence: number
let signal: AbortSignal
function emit(type: string, payload?: unknown) {
  controller.enqueue(new TextEncoder().encode(`event: ${type}\ndata: ${JSON.stringify({
    schemaVersion: 'instruct.chat.event.v1', requestId: 'request-test', sequence: sequence++, type, payload,
  })}\n\n`))
}
async function step(stage: ChatProgress['stage'], state: ChatProgress['state'], message: string, count: number | null = null) {
  await act(async () => emit('progress', {
    stage, state, message, durationMs: state === 'running' ? null : 1200, evidenceCount: count,
  }))
}
function button(text: string) {
  return [...container.querySelectorAll('button')].find(b => b.textContent === text)!
}
beforeEach(async () => {
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  sequence = 0
  container = document.createElement('div'); document.body.append(container)
  root = createRoot(container)
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
    if (!url.endsWith('/chat')) return new Response(JSON.stringify(catalog))
    signal = init.signal!
    return new Response(new ReadableStream<Uint8Array>({ start(c) { controller = c } }),
      { headers: { 'Content-Type': 'text/event-stream' } })
  }))
  await act(async () => root.render(
    <AuthenticationContext.Provider value={{ getAccessToken: async () => 'test-token' }}><Workspace /></AuthenticationContext.Provider>,
  ))
  await act(async () => button('Sign in').click())
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove(); vi.unstubAllGlobals()
})
async function ask() {
  await act(async () => {
    const input = container.querySelector('#classroom-message') as HTMLTextAreaElement
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, 'Who has insufficient evidence?')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => button('Send').click())
  await act(async () => emit('started'))
}
const panel = () => container.querySelector('.activity-panel')!

it('keeps actual IQ progress visible before the buffered answer and retains terminal details', async () => {
  await ask()
  await step('model', 'running', 'Choosing tools.')
  expect(panel().textContent).toContain('In progress')
  expect(container.querySelector('.turn-assistant')).toBeNull()
  await step('model', 'succeeded', 'Tool selected.')
  await step('fabric', 'running', 'Reading assessment evidence.')
  expect(panel().textContent).toContain('Reading assessment evidence.')
  await step('fabric', 'succeeded', 'Assessment evidence checked.', 3)
  expect(panel().textContent).toContain('1.2 s · 3 sources')
  await step('work', 'running', 'Checking team context.')
  await step('work', 'unavailable', 'Work IQ requires operator setup.', 0)
  expect(panel().textContent).toContain('Unavailable')
  expect(panel().textContent).toContain('Work IQ requires operator setup.')
  expect(panel().textContent).toContain('Not requested')
  expect(panel().textContent).toContain('Not enabled')
  await step('validation', 'running', 'Checking references.')
  await step('validation', 'succeeded', 'Answer references verified.', 3)
  await act(async () => {
    emit('final', {
      schemaVersion: 'instruct.chat.v2', sessionId: 'session-test', principal, classId: 'science-test',
      model: 'gpt-5.6-luna', message: '## Recommendation\n\nConsider a short check-in.',
      observations: [{ factId: 'fact-test', kind: 'assessment', evidenceRefs: ['record-ref'] }],
      citations: [],
      observationCitations: [{ refId: 'record-ref', source: 'fabric', title: 'Assessment record evidence', locator: 'Verified record', excerpt: 'Synthetic response evidence.' }],
    })
    controller.close()
  })
  expect(container.querySelector('.turn-assistant')?.textContent).toContain('Consider a short check-in.')
  expect(container.querySelector('.turn-assistant .chat-answer h3')?.textContent).toBe('Recommendation')
  expect(container.querySelector('.turn-user .chat-answer')).toBeNull()
  expect(container.querySelector('[aria-label="Message sources"]')).toBeNull()
  const records = container.querySelector<HTMLDetailsElement>('.message-observations')!
  expect(records.open).toBe(false)
  expect(records.querySelector('[aria-label="Observation provenance"]')?.textContent).toContain('Assessment record evidence')
  expect(panel().textContent).toContain('Answer ready')
  expect(panel().textContent).toContain('Assessment evidence checked.')
  expect(button('Refresh access').disabled).toBe(false)
})

it('shows simultaneous source activity and keeps the remaining source active after a sibling finishes', async () => {
  await ask()
  await step('fabric', 'running', 'Reading assessment evidence.')
  await step('foundry', 'running', 'Reading approved resources.')
  await step('work', 'running', 'Reading team context.')
  expect(panel().textContent).toContain('3 IQ sources retrieving in parallel')
  expect(panel().querySelectorAll('.activity-step.state-running')).toHaveLength(3)
  await step('foundry', 'succeeded', 'Resources checked.', 2)
  expect(panel().textContent).toContain('2 IQ sources retrieving in parallel')
  await step('fabric', 'succeeded', 'Assessment checked.', 3)
  expect(panel().querySelector('.request-status')?.textContent).toContain('Reading team context.')
  expect(panel().querySelectorAll('.activity-step.state-running')).toHaveLength(1)
  await act(async () => {
    button('Cancel request').click()
    controller.close()
  })
})

it('starts with an empty conversation and no introductory section or sample questions', () => {
  expect(container.querySelector('.welcome')).toBeNull()
  expect(container.querySelector('.transcript')?.textContent).toBe('')
  expect(container.textContent).not.toContain('Start with a question')
  expect(container.textContent).not.toContain('Who has insufficient evidence?')
  expect(container.textContent).not.toContain('What did the team discuss?')
  expect(container.querySelector('#classroom-message')).not.toBeNull()
})

it('shows terminal errors without manufacturing successful provider results', async () => {
  await ask()
  await step('model', 'running', 'Waiting for the model.')
  await step('model', 'failed', 'Model request failed.')
  await act(async () => {
    emit('error', { message: 'Model is rate limited.', status: 503 })
    controller.close()
  })
  expect(panel().textContent).toContain('Request failed')
  expect(container.querySelector('[role=alert]')?.textContent).toContain('Model is rate limited.')
  expect(container.querySelector('.turn-assistant')).toBeNull()
  expect(button('Refresh access').disabled).toBe(false)
})

it('cancels active calls, marks them cancelled, and ignores late status and answers', async () => {
  await ask()
  await step('fabric', 'running', 'Retrieving assessment evidence.')
  await act(async () => button('Cancel request').click())
  expect(signal.aborted).toBe(true)
  expect(panel().textContent).toContain('Request cancelled')
  expect(panel().textContent).toContain('Stopped before this step finished.')
  await act(async () => {
    emit('progress', { stage: 'fabric', state: 'succeeded', message: 'Late result.', durationMs: 100, evidenceCount: 2 })
    controller.close()
  })
  expect(panel().textContent).not.toContain('Late result.')
  expect(container.querySelector('.turn-assistant')).toBeNull()
  await act(async () => button('New conversation').click())
  expect(panel().textContent).toContain('No request running')
  expect(panel().textContent).not.toContain('Stopped before this step finished.')
})
