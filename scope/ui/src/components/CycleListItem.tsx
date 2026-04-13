import type { Cycle } from '../api/types'

interface Props {
  cycle: Cycle
  selected: boolean
  onClick: () => void
}

function scoreClass(score: number): string {
  if (score >= 80) return 'high'
  if (score >= 50) return 'mid'
  return 'low'
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
  } catch {
    return ts.slice(11, 16)
  }
}

export default function CycleListItem({ cycle, selected, onClick }: Props) {
  return (
    <li className={`cycle-item ${selected ? 'selected' : ''}`} onClick={onClick}>
      <span className={`score-dot ${scoreClass(cycle.focus_score)}`} />
      <div className="cycle-item-info">
        <div className="cycle-item-time">{formatTime(cycle.timestamp)}</div>
        <div className="cycle-item-task">{cycle.task || '(unclear)'}</div>
      </div>
    </li>
  )
}
