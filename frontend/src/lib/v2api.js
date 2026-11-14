import { api } from './api';

// VoltCraft v2 (blueprint) API wrappers — thin layer over the shared axios
// instance in lib/api.js (baseURL already ends with /api, token interceptor
// already attached), so every call here is api.<verb>('/v2/...').

// Stage pipelines per zone category (PRD §2.2). Order matters: nextStage()
// walks these arrays.
export const STAGE_PIPELINES = {
  ZONE_1_RESIDENTIAL: ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
  ZONE_2_CORRIDOR: ['C1', 'C2', 'C3', 'C4', 'C5'],
  ZONE_3_RISER: ['R1', 'R2', 'R3', 'R4', 'R5'],
  ZONE_4_EXTERNAL: ['M1', 'M2', 'M3', 'M4', 'M5'],
};

// Stage display names per pipeline code (PRD §2.2 taxonomy).
export const STAGE_NAMES = {
  S1: 'Slab/Precast Conduit', S2: 'Wall Chasing & Backbox', S3: 'Cable Pulling/Wiring',
  S4: 'DB Box & Final Fix', S5: 'Testing & Commissioning', S6: 'RTO Passed & Handover',
  C1: 'Bracket & Marking', C2: 'Trunking & GI Conduit', C3: 'Sub-Main & Circuit Pulling',
  C4: 'Fittings & Accessories', C5: 'Testing & RTO Sign-off',
  R1: 'Ladder, Tray & Trunking', R2: 'Enclosure & Meter Board', R3: 'Main & Sub-Main Termination',
  R4: 'Earthing, Bonding & Labeling', R5: 'Fire-Stop & RTO Handover',
  M1: 'Trunking & Tray Run', M2: 'Surface GI Conduit', M3: 'Cable Pulling',
  M4: 'Weatherproof Lights & Isolators', M5: 'Testing & RTO',
};

export const ZONE_CATEGORY_LABELS = {
  ZONE_1_RESIDENTIAL: 'Residential Units',
  ZONE_2_CORRIDOR: 'Floor Common & Corridor',
  ZONE_3_RISER: 'Vertical Risers',
  ZONE_4_EXTERNAL: 'Block Infra & External',
};

// Module counts per subscription tier (PRD §1.3: Starter 5, Pro 10, Enterprise 14).
export const TIER_MODULE_COUNTS = { STARTER: 5, PRO: 10, ENTERPRISE: 14 };
export const TOTAL_MODULES = 14;

// Returns the next stage code for a zone, or null when it is at the final stage.
export function nextStage(zone) {
  const pipeline = STAGE_PIPELINES[zone?.zone_category] || [];
  const idx = pipeline.indexOf(zone?.current_stage_code);
  if (idx < 0 || idx >= pipeline.length - 1) return null;
  return pipeline[idx + 1];
}

// Normalizes FastAPI errors: v2 guardrails return {detail:{error_code,message}},
// plain errors return {detail:"..."} and validation returns an array.
export function v2Error(e) {
  const d = e?.response?.data?.detail;
  if (d && typeof d === 'object' && !Array.isArray(d)) {
    return { code: d.error_code || '', message: d.message || 'Request failed. Please try again.' };
  }
  if (typeof d === 'string') return { code: '', message: d };
  if (Array.isArray(d)) {
    return { code: 'VALIDATION', message: d.map(x => `${(x.loc || []).at(-1) || 'field'}: ${x.msg}`).join('; ') };
  }
  return { code: '', message: 'Connection error. Please try again.' };
}

export const v2 = {
  // Super-admin: tenants + APK releases
  listTenants: () => api.get('/v2/super-admin/tenants').then(r => r.data),
  createTenant: payload => api.post('/v2/super-admin/tenants', payload).then(r => r.data),
  patchTenant: (id, payload) => api.patch(`/v2/super-admin/tenants/${id}`, payload).then(r => r.data),
  publishApkRelease: payload => api.post('/v2/super-admin/apk-releases', payload).then(r => r.data),
  getAppRelease: () => api.get('/v2/app-release').then(r => r.data),

  // Projects + spatial matrix
  listProjects: () => api.get('/v2/projects').then(r => r.data),
  createProject: payload => api.post('/v2/projects', payload).then(r => r.data),
  getMatrix: (projectId, params) => api.get(`/v2/projects/${projectId}/matrix`, { params }).then(r => r.data),
  getZone: zoneId => api.get(`/v2/zones/${zoneId}`).then(r => r.data),
  batchAdvance: (projectId, payload) =>
    api.post(`/v2/projects/${projectId}/zones/batch-advance`, payload).then(r => r.data),
};
