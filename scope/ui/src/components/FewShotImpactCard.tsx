import { useEffect, useState } from 'react'
import type { Correction, FewShotImpact } from '../api/types'
import { fetchCorrections, fetchFewShotImpact } from '../api/client'

export default function FewShotImpactCard() {
  const [corrections, setCorrections] = useState<Correction[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [impact, setImpact] = useState<FewShotImpact | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchCorrections(20)
      .then(corrs => {
        setCorrections(corrs)
        if (corrs.length > 0 && selectedId === null) {
          setSelectedId(corrs[0].id)
        }
      })
      .catch(() => setCorrections([]))
  }, [])

  useEffect(() => {
    if (selectedId === null) return
    setLoading(true)
    fetchFewShotImpact(selectedId)
      .then(setImpact)
      .catch(() => setImpact(null))
      .finally(() => setLoading(false))
  }, [selectedId])

  if (corrections.length === 0) {
    return (
      <div style={{ padding: 16, color: 'var(--color-text-muted)', fontSize: 13 }}>
        <p style={{ marginBottom: 8 }}>No corrections yet.</p>
        <p>
          When you correct the model via the Pulse dashboard, those corrections
          are injected as few-shot examples into future classification prompts.
          This card will show whether those corrections actually improved accuracy
          on similar activity.
        </p>
      </div>
    )
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <label style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
          Correction:{' '}
          <select
            value={selectedId ?? ''}
            onChange={e => setSelectedId(Number(e.target.value))}
            style={{
              padding: '4px 8px',
              border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--color-bg)',
              color: 'var(--color-text)',
              fontSize: 13,
            }}
          >
            {corrections.map(c => (
              <option key={c.id} value={c.id}>
                #{c.id}: {c.model_task ?? '?'} → {c.user_task ?? c.user_kind}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading ? (
        <div style={{ color: 'var(--color-text-muted)' }}>Loading...</div>
      ) : impact ? (
        <div>
          {/* What the correction was */}
          <div style={{ fontSize: 13, marginBottom: 12 }}>
            <span style={{ color: 'var(--color-text-muted)' }}>Model said: </span>
            <span>{impact.correction.model_task ?? '(unclear)'}</span>
            <span style={{ color: 'var(--color-text-muted)' }}> → User said: </span>
            <span style={{ fontWeight: 600 }}>{impact.correction.user_task ?? impact.correction.user_kind}</span>
          </div>

          {impact.signal_overlap.length > 0 && (
            <div style={{ fontSize: 12, marginBottom: 12 }}>
              <span style={{ color: 'var(--color-text-muted)' }}>Matching signals: </span>
              {impact.signal_overlap.map((s, i) => (
                <span key={i} className="tag" style={{ marginRight: 4 }}>{s}</span>
              ))}
            </div>
          )}

          {/* Before/After comparison */}
          <div style={{ display: 'flex', gap: 24 }}>
            <ComparisonBox label="Before correction" data={impact.before} />
            <ComparisonBox label="After correction" data={impact.after} />
          </div>

          {(impact.before.total < 5 || impact.after.total < 5) && (
            <div style={{
              marginTop: 8, fontSize: 11, color: 'var(--color-text-subtle)',
              fontStyle: 'italic',
            }}>
              Low sample size — interpret with caution
            </div>
          )}
        </div>
      ) : (
        <div style={{ color: 'var(--color-text-muted)' }}>No impact data available</div>
      )}
    </div>
  )
}

function ComparisonBox({ label, data }: {
  label: string
  data: { total: number; corrected: number; accuracy: number }
}) {
  const accPct = Math.round(data.accuracy * 100)
  return (
    <div style={{
      flex: 1,
      background: 'var(--color-bg)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-sm)',
      padding: 12,
    }}>
      <div style={{ fontSize: 11, color: 'var(--color-text-muted)', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 700, fontFamily: 'var(--font-mono)' }}>
        {data.total > 0 ? `${accPct}%` : 'N/A'}
      </div>
      <div style={{ fontSize: 11, color: 'var(--color-text-subtle)' }}>
        {data.total} similar cycles, {data.corrected} corrected
      </div>
    </div>
  )
}
