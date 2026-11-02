import type { Proposal, ProposalCosts } from '../../types/proposal'
import { CompatibilitySection } from './CompatibilitySection'
import { CostsSection } from './CostsSection'
import { SourcesSection } from './SourcesSection'

/** Developer 3: US-13 costs and budget, US-15 match and trade-offs, US-14 sources. */
export function CostsAndCompatibility({ proposal, costs, generatedAt = null }: { proposal: Proposal; costs?: ProposalCosts; generatedAt?: string | null }) {
  return <>
    <CostsSection costs={costs} />
    <CompatibilitySection proposal={proposal} />
    <SourcesSection proposal={proposal} generatedAt={generatedAt} />
  </>
}
