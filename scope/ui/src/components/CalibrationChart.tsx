import type { CalibrationData } from '../api/types'

interface Props {
  data: CalibrationData
}

const LEVELS: ('high' | 'medium' | 'low')[] = ['high', 'medium', 'low']
const LEVEL_COLORS = {
  high: 'var(--color-confidence-high)',
  medium: 'var(--color-confidence-mid)',
  low: 'var(--color-confidence-low)',
}

export default function CalibrationChart({ data }: Props) {
  const maxTotal = Math.max(1, ...LEVELS.map(l => data[l].total))
  const barMaxWidth = 300

  // Check if calibration is inverted (high confidence has lower accuracy than low)
  const inverted = data.high.total > 0 && data.low.total > 0
    && data.high.accuracy < data.low.accuracy

  return (
    <div>
      {inverted && (
        <div style={{
          background: '#fef3c7',
          color: '#92400e',
          padding: '8px 12px',
          borderRadius: 'var(--radius-sm)',
          fontSize: 12,
          marginBottom: 12,
        }}>
          Model may be miscalibrated: high-confidence predictions are less accurate than low-confidence ones.
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {LEVELS.map(level => {
          const d = data[level]
          const accuracyWidth = (d.accuracy * barMaxWidth * d.total) / maxTotal
          const correctedWidth = ((1 - d.accuracy) * barMaxWidth * d.total) / maxTotal
          return (
            <div key={level} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div style={{ width: 70, textAlign: 'right', fontSize: 13, fontWeight: 600 }}>
                {level}
              </div>
              <div style={{ display: 'flex', height: 24, borderRadius: 'var(--radius-sm)', overflow: 'hidden' }}>
                {accuracyWidth > 0 && (
                  <div style={{
                    width: accuracyWidth,
                    background: LEVEL_COLORS[level],
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, color: 'white', minWidth: 30,
                  }}>
                    {Math.round(d.accuracy * 100)}%
                  </div>
                )}
                {correctedWidth > 0 && (
                  <div style={{
                    width: correctedWidth,
                    background: 'var(--color-correction)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, color: 'white', minWidth: 20,
                    opacity: 0.7,
                  }}>
                    {d.corrected}
                  </div>
                )}
              </div>
              <span style={{ fontSize: 11, color: 'var(--color-text-subtle)' }}>
                n={d.total}
              </span>
            </div>
          )
        })}
      </div>
      <div style={{ marginTop: 8, fontSize: 11, color: 'var(--color-text-subtle)' }}>
        Colored bar = accurate (uncorrected). Orange = corrected.
      </div>
    </div>
  )
}
