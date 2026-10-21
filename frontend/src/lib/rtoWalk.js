// RTO Walk derivations (spec v2 §4 + v2.1 §D): pure functions over the
// workspace payload. The gate index always derives from the project's
// stage configuration — never a hardcoded number.
import {stagesOf} from './api';

export const gateIndexOf = data => stagesOf(data).findIndex(s => s.requires_rto);

// At most one inspection per unit can be pending; map unit_id -> record.
export function pendingInspectionByUnit(data){
 const map = new Map();
 for(const i of data.inspections || []) if(i.status === 'pending') map.set(i.unit_id, i);
 return map;
}

// Units with a server-confirmed proposal (v2.1 §D): rendered locked in the
// walk — their outcome is already submitted and awaiting a decision.
export function proposedUnitIds(data){
 const ids = new Set();
 for(const i of data.inspections || [])
  if(i.status === 'pending' && i.proposed_result) ids.add(i.unit_id);
 return ids;
}

// Walk candidates for one block: units at the gate stage, grouped by
// level (ascending), units ordered by number within a floor.
export function walkFloors(data, block){
 const g = gateIndexOf(data);
 if(g < 0) return [];
 const byLevel = new Map();
 for(const u of data.units || []){
  if(u.block !== block || u.stage !== g) continue;
  if(!byLevel.has(u.level)) byLevel.set(u.level, []);
  byLevel.get(u.level).push(u);
 }
 return [...byLevel.entries()].sort((a, b) => a[0] - b[0]).map(([level, units]) => ({
  level,
  units: units.slice().sort((a, b) => String(a.number).localeCompare(String(b.number), undefined, {numeric: true})),
 }));
}

// Blocks that currently have at least one gate-stage unit, in project order.
export function walkBlocks(data){
 const g = gateIndexOf(data);
 if(g < 0) return [];
 const seen = [];
 for(const b of data.blocks || []) if(!seen.includes(b.name)) seen.push(b.name);
 return seen.filter(name => (data.units || []).some(u => u.block === name && u.stage === g));
}

// "Floor inspected — pass the rest": every non-failed unit on the floor
// becomes 'pass'. Units carrying a server proposal are locked and skipped.
export function applyFloorPass(marks, floor, proposedIds){
 const next = {...marks};
 for(const u of floor.units){
  if(proposedIds.has(u.id)) continue;
  if(next[u.id] !== 'fail') next[u.id] = 'pass';
 }
 return next;
}

// Local draft (marks are a pre-submission scratchpad only — v2.1 §F).
// Keyed by project + date; nothing here is server state.
const draftKey = (pid, date) => `rto-walk:${pid}:${date}`;
export function loadWalkDraft(pid, date){
 try{
  const raw = localStorage.getItem(draftKey(pid, date));
  return raw ? JSON.parse(raw) : null;
 }catch{ return null; }
}
export function saveWalkDraft(pid, date, draft){
 try{ localStorage.setItem(draftKey(pid, date), JSON.stringify(draft)); }catch{ /* storage unavailable */ }
}
export function clearWalkDraft(pid, date){
 try{ localStorage.removeItem(draftKey(pid, date)); }catch{ /* ignore */ }
}
