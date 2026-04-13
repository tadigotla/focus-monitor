// Typed fetch functions for the Scope API.
// All requests go through the Vite proxy (/api -> 127.0.0.1:9877).

import {
  ApiError, Cycle, CycleDetail, CycleTrace, Correction,
  CorrectionRatePoint, CalibrationData, TaskAccuracy, FewShotImpact,
} from './types'

async function fetchJson<T>(path: string): Promise<T> {
  const resp = await fetch(path)
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({ error: resp.statusText }))
    throw new ApiError(resp.status, body.error || resp.statusText)
  }
  return resp.json()
}

export function fetchCycles(date: string, limit = 50, offset = 0): Promise<Cycle[]> {
  return fetchJson(`/api/cycles?date=${date}&limit=${limit}&offset=${offset}`)
}

export function fetchCycle(id: number): Promise<CycleDetail> {
  return fetchJson(`/api/cycles/${id}`)
}

export function fetchCycleTrace(id: number): Promise<CycleTrace> {
  return fetchJson(`/api/cycles/${id}/trace`)
}

export function fetchCycleCorrections(id: number): Promise<Correction[]> {
  return fetchJson(`/api/cycles/${id}/corrections`)
}

export function fetchCorrections(limit = 50, offset = 0): Promise<Correction[]> {
  return fetchJson(`/api/corrections?limit=${limit}&offset=${offset}`)
}

export function fetchCorrectionRate(days = 30): Promise<CorrectionRatePoint[]> {
  return fetchJson(`/api/stats/correction-rate?days=${days}`)
}

export function fetchConfidenceCalibration(): Promise<CalibrationData> {
  return fetchJson('/api/stats/confidence-calibration')
}

export function fetchPerTaskAccuracy(): Promise<TaskAccuracy[]> {
  return fetchJson('/api/stats/per-task-accuracy')
}

export function fetchFewShotImpact(correctionId: number): Promise<FewShotImpact> {
  return fetchJson(`/api/stats/few-shot-impact?correction_id=${correctionId}`)
}
