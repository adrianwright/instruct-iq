export type Principal = { tenantId: string; subject: string }
export type Source = 'foundry' | 'fabric' | 'work' | 'web'
export type SourceState = 'not_requested' | 'disabled' | 'unavailable' | 'failed' | 'running' | 'succeeded'
export type Claim = { claimId: string; text: string; basis: 'supported_fact' | 'instructional_proposal'; factIds: string[]; evidenceRefs: string[] }
export type Evidence = {
  refId: string; classId: string; source: Source; documentId: string; title: string
  locator: string; excerpt: string; publicUrl: string | null
  provenance: { mode: string; nativeId: string; nativeRevision: string; retrievedAt: string; contentSha256: string; adapter: string }
}
export type Fact = {
  factId: string; kind: string; authority: string; evidenceRefs: string[]
  effectiveFrom: string; effectiveTo: string | null
  [key: string]: unknown
}
export type Batch = { source: Source; requested: boolean; state: SourceState; reason: string | null; durationMs: number; evidence: Evidence[]; facts: Fact[]; classId: string; assessmentId: string; schemaVersion: string }
export type Group = { groupId: string; need: string; provisional: true; studentIds: string[]; overlappingNeeds: Record<string, string[]>; rationale: Claim; scaffold: Claim }
export type Package = {
  objective: Claim; segments: { segmentId: string; minutes: number; instruction: Claim; groupIds: string[] }[]
  exitTicket: { prompt: Claim; answerKey: Claim; skillIds: string[] }
  implementedSupportFactIds: string[]; appliedScheduleFactId: string; resourceFactIds: string[]
}
export const scenario = {
  assessmentDate: '2026-10-16', lessonDate: '2026-10-19', timezone: 'America/New_York',
  planningCutoff: '2026-10-19T07:00:00-04:00', lessonMinutes: 35, studentCount: 24,
} as const
export type PlanRequest = { schemaVersion: 'instruct.request.v1'; classId: string; assessmentId: string; scenario: typeof scenario; includeWork: boolean; includeWeb: boolean }
export type Plan = {
  schemaVersion: 'instruct.plan.v1'; planId: string; revision: 1; requestId: string
  principal: Principal; classId: string; assessmentId: string; scenario: typeof scenario
  generatedAt: string; executionMode: 'connected' | 'test_double' | 'development_example'
  status: 'complete' | 'partial' | 'blocked'; sources: Batch[]; groups: Group[]; package: Package | null
  issues: { issueId: string; code: string; affected: string; blocking: boolean; message: string; factIds: string[]; evidenceRefs: string[]; resolution: string }[]
  unresolvedQuestions: string[]
}
export type Final = { schemaVersion: 'instruct.final.v1'; requestId: string; result: Plan }
export type Classes = { schemaVersion: 'instruct.classes.v1'; requestId: string; principal: Principal; classes: { classId: string; title: string; assessmentIds: string[]; studentCount: 24 }[] }
export type Change = { path: string; before: string | number | string[]; after: string | number | string[]; provenance: 'teacher_edit_unverified' }
export type Draft = {
  schemaVersion: 'instruct.draft.v1'
  scope: { principal: Principal; classId: string; planId: string; schemaVersion: 'instruct.draft.v1' }
  state: 'generated' | 'edited' | 'reviewed'; baseline: Plan; baselineSha256: string
  edits: { revision: number; editedAt: string; editor: Principal; changes: Change[]; invalidatedClaimIds: string[] }[]
  review: { reviewer: Principal; reviewedAt: string; editRevision: number; meaning: 'teacher_review_only_not_published' } | null
}
export type Proposal = { planId: string; baselineSha256: string; editRevision: number; changes: Change[] }
export type Conversation = {
  schemaVersion: 'instruct.conversation.v1'; requestId: string; principal: Principal
  classId: string; assessmentId: string; mode: 'bounded_commands'; intent: string
  message: string; evidenceRefs: string[]; followups: string[]
  plan: Final | null; proposal: Proposal | null
}
export const sources: Source[] = ['foundry', 'fabric', 'work', 'web']
export const samePrincipal = (a: Principal, b: Principal) => a.tenantId === b.tenantId && a.subject === b.subject
