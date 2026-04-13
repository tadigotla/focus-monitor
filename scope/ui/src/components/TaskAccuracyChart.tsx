import type { TaskAccuracy } from '../api/types'

interface Props {
  data: TaskAccuracy[]
}

function accuracyColor(acc: number): string {
  if (acc >= 0.9) return 'var(--color-score-high)'
  if (acc >= 0.7) return 'var(--color-score-mid)'
  return 'var(--color-score-low)'
}

export default function TaskAccuracyChart({ data }: Props) {
  if (data.length === 0) {
    return <div style={{ color: 'var(--color-text-muted)', padding: 16 }}>No task data yet</div>
  }

  const barMaxWidth = 250

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      {data.map(t => (
        <div key={t.task} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 160, textAlign: 'right', fontSize: 13,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {t.task}
          </div>
          <div style={{
            width: barMaxWidth * t.accuracy,
            height: 20,
            background: accuracyColor(t.accuracy),
            borderRadius: 'var(--radius-sm)',
            minWidth: t.accuracy > 0 ? 4 : 0,
            transition: 'width 0.3s',
          }} />
          <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', minWidth: 40 }}>
            {Math.round(t.accuracy * 100)}%
          </span>
          <span style={{ fontSize: 11, color: 'var(--color-text-subtle)' }}>
            ({t.total})
          </span>
        </div>
      ))}
    </div>
  )
}
