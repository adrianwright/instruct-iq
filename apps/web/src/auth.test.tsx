// @vitest-environment jsdom
import { act, type ReactNode } from 'react'
import { readFileSync } from 'node:fs'
import { createRoot, type Root } from 'react-dom/client'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { EventType, type AccountInfo, type EventMessage } from '@azure/msal-browser'
import { AuthenticationProvider } from './auth'
import Workspace from './instruct/Workspace'
import type { Final } from './instruct/types'

const sdk = vi.hoisted(() => {
  vi.stubEnv('VITE_ENTRA_TENANT_ID', 'tenant')
  vi.stubEnv('VITE_ENTRA_CLIENT_ID', 'client')
  vi.stubEnv('VITE_API_SCOPE', 'api://test/access')
  return ({
  active: null as AccountInfo | null,
  accounts: [] as AccountInfo[],
  callbacks: new Set<(event: EventMessage) => void>(),
  loginPopup: vi.fn(), acquireTokenSilent: vi.fn(),
  })
})
vi.mock('@azure/msal-browser', async importOriginal => ({
  ...await importOriginal<typeof import('@azure/msal-browser')>(),
  PublicClientApplication: class {
    initialize = async () => {}
    getActiveAccount = () => sdk.active
    getAllAccounts = () => sdk.accounts
    loginPopup = sdk.loginPopup
    acquireTokenSilent = sdk.acquireTokenSilent
    setActiveAccount = (account: AccountInfo) => {
      sdk.active = account
      emit(EventType.ACTIVE_ACCOUNT_CHANGED)
    }
    addEventCallback = (callback: (event: EventMessage) => void) => { sdk.callbacks.add(callback); return callback }
    removeEventCallback = (callback: (event: EventMessage) => void) => { sdk.callbacks.delete(callback) }
  },
}))
vi.mock('@azure/msal-react', () => ({
  MsalProvider: ({ children }: { children: ReactNode }) => children,
  useMsal: () => ({ instance, accounts: sdk.accounts }),
}))
import { PublicClientApplication } from '@azure/msal-browser'
const instance = new PublicClientApplication({ auth: { clientId: 'test' } })
function emit(eventType: EventMessage['eventType'], account?: AccountInfo) {
  for (const callback of sdk.callbacks) callback({ eventType, payload: account ? { account } : null } as EventMessage)
}
const teacher = { homeAccountId: 'teacher.tenant', tenantId: 'tenant', localAccountId: 'teacher' } as AccountInfo
let root: Root, container: HTMLDivElement
beforeEach(() => {
  vi.stubEnv('VITE_ENTRA_TENANT_ID', 'tenant')
  vi.stubEnv('VITE_ENTRA_CLIENT_ID', 'client')
  vi.stubEnv('VITE_API_SCOPE', 'api://test/access')
  vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true)
  sdk.active = null; sdk.accounts = []; sdk.callbacks.clear()
  sdk.loginPopup.mockReset(); sdk.acquireTokenSilent.mockReset()
  container = document.createElement('div'); document.body.append(container)
  root = createRoot(container)
})
afterEach(async () => {
  await act(async () => root.unmount())
  container.remove(); vi.unstubAllEnvs(); vi.unstubAllGlobals()
})
async function mount() {
  await act(async () => root.render(<AuthenticationProvider><Workspace /></AuthenticationProvider>))
}
async function clickConnect() {
  await act(async () => (container.querySelector('header button') as HTMLButtonElement).click())
}
it('completes first interactive sign-in and authorized class load without cancelling its caller', async () => {
  sdk.loginPopup.mockImplementation(async () => {
    sdk.accounts = [teacher]
    emit(EventType.LOGIN_SUCCESS, teacher)
    await Promise.resolve()
    return { account: teacher, accessToken: 'synthetic-test-only' }
  })
  const plan = JSON.parse(readFileSync('..\\..\\docs\\contracts\\examples\\complete.json', 'utf8')) as Final
  const principal = { tenantId: 'tenant', subject: 'teacher' }
  plan.result.principal = principal; plan.result.executionMode = 'connected'
  const fetch = vi.fn().mockImplementation(async (url: string) => {
    if (url.endsWith('/chat')) {
      const final = {
    schemaVersion: 'instruct.chat.v2', sessionId: 'test-session', principal,
    classId: plan.result.classId, model: 'gpt-5.6-luna',
    message: 'Private authorized classroom history', observations: [], citations: [],
      }
      const events = [
        { type: 'started' },
        { type: 'progress', payload: { stage: 'validation', state: 'running', message: 'Checking references.', durationMs: null, evidenceCount: null } },
        { type: 'progress', payload: { stage: 'validation', state: 'succeeded', message: 'References verified.', durationMs: 10, evidenceCount: 0 } },
        { type: 'final', payload: final },
      ]
      return new Response(events.map((event, sequence) => `event: ${event.type}\ndata: ${JSON.stringify({
        ...event, schemaVersion: 'instruct.chat.event.v1', requestId: 'test-request', sequence,
      })}\n\n`).join(''), { headers: { 'Content-Type': 'text/event-stream' } })
    }
    return new Response(JSON.stringify({
    schemaVersion: 'instruct.classes.v1', principal: { tenantId: 'tenant', subject: 'teacher' },
    classes: [{ classId: plan.result.classId, title: 'Authorized class', studentCount: 24, assessmentIds: [plan.result.assessmentId] }],
    }))
  })
  vi.stubGlobal('fetch', fetch)
  await mount(); await clickConnect(); await mount()
  expect(sdk.loginPopup).toHaveBeenCalledOnce()
  expect(fetch).toHaveBeenCalledOnce()
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(false)
  expect(container.textContent).toContain('Authorized class')
  expect(container.textContent).toContain('Connected. Ask naturally')
  await act(async () => { emit(EventType.LOGIN_SUCCESS, teacher); emit(EventType.ACTIVE_ACCOUNT_CHANGED) })
  expect(container.textContent).toContain('Authorized class')
  sdk.acquireTokenSilent.mockResolvedValue({ accessToken: 'synthetic-test-only' })
  await act(async () => {
    const input = container.querySelector('#classroom-message') as HTMLTextAreaElement
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, 'Who has insufficient evidence?')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => {
    const button = [...container.querySelectorAll('button')].find(b => b.textContent === 'Send')!
    button.click()
  })
  expect(container.textContent).toContain('Private authorized classroom history')
  const input = container.querySelector('#classroom-message') as HTMLTextAreaElement
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(input, 'Private draft command')
    input.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await act(async () => {
    sdk.active = { ...teacher, homeAccountId: 'other.tenant', localAccountId: 'other' }
    sdk.accounts = [teacher, sdk.active]
    emit(EventType.ACTIVE_ACCOUNT_CHANGED)
  })
  expect(container.textContent).not.toContain('Authorized class')
  expect((container.querySelector('#classroom-message') as HTMLTextAreaElement).value).toBe('')
  expect(container.querySelector('.transcript')?.textContent).toBe('')
  expect(container.textContent).not.toContain('Private authorized classroom history')
  expect(container.textContent).not.toContain('Generated baseline: complete')
  expect(fetch.mock.calls[0][1].signal.aborted).toBe(true)
})
it('invalidates a pending sign-in on sign-out and never loads its late classes', async () => {
  let finish!: (value: unknown) => void
  sdk.loginPopup.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  await mount(); await clickConnect()
  expect(container.textContent).toContain('Signing in and loading authorized classes')
  await act(async () => emit(EventType.LOGOUT_START))
  await act(async () => {
    finish({ account: teacher, accessToken: 'synthetic-test-only' })
  })
  expect(fetch).not.toHaveBeenCalled()
  expect((container.querySelector('header button') as HTMLButtonElement).disabled).toBe(false)
})
it('surfaces consent failure codes without exposing the raw token or error payload', async () => {
  sdk.loginPopup.mockRejectedValue({ errorCode: 'consent_required', errorMessage: 'AADSTS65001 private payload', correlationId: '12345678-1234-1234-1234-123456789abc' })
  await mount(); await clickConnect()
  expect(container.querySelector('[role=alert]')?.textContent).toContain('consent_required; AADSTS65001')
  expect(container.textContent).not.toContain('private payload')
  expect((container.querySelector('header button') as HTMLButtonElement).disabled).toBe(false)
})
