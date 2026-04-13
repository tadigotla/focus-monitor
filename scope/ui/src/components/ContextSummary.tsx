import type { CycleDetail, CycleTrace } from '../api/types'

interface Props {
  cycle: CycleDetail
  trace: CycleTrace | null
}

export default function ContextSummary({ cycle, trace }: Props) {
  const r = cycle.raw_response
  return (
    <div className="context-summary">
      {cycle.apps_used.length > 0 && (
        <div className="context-row">
          <span className="context-label">Apps</span>
          <span className="context-value">{cycle.apps_used.join(', ')}</span>
        </div>
      )}
      {cycle.window_titles.length > 0 && (
        <div className="context-row">
          <span className="context-label">Titles</span>
          <span className="context-value">{cycle.window_titles.slice(0, 5).join(', ')}</span>
        </div>
      )}
      {r.planned_match && r.planned_match.length > 0 && (
        <div className="context-row">
          <span className="context-label">Matched tasks</span>
          <span className="context-value">{r.planned_match.join(', ')}</span>
        </div>
      )}
      {trace && trace.few_shot_ids.length > 0 && (
        <div className="context-row">
          <span className="context-label">Few-shot</span>
          <span className="context-value">{trace.few_shot_ids.length} correction(s) injected</span>
        </div>
      )}
    </div>
  )
}
