import { samePrincipal, type Change, type Draft, type Plan, type Principal } from './types'

export function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`
  if (value !== null && typeof value === 'object') return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical((value as Record<string, unknown>)[k])}`).join(',')}}`
  return JSON.stringify(value)
}
export async function digest(value: unknown) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical(value))))).map(b => b.toString(16).padStart(2, '0')).join('')
}
export const draftKey = (p: Principal, classId: string, planId: string) => JSON.stringify(['instruct.draft.v1', p.tenantId, p.subject, classId, planId])
export function normalizePlan(plan: Plan): Plan {
  const normalized = structuredClone(plan)
  // Python model_dump includes the sole defaulted fact field in canonical hashes.
  for (const source of normalized.sources) for (const fact of source.facts) {
    if (fact.effectiveTo === undefined) fact.effectiveTo = null
  }
  return normalized
}
export async function newDraft(plan: Plan): Promise<Draft> {
  plan = normalizePlan(plan)
  return { schemaVersion: 'instruct.draft.v1', scope: { principal: plan.principal, classId: plan.classId, planId: plan.planId, schemaVersion: 'instruct.draft.v1' }, state: 'generated', baseline: structuredClone(plan), baselineSha256: await digest(plan), edits: [], review: null }
}
const editable = /^\/(groups\/(0|[1-9][0-9]*)\/(rationale\/text|scaffold\/text|studentIds)|package\/(objective\/text|segments\/(0|[1-9][0-9]*)\/(minutes|instruction\/text)|exitTicket\/(prompt|answerKey)\/text))$/
function target(document: Plan, path: string): { parent: Record<string, unknown>; key: string } {
  if (!editable.test(path)) throw Error('Field is not editable.')
  const parts = path.slice(1).split('/')
  let node: unknown = document
  for (const part of parts.slice(0, -1)) node = (node as Record<string, unknown>)[part]
  if (!node || typeof node !== 'object') throw Error('Edit path does not resolve.')
  return { parent: node as Record<string, unknown>, key: parts.at(-1)! }
}
export function replay(draft: Draft): Plan {
  const document = structuredClone(draft.baseline)
  for (const [index, revision] of draft.edits.entries()) {
    if (revision.revision !== index + 1 || !samePrincipal(revision.editor, draft.scope.principal) || !revision.changes.length || !Number.isFinite(Date.parse(revision.editedAt))) throw Error('Invalid edit revision.')
    const invalidated = new Set<string>(), paths = revision.changes.map(c => c.path)
    if (new Set(paths).size !== paths.length) throw Error('Duplicate edit paths.')
    for (const change of revision.changes) {
      const { parent, key } = target(document, change.path)
      const old = parent[key]
      if (change.provenance !== 'teacher_edit_unverified' || canonical(old) !== canonical(change.before) || canonical(old) === canonical(change.after) || typeof old !== typeof change.after || Array.isArray(old) !== Array.isArray(change.after)) throw Error('Invalid edit before/after value.')
      if (key === 'text') {
        if (typeof change.after !== 'string' || !change.after.trim() || change.after.length > 12000) throw Error('Text must contain 1–12000 characters.')
        invalidated.add(parent.claimId as string)
      } else if (key === 'minutes') {
        if (!Number.isInteger(change.after) || Number(change.after) < 1 || Number(change.after) > 35) throw Error('Minutes must be 1–35.')
        invalidated.add((parent.instruction as { claimId: string }).claimId)
      } else {
        if (!Array.isArray(change.after) || !change.after.length || change.after.some(s => typeof s !== 'string')) throw Error('Group must not be empty.')
        if (!paths.includes(change.path.replace(/studentIds$/, 'rationale/text'))) throw Error('Membership changes require a changed rationale in the same revision.')
        invalidated.add((parent.rationale as { claimId: string }).claimId)
      }
      parent[key] = structuredClone(change.after)
    }
    if (canonical([...invalidated].sort()) !== canonical([...revision.invalidatedClaimIds].sort()) || invalidated.size !== revision.invalidatedClaimIds.length) throw Error('Invalid claim invalidation.')
    const assigned = document.groups.flatMap(g => g.studentIds)
    if (document.groups.some(g => !g.studentIds.length) || canonical([...assigned].sort()) !== canonical(draft.baseline.groups.flatMap(g => g.studentIds).sort()) || new Set(assigned).size !== assigned.length) throw Error('Group edits must preserve the complete roster partition.')
    if (document.package && document.package.segments.reduce((n, s) => n + s.minutes, 0) !== 35) throw Error('Lesson must remain 35 minutes including exit ticket.')
  }
  return document
}
export function editDraft(draft: Draft, changes: Change[]): Draft {
  const document = replay(draft), invalidated = new Set<string>()
  for (const c of changes) {
    const { parent, key } = target(document, c.path)
    const claimId = key === 'text' ? parent.claimId : ((key === 'minutes' ? parent.instruction : parent.rationale) as { claimId: string }).claimId
    invalidated.add(claimId as string)
  }
  const next: Draft = { ...draft, state: 'edited', review: null, edits: [...draft.edits, { revision: draft.edits.length + 1, editedAt: new Date().toISOString(), editor: draft.scope.principal, changes, invalidatedClaimIds: [...invalidated] }] }
  replay(next)
  return next
}
export async function validateDraft(draft: Draft, p: Principal, classId: string, planId: string) {
  draft = { ...draft, baseline: normalizePlan(draft.baseline) }
  const b = draft.baseline, s = draft.scope
  if (draft.schemaVersion !== 'instruct.draft.v1' || s.schemaVersion !== draft.schemaVersion || !samePrincipal(s.principal, p) || s.classId !== classId || s.planId !== planId || !samePrincipal(b.principal, p) || b.classId !== classId || b.planId !== planId || b.schemaVersion !== 'instruct.plan.v1' || await digest(b) !== draft.baselineSha256) throw Error('Draft schema, hash or scope is invalid. Reset this local draft.')
  replay(draft)
  if (draft.state === 'generated' ? draft.edits.length || draft.review : draft.state === 'edited' ? !draft.edits.length || draft.review : draft.state === 'reviewed' ? !draft.review || draft.review.editRevision !== draft.edits.length || !samePrincipal(draft.review.reviewer, p) || draft.review.meaning !== 'teacher_review_only_not_published' || !Number.isFinite(Date.parse(draft.review.reviewedAt)) : true) throw Error('Invalid draft review state.')
  return draft
}
export function saveDraft(storage: Storage, draft: Draft) {
  storage.setItem(draftKey(draft.scope.principal, draft.scope.classId, draft.scope.planId), JSON.stringify(draft))
}
export async function loadDraft(storage: Storage, p: Principal, classId: string, planId: string) {
  const value = storage.getItem(draftKey(p, classId, planId))
  if (!value) throw Error('Local draft not found.')
  return validateDraft(JSON.parse(value), p, classId, planId)
}
export function listDrafts(storage: Storage, p: Principal, classId: string) {
  const ids: string[] = []
  for (let i = 0; i < storage.length; i++) {
    try {
      const key = JSON.parse(storage.key(i)!)
      if (Array.isArray(key) && key.length === 5 && key[0] === 'instruct.draft.v1' && key[1] === p.tenantId && key[2] === p.subject && key[3] === classId) ids.push(key[4])
    } catch { /* Ignore unrelated application keys. */ }
  }
  return ids.sort()
}
export const invalidatedClaims = (d: Draft) => new Set(d.edits.flatMap(e => e.invalidatedClaimIds))
export function markdown(draft: Draft) {
  const p = replay(draft), invalid = invalidatedClaims(draft)
  const claim = (c: { claimId: string; text: string; evidenceRefs: string[] }) => `${c.text}\n\n${invalid.has(c.claimId) ? 'Teacher edit — unverified; generated citations no longer support this claim.' : `Generated references: ${c.evidenceRefs.join(', ') || 'Instructional proposal (no factual citation)'}`}`
  const requirements = p.sources.flatMap(s => s.facts).filter(f => ['support', 'resource', 'schedule'].includes(f.kind)).map(f => `- ${f.kind} ${f.factId} (${f.authority}): ${String(f.requirement ?? f.usage ?? `${f.minutes} minutes on ${f.lessonDate}`)}; effective ${f.effectiveFrom} to ${f.effectiveTo ?? 'open'}; baseline references: ${f.evidenceRefs.join(', ')}`)
  return [`# Instructional draft — baseline ${p.status}`, `Class: ${p.classId}; assessment: ${p.assessmentId}; plan: ${p.planId}`, `State: ${draft.state}. Teacher review only; not published. Browser structural checks only; no server semantic revalidation.`, '## Sources', ...p.sources.map(s => `- ${s.source}: ${s.state}${s.reason ? ` — ${s.reason}` : ''}`), '## Baseline issues (not rechecked after edits)', ...p.issues.map(i => `- ${i.message} Resolution: ${i.resolution}`), '## Learning needs (provisional)', ...p.groups.map(g => `### ${g.need}\n${g.studentIds.join(', ')}\n\n${claim(g.rationale)}\n\n${claim(g.scaffold)}\n\nBaseline overlaps (not revalidated after edits): ${JSON.stringify(g.overlappingNeeds)}`), '## Lesson', ...(p.package ? [claim(p.package.objective), ...p.package.segments.map(s => `### ${s.minutes} minutes · ${s.segmentId}\n${claim(s.instruction)}`), '## Exit ticket', claim(p.package.exitTicket.prompt), '### Answer key', claim(p.package.exitTicket.answerKey), `Required supports: ${p.package.implementedSupportFactIds.join(', ')}`, `Applied schedule: ${p.package.appliedScheduleFactId}`, `Approved resources: ${p.package.resourceFactIds.join(', ')}`] : ['No approved lesson available.']), '## Authorized baseline requirements (including schedule history)', ...requirements, '## Unresolved questions', ...p.unresolvedQuestions, '## Teacher edits (unverified)', ...draft.edits.map(e => `- Revision ${e.revision}, ${e.editedAt}: ${e.changes.map(c => c.path).join(', ')}. Invalidated generated claims: ${e.invalidatedClaimIds.join(', ')}`), '## Baseline evidence provenance (not proof of edited claims)', ...p.sources.flatMap(s => s.evidence.map(e => `- ${e.refId}: ${e.title}; ${e.locator}; native ${e.provenance.nativeId} revision ${e.provenance.nativeRevision}; ${e.provenance.contentSha256}`))].join('\n\n')
}
export function exportDraft(draft: Draft, format: 'json' | 'markdown') {
  return { schemaVersion: 'instruct.export.v1', format, exportedAt: new Date().toISOString(), draft, markdown: format === 'markdown' ? markdown(draft) : null }
}
