import { useEffect, useRef, useState } from 'react'
import { ArrowUp, BookOpen, MessageSquare, Plus } from 'lucide-react'
import { useAuthentication } from '../authentication'
import { getClasses } from './client'
import { streamChat, type Chat } from './chat'
import { ActivityPanel, type Activity, type RequestState } from './ActivityPanel'
import { ChatMessage } from './ChatMessage'
import { samePrincipal, type Classes } from './types'
import './workspace.css'

type Turn = { role: 'user' | 'assistant'; text: string; response?: Chat }
const errorText = (e: unknown) => e instanceof Error ? e.message : 'Request failed.'

export default function Workspace() {
  const auth = useAuthentication()
  // Preserve first-login callers; only an established identity switch/logout resets this key.
  return <TeacherWorkspace key={auth.identityKey ?? 'unconfigured'} />
}

function TeacherWorkspace() {
  const { getAccessToken, signOut } = useAuthentication()
  const [catalog, setCatalog] = useState<Classes | null>(null)
  const [turns, setTurns] = useState<Turn[]>([])
  const [input, setInput] = useState(''), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [activity, setActivity] = useState<Activity>({})
  const [requestState, setRequestState] = useState<RequestState>('idle')
  const [phase, setPhase] = useState(''), [elapsed, setElapsed] = useState(0)
  const startedAt = useRef(0)
  const session = useRef<string | null>(null), scope = useRef<string | null>(null)
  const operation = useRef(0), controller = useRef<AbortController | null>(null)
  const activeSteps = Object.values(activity).filter(step => step.state === 'running')
  const activityPhase = activeSteps.length > 1 ? `${activeSteps.length} IQ sources retrieving in parallel`
    : activeSteps[0]?.message ?? phase
  useEffect(() => () => { operation.current++; controller.current?.abort() }, [])
  useEffect(() => {
    if (!busy) return
    const timer = window.setInterval(() => setElapsed(Date.now() - startedAt.current), 100)
    return () => window.clearInterval(timer)
  }, [busy])
  function clear(cancelled = false) {
    operation.current++; controller.current?.abort()
    session.current = null; scope.current = null
    setTurns([]); setInput(''); setError(''); setNotice(''); setBusy(false)
    setRequestState(cancelled ? 'cancelled' : 'idle')
    if (cancelled) setElapsed(Date.now() - startedAt.current)
    else { setActivity({}); setElapsed(0) }
  }
  function start(phase: string) {
    startedAt.current = Date.now()
    setElapsed(0); setActivity({}); setRequestState('running'); setPhase(phase); setBusy(true)
  }
  function finish(state: RequestState) {
    setElapsed(Date.now() - startedAt.current)
    setRequestState(state); setBusy(false)
  }
  async function connect() {
    clear(); setCatalog(null); start('Signing in')
    const id = operation.current, abort = new AbortController()
    controller.current = abort
    setNotice('Signing in and loading authorized classes…')
    try {
      const token = await getAccessToken()
      if (id !== operation.current) return
      setPhase('Loading authorized classes')
      const data = await getClasses(token, abort.signal)
      if (id !== operation.current) return
      setCatalog(data)
      setNotice(data.classes.length ? 'Connected. Ask naturally; I will clarify the class when needed.' : 'No authorized classes. Ask your operator to check instructional class grants.')
      finish('idle')
    } catch (e) { if (id === operation.current) { setNotice(''); setError(errorText(e)); finish('failed') } }
  }
  async function send(text: string) {
    if (busy || !text.trim() || !catalog) return
    controller.current?.abort()
    const id = ++operation.current, abort = new AbortController()
    controller.current = abort
    start('Checking sign-in'); setError(''); setNotice(''); setInput('')
    setTurns(old => [...old, { role: 'user', text }])
    try {
      const token = await getAccessToken()
      if (id !== operation.current) return
      setPhase('Checking classroom access')
      const current = await getClasses(token, abort.signal)
      if (id !== operation.current) return
      if (!samePrincipal(current.principal, catalog.principal)) {
        clear(); setCatalog(null); setError('Identity changed. Sign in again.'); return
      }
      setPhase('Waiting for backend')
      const data = await streamChat(text, session.current, current, token, progress => {
        if (id !== operation.current) return
        setActivity(old => ({ ...old, [progress.stage]: progress }))
        setPhase(progress.state === 'running' ? progress.message : 'Waiting for next step')
      }, abort.signal)
      if (id !== operation.current) return
      session.current = data.sessionId
      if (scope.current && scope.current !== data.classId) setTurns([{ role: 'user', text }])
      scope.current = data.classId
      setTurns(old => [...old, { role: 'assistant', text: data.message, response: data }])
      finish('succeeded')
    } catch (e) {
      if (id === operation.current) {
        setError(`${errorText(e)} Start a new conversation if its session expired. No cached or simulated answer.`)
        finish('failed')
      }
    }
  }
  return <main className="workspace chat-workspace">
    <a className="skip-link" href="#classroom-message">Skip to message</a>
    <header className="site-header">
      <a className="brand" href="#workspace-title"><BookOpen size={22} aria-hidden="true" /><span>Instruct IQ</span><span className="brand-divider" />Classroom workspace</a>
      <div className="actions"><button disabled={busy} onClick={() => void connect()}>{catalog ? 'Refresh access' : 'Sign in'}</button>
        {catalog && <button onClick={() => { clear(); setCatalog(null); if (signOut) void signOut().catch(e => setError(errorText(e))) }}>Sign out</button>}</div>
    </header>
    <div className="workspace-content">
    <nav className="breadcrumb" aria-label="Breadcrumb">Instruct IQ <span aria-hidden="true">/</span> Classroom conversation</nav>
    <div className="page-intro"><p className="eyebrow">TEACHER WORKSPACE</p><h1 id="workspace-title">Your classroom, in conversation</h1><p>Ask a question. Explore the evidence. Decide what comes next.</p></div>
    {notice && <p className="notice" role="status" aria-live="polite">{notice}</p>}
    <div className="workspace-layout"><div className="conversation-column">
    {catalog && <details className="class-context"><summary>Authorized classroom context <span className="context-count">{catalog.classes.length}</span></summary>{catalog.classes.map(c => <p key={c.classId}>{c.title}</p>)}</details>}
    <section className="panel" aria-label="Classroom conversation">
      <div className="conversation-heading"><h2><MessageSquare size={18} aria-hidden="true" /> Conversation</h2><button type="button" onClick={() => clear()}><Plus size={16} aria-hidden="true" />New conversation</button></div>
      <div className="transcript" role="log" aria-label="Conversation history" aria-live="polite" aria-relevant="additions">
        {turns.map((turn, i) => <article className={`turn turn-${turn.role}`} key={i}><strong>{turn.role === 'user' ? 'You' : 'Instruct IQ · GPT-5.6'}</strong>
          {turn.role === 'assistant' && <p><small>Model interpretation, suggestion or clarification — not a student record.</small></p>}
          {turn.role === 'assistant' ? <ChatMessage message={turn.text} citations={turn.response?.citations ?? []} /> : <p>{turn.text}</p>}
          {!!turn.response?.observations.length && <details className="message-observations"><summary>Retrieved observations and approved records ({turn.response.observations.length})</summary><section aria-label="Verified observations">
            {turn.response.observations.map(f => <details key={f.factId}><summary>{f.kind} · {f.factId}</summary>
              <dl>{Object.entries(f).filter(([key]) => !['evidenceRefs', 'factId'].includes(key)).map(([key, value]) =>
                <div key={key}><dt>{key}</dt><dd>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</dd></div>)}</dl>
              <small>Sources: {f.evidenceRefs.join(', ')}</small></details>)}
            {!!turn.response.observationCitations?.length && <section aria-label="Observation provenance"><h3>Supporting record evidence</h3>
              {turn.response.observationCitations.map(c => <details key={c.refId}><summary>{c.title}</summary>
                <p><small>Reference: {c.refId}</small></p><p>{c.locator}</p><blockquote>{c.excerpt}</blockquote></details>)}
            </section>}
          </section></details>}
        </article>)}
      </div>
      {error && <div role="alert" className="error">{error}</div>}
      {busy && <p className="buffer-notice">Working on your request. Follow backend activity for live progress; the answer appears after reference validation.</p>}
      <form className="composer" onSubmit={e => { e.preventDefault(); void send(input) }}>
        <label htmlFor="classroom-message">Message Instruct IQ</label>
        <textarea id="classroom-message" value={input} maxLength={2000} required disabled={busy || !catalog} onChange={e => setInput(e.target.value)} placeholder="Ask about your classroom…" />
        <div className="composer-footer"><small>Grounded in your authorized classroom evidence.</small><div className="actions">
          {busy && <button type="button" onClick={() => { clear(true); setNotice('Cancelled. Conversation cleared; no answer was accepted.') }}>Cancel request</button>}
          <button className="primary" disabled={busy || !catalog || !input.trim()}>Send<ArrowUp size={16} aria-hidden="true" /></button></div></div>
      </form>
    </section>
    <p className="privacy-note">Only your authorized classroom records. Observations are separate from model interpretations. Work and Web are not assumed available. Nothing is published. Conversations expire after 15 minutes or server restart.</p>
    </div><ActivityPanel activity={activity} state={requestState} phase={activityPhase} elapsed={elapsed} connected={catalog !== null} /></div>
    </div>
  </main>
}
