import { canonical, editDraft } from './draft'
import type { Change, Draft, Proposal } from './types'

export const supportedPrompts = ['Plan my next lesson', 'What needs reteaching', 'Help me differentiate']
export function applyProposal(draft: Draft, proposal: Proposal, snapshot: string): Draft {
  if (canonical(draft) !== snapshot || draft.scope.planId !== proposal.planId || draft.baselineSha256 !== proposal.baselineSha256 || draft.edits.length !== proposal.editRevision) throw Error('The canvas changed. Request a fresh proposal; no edits were overwritten.')
  // Conversational revisions may change timing or append modelling scaffolds only.
  if (!proposal.changes.length || proposal.changes.some(c => !/^\/package\/segments\/\d+\/(minutes|instruction\/text)$/.test(c.path))) throw Error('Unsupported proposal fields.')
  return editDraft(draft, proposal.changes)
}
export function inverseChanges(changes: Change[]): Change[] {
  return changes.map(c => ({ ...c, before: c.after, after: c.before }))
}
