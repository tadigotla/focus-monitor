interface Props {
  level: 'low' | 'medium' | 'high'
  label: string
}

const FILL_COUNT = { low: 1, medium: 2, high: 3 }

export default function ConfidenceBadge({ level, label }: Props) {
  const filled = FILL_COUNT[level] || 1
  return (
    <span className="confidence-badge">
      <span className="confidence-segments">
        {[0, 1, 2].map(i => (
          <span
            key={i}
            className={`confidence-segment ${i < filled ? `filled ${level}` : ''}`}
          />
        ))}
      </span>
      {label}: {level}
    </span>
  )
}
