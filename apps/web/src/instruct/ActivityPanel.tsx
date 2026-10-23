import { Check, Circle, LoaderCircle, Minus, OctagonAlert } from 'lucide-react'
import type { ChatProgress, Stage } from './chat'

export type Activity = Partial<Record<Stage, ChatProgress>>
export type RequestState = 'idle' | 'running' | 'succeeded' | 'failed' | 'cancelled'
const labels: Record<Stage, [string, string]> = {
  model: ['GPT-5.6', 'Interprets your question and selects tools.'],
  fabric: ['Fabric IQ', 'Assessment records and skill evidence.'],
  foundry: ['Foundry IQ', 'Approved curriculum and resources.'],
  work: ['Work IQ', 'Teaching-team context, when requested.'],
  validation: ['Answer validation', 'Checks references and classroom access.'],
}
const states = {
  running: 'In progress', succeeded: 'Completed', failed: 'Failed',
  unavailable: 'Unavailable', disabled: 'Disabled',
}
const duration = (ms: number) => `${(ms / 1000).toFixed(1)} s`

export function ActivityPanel({ activity, state, elapsed, phase, connected }: {
  activity: Activity; state: RequestState; elapsed: number; phase: string; connected: boolean
}) {
  const title = {
    idle: 'No request running', running: phase, succeeded: 'Answer ready',
    failed: 'Request failed', cancelled: 'Request cancelled',
  }[state]
  return <aside className="activity-panel" aria-labelledby="activity-title">
    <div className="section-heading"><h2 id="activity-title">Backend activity</h2><span className={`connection ${connected ? 'connected' : ''}`}>{connected ? 'Signed in' : 'Not connected'}</span></div>
    <div className={`request-status state-${state}`}>
      <strong role="status" aria-live="polite">{title}</strong>
      {state !== 'idle' && <span>{duration(elapsed)} elapsed</span>}
    </div>
    <p className="activity-help">Live status from this request. IQ sources run only when selected by the model.</p>
    <ul className="activity-list">
      {(Object.keys(labels) as Stage[]).map(stage => {
        const step = activity[stage]
        const interrupted = step?.state === 'running' && state !== 'running'
        const status = interrupted ? (state === 'cancelled' ? 'Cancelled' : 'Interrupted')
          : step ? states[step.state] : stage === 'model' || stage === 'validation' ? 'Waiting' : 'Not requested'
        const Icon = interrupted || step?.state === 'failed' ? OctagonAlert
          : step?.state === 'running' ? LoaderCircle : step?.state === 'succeeded' ? Check
          : step ? Minus : Circle
        return <li key={stage} className={`activity-step state-${interrupted ? 'failed' : step?.state ?? 'idle'}`}>
          <Icon size={17} className={!interrupted && step?.state === 'running' ? 'spin' : ''} aria-hidden="true" />
          <div><div className="step-heading"><h3>{labels[stage][0]}</h3><span>{status}</span></div>
            <p>{interrupted ? 'Stopped before this step finished.' : step?.message ?? labels[stage][1]}</p>
            {step && (step.durationMs !== null || step.evidenceCount !== null) && <small>
              {step.durationMs !== null && duration(step.durationMs)}
              {step.durationMs !== null && step.evidenceCount !== null && ' · '}
              {step.evidenceCount !== null && `${step.evidenceCount} source${step.evidenceCount === 1 ? '' : 's'}`}
            </small>}
          </div>
        </li>
      })}
      <li className="activity-step"><Minus size={17} aria-hidden="true" /><div><div className="step-heading"><h3>Web IQ</h3><span>Not enabled</span></div><p>Web browsing is not available in classroom chat.</p></div></li>
    </ul>
    <p className="activity-footnote">A completed call may return no evidence. Unavailable sources are never replaced with simulated results.</p>
  </aside>
}
