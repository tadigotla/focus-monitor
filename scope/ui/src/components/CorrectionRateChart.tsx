import { useState } from 'react'
import type { CorrectionRatePoint } from '../api/types'

interface Props {
  data: CorrectionRatePoint[]
}

function rateColor(rate: number): string {
  if (rate <= 0.1) return 'var(--color-score-high)'
  if (rate <= 0.3) return 'var(--color-score-mid)'
  return 'var(--color-score-low)'
}

export default function CorrectionRateChart({ data }: Props) {
  const [hovered, setHovered] = useState<number | null>(null)

  if (data.length === 0) {
    return <div style={{ color: 'var(--color-text-muted)', padding: 16 }}>No data yet</div>
  }

  const maxRate = Math.max(0.1, ...data.map(d => d.rate))
  const chartHeight = 180
  const barWidth = Math.min(40, Math.max(12, 600 / data.length - 4))
  const chartWidth = data.length * (barWidth + 4) + 40

  // Moving average (7-day window)
  const showTrend = data.length > 14
  const maWindow = 7
  const movingAvg = data.map((_, i) => {
    const start = Math.max(0, i - maWindow + 1)
    const slice = data.slice(start, i + 1)
    return slice.reduce((sum, d) => sum + d.rate, 0) / slice.length
  })

  return (
    <div style={{ position: 'relative' }}>
      <svg width={chartWidth} height={chartHeight + 40} style={{ overflow: 'visible' }}>
        {/* Y-axis labels */}
        <text x={30} y={12} fontSize={10} fill="var(--color-text-subtle)" textAnchor="end">
          {Math.round(maxRate * 100)}%
        </text>
        <text x={30} y={chartHeight} fontSize={10} fill="var(--color-text-subtle)" textAnchor="end">
          0%
        </text>

        {/* Bars */}
        {data.map((d, i) => {
          const barHeight = (d.rate / maxRate) * (chartHeight - 20)
          const x = 40 + i * (barWidth + 4)
          const y = chartHeight - barHeight
          return (
            <g key={i}
               onMouseEnter={() => setHovered(i)}
               onMouseLeave={() => setHovered(null)}>
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(1, barHeight)}
                fill={rateColor(d.rate)}
                rx={2}
                opacity={hovered === i ? 1 : 0.8}
              />
              {/* Date label (show every Nth) */}
              {(i % Math.max(1, Math.floor(data.length / 7)) === 0 || i === data.length - 1) && (
                <text
                  x={x + barWidth / 2}
                  y={chartHeight + 14}
                  fontSize={9}
                  fill="var(--color-text-subtle)"
                  textAnchor="middle"
                >
                  {d.date.slice(5)}
                </text>
              )}
            </g>
          )
        })}

        {/* Trend line */}
        {showTrend && (
          <polyline
            points={movingAvg.map((avg, i) => {
              const x = 40 + i * (barWidth + 4) + barWidth / 2
              const y = chartHeight - (avg / maxRate) * (chartHeight - 20)
              return `${x},${y}`
            }).join(' ')}
            fill="none"
            stroke="var(--color-text-muted)"
            strokeWidth={1.5}
            strokeDasharray="4 2"
          />
        )}
      </svg>

      {/* Tooltip */}
      {hovered !== null && (
        <div style={{
          position: 'absolute',
          top: 0,
          right: 0,
          background: 'var(--color-surface-raised)',
          border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-sm)',
          padding: '6px 10px',
          fontSize: 12,
          fontFamily: 'var(--font-mono)',
        }}>
          {data[hovered].corrections} / {data[hovered].total_cycles} = {Math.round(data[hovered].rate * 100)}%
          <br />
          <span style={{ color: 'var(--color-text-muted)' }}>{data[hovered].date}</span>
        </div>
      )}
    </div>
  )
}
