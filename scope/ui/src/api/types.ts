// TypeScript interfaces mirroring Scope API JSON responses.

export interface Cycle {
  id: number
  timestamp: string
  task: string | null
  focus_score: number
  name_confidence: 'low' | 'medium' | 'high'
  boundary_confidence: 'low' | 'medium' | 'high'
  summary: string
}

export interface Evidence {
  signal: string
  weight: 'strong' | 'medium' | 'weak'
}

export interface Artifact {
  app: string | null
  workspace: string | null
  active_file: string | null
  terminal_cwd: string | null
  browser_url: string | null
  browser_tab_titles: string[] | null
  one_line_action: string
}

export interface CycleDetail {
  id: number
  timestamp: string
  window_titles: string[]
  apps_used: string[]
  project_detected: string[]
  is_distraction: boolean
  summary: string
  raw_response: {
    task: string | null
    focus_score: number
    evidence: Evidence[]
    boundary_confidence: string
    name_confidence: string
    needs_user_input: boolean
    projects: string[]
    planned_match: string[]
    distractions: string[]
    summary: string
    pass1_artifacts?: Artifact[]
    [key: string]: unknown
  }
}

export interface CycleTrace {
  id: number
  activity_log_id: number
  created_at: string
  pass1_prompt: string | null
  pass1_responses: string[]
  pass1_elapsed_ms: number[]
  pass2_prompt: string | null
  pass2_response_raw: string | null
  pass2_elapsed_ms: number | null
  few_shot_ids: number[]
  screenshot_paths: string[]
  parse_retries: number
}

export interface Correction {
  id: number
  created_at: string
  entry_kind: string
  entry_id: number
  range_start: string
  range_end: string
  model_task: string | null
  model_evidence: Evidence[]
  model_boundary_confidence: string
  model_name_confidence: string
  user_verdict: 'corrected' | 'confirmed'
  user_task: string | null
  user_kind: string
  user_note: string | null
  signals: Record<string, unknown>
}

export interface Session {
  id: number
  start: string
  end: string
  task: string | null
  task_name_confidence: string
  boundary_confidence: string
  cycle_count: number
  dip_count: number
  evidence: Evidence[]
  kind: string
}

// Stats types
export interface CorrectionRatePoint {
  date: string
  total_cycles: number
  corrections: number
  rate: number
}

export interface CalibrationLevel {
  total: number
  corrected: number
  accuracy: number
}

export interface CalibrationData {
  high: CalibrationLevel
  medium: CalibrationLevel
  low: CalibrationLevel
}

export interface TaskAccuracy {
  task: string
  total: number
  corrected: number
  accuracy: number
}

export interface FewShotImpact {
  correction_id: number
  correction: Correction
  signal_overlap: string[]
  before: { total: number; corrected: number; accuracy: number }
  after: { total: number; corrected: number; accuracy: number }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}
