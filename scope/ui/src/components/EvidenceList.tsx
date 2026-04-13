import type { Evidence } from '../api/types'

interface Props {
  evidence: Evidence[]
}

export default function EvidenceList({ evidence }: Props) {
  if (evidence.length === 0) {
    return <div className="empty-state" style={{ height: 'auto', padding: '8px 0' }}>No evidence signals</div>
  }
  return (
    <ul className="evidence-list">
      {evidence.map((e, i) => (
        <li key={i} className="evidence-item">
          <span className={`weight-badge ${e.weight}`}>{e.weight}</span>
          <span>{e.signal}</span>
        </li>
      ))}
    </ul>
  )
}
