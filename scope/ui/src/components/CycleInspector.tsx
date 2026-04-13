import { useEffect, useState } from 'react'
import type { Cycle, CycleDetail, CycleTrace, Correction, Artifact } from '../api/types'
import { fetchCycle, fetchCycleTrace, fetchCycleCorrections } from '../api/client'
import ArtifactCard from './ArtifactCard'
import ContextSummary from './ContextSummary'
import PromptViewer from './PromptViewer'
import ConfidenceBadge from './ConfidenceBadge'
import EvidenceList from './EvidenceList'
import TimingBar from './TimingBar'
import CorrectionBadge from './CorrectionBadge'

interface Props {
  cycleId: number
  onPrev: (() => void) | null
  onNext: (() => void) | null
}

function scoreClass(score: number): string {
  if (score >= 80) return 'high'
  if (score >= 50) return 'mid'
  return 'low'
}

function parseArtifact(raw: string): Artifact | null {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export default function CycleInspector({ cycleId, onPrev, onNext }: Props) {
  const [detail, setDetail] = useState<CycleDetail | null>(null)
  const [trace, setTrace] = useState<CycleTrace | null>(null)
  const [corrections, setCorrections] = useState<Correction[]>([])
  const [loading, setLoading] = useState(true)
  const [rawExpanded, setRawExpanded] = useState(false)

  useEffect(() => {
    setLoading(true)
    setDetail(null)
    setTrace(null)
    setCorrections([])

    Promise.all([
      fetchCycle(cycleId).catch(() => null),
      fetchCycleTrace(cycleId).catch(() => null),
      fetchCycleCorrections(cycleId).catch(() => []),
    ]).then(([d, t, c]) => {
      setDetail(d)
      setTrace(t)
      setCorrections(c)
      setLoading(false)
    })
  }, [cycleId])

  if (loading) {
    return <div className="main-panel"><div className="loading">Loading cycle...</div></div>
  }

  if (!detail) {
    return <div className="main-panel"><div className="empty-state">Cycle not found</div></div>
  }

  const r = detail.raw_response
  const artifacts: Artifact[] = trace
    ? trace.pass1_responses
        .map(raw => parseArtifact(raw))
        .filter((a): a is Artifact => a !== null)
    : (r.pass1_artifacts || [])

  return (
    <div className="main-panel">
      {/* Header with navigation */}
      <div className="inspector-header">
        <h2>{r.task || '(unclear)'}</h2>
        <div className="nav-buttons">
          <button onClick={onPrev ?? undefined} disabled={!onPrev}>&larr; Prev</button>
          <button onClick={onNext ?? undefined} disabled={!onNext}>Next &rarr;</button>
        </div>
      </div>

      {/* INPUTS section */}
      <div className="section">
        <div className="section-header">Inputs</div>
        <div className="section-body">
          <ContextSummary cycle={detail} trace={trace} />

          {artifacts.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: 8 }}>
                Pass 1 Artifacts ({artifacts.length})
              </div>
              {artifacts.map((art, i) => (
                <ArtifactCard
                  key={i}
                  artifact={art}
                  index={i}
                  screenshotPath={trace?.screenshot_paths[i]}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {trace && <PromptViewer prompt={trace.pass2_prompt} />}

      {/* OUTPUT section */}
      <div className="section">
        <div className="section-header">Output</div>
        <div className="section-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 12 }}>
            <span className={`focus-score ${scoreClass(r.focus_score)}`}>
              {r.focus_score >= 0 ? r.focus_score : '?'}
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <ConfidenceBadge level={r.name_confidence as 'low' | 'medium' | 'high'} label="name" />
              <ConfidenceBadge level={r.boundary_confidence as 'low' | 'medium' | 'high'} label="boundary" />
            </div>
          </div>

          <EvidenceList evidence={r.evidence || []} />

          {r.projects.length > 0 && (
            <div style={{ marginTop: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Projects: </span>
              <span className="tag-list">
                {r.projects.map((p, i) => <span key={i} className="tag">{p}</span>)}
              </span>
            </div>
          )}

          {r.distractions.length > 0 && (
            <div style={{ marginTop: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>Distractions: </span>
              <span className="tag-list">
                {r.distractions.map((d, i) => <span key={i} className="tag">{d}</span>)}
              </span>
            </div>
          )}

          <div className="section" style={{ marginTop: 12 }}>
            <div className="section-header" onClick={() => setRawExpanded(!rawExpanded)}>
              Raw Response
              <span className="toggle">{rawExpanded ? '\u25BC' : '\u25B6'}</span>
            </div>
            {rawExpanded && (
              <div className="section-body">
                <pre className="raw-json">{JSON.stringify(r, null, 2)}</pre>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* META section */}
      <div className="section">
        <div className="section-header">Meta</div>
        <div className="section-body">
          {trace && <TimingBar trace={trace} />}

          <div style={{ marginTop: 8, fontSize: 13 }}>
            <span style={{ color: trace && trace.parse_retries > 0 ? 'var(--color-score-mid)' : 'var(--color-score-high)' }}>
              {trace ? (trace.parse_retries === 0 ? 'No parse retries' : `${trace.parse_retries} parse retries`) : 'No trace data'}
            </span>
          </div>

          <div style={{ marginTop: 8 }}>
            <CorrectionBadge corrections={corrections} />
          </div>
        </div>
      </div>
    </div>
  )
}
