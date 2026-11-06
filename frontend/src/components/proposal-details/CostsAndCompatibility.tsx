import type { Proposal, ProposalCosts } from '../../types/proposal'
import { CompatibilitySection } from './CompatibilitySection'
import { CostsSection } from './CostsSection'

/** Developer 3: US-13 costs and budget, US-15 match and trade-offs, US-14 sources. */
export function CostsAndCompatibility({ proposal, costs, stale = false }: { proposal: Proposal; costs?: ProposalCosts; stale?: boolean }) {
  return <>
    <CostsSection costs={costs} />
    {!stale && <CompatibilitySection proposal={proposal} />}
  </>
}
