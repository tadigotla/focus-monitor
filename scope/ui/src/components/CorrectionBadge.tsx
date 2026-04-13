import type { Correction } from '../api/types'

interface Props {
  corrections: Correction[]
}

export default function CorrectionBadge({ corrections }: Props) {
  if (corrections.length === 0) {
    return <span style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>No corrections</span>
  }

  // Show the most recent correction
  const c = corrections[0]

  if (c.user_verdict === 'confirmed') {
    return <span className="correction-badge confirmed">Confirmed</span>
  }

  return (
    <span className="correction-badge corrected">
      Corrected {c.user_task ? `\u2192 ${c.user_task}` : ''} ({c.user_kind.replace(/_/g, ' ')})
    </span>
  )
}
