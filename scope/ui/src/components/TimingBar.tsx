import type { CycleTrace } from '../api/types'

interface Props {
  trace: CycleTrace
}

export default function TimingBar({ trace }: Props) {
  const pass1Total = trace.pass1_elapsed_ms.reduce((a, b) => a + b, 0)
  const pass2 = trace.pass2_elapsed_ms || 0
  const total = pass1Total + pass2

  if (total === 0) {
    return <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>No timing data</div>
  }

  const pass1Pct = (pass1Total / total) * 100
  const pass2Pct = (pass2 / total) * 100

  return (
    <div>
      <div className="timing-bar">
        {pass1Total > 0 && (
          <div className="timing-segment pass1" style={{ width: `${pass1Pct}%` }}>
            P1: {Math.round(pass1Total)}ms
          </div>
        )}
        {pass2 > 0 && (
          <div className="timing-segment pass2" style={{ width: `${pass2Pct}%` }}>
            P2: {Math.round(pass2)}ms
          </div>
        )}
      </div>
      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
        Total: {(total / 1000).toFixed(1)}s
        {trace.pass1_elapsed_ms.length > 0 && (
          <> ({trace.pass1_elapsed_ms.length} Pass 1 calls)</>
        )}
      </div>
    </div>
  )
}
