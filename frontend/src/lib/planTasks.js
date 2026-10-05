import {stageName,stagesOf} from './api';
// Helpers for multi-worker tasks + daily work plan (Parts B/C).
// stageName()/stagesOf() are the Part-A shared helpers from lib/api.js
// (single source — do not redefine them here).
// Resolve a stage index to its display name (dynamic stages, with a safe
// fallback when the index is out of range).
export const resolveStage=(data,idx,t)=>{const s=stagesOf(data)[idx];return s?stageName(s,t):t(`stage${idx}`);};
// Backend writes assignees now; fall back to the old assigned_to during rollout.
export const isAssigned=(task,uid)=>!!uid&&(task.assignees||(task.assigned_to?[task.assigned_to]:[])).includes(uid);
// "Karim, Hasan +2" from denormalized assignee_names (or the old single name).
export const assigneeNames=(task,t)=>{const ns=task.assignee_names||(task.assigned_to_name?[task.assigned_to_name]:[]);if(ns.length>2)return `${ns[0]}, ${ns[1]} +${ns.length-2}`;if(ns.length)return ns.join(', ');return t('unassigned');};
// "Blk 40A · L12 · Wire pulling — 5 units" for a stage-group row.
export const groupText=(g,t)=>`${t('blk')} ${g.block} · L${g.level} · ${stageName({name:g.stage_name,name_key:g.stage_name_key},t)} — ${unitCount(g.remaining_units,t)}`;
export const PRIW={urgent:0,high:1,medium:2,low:3};
// ---- Daily-plan redesign (2026-10-05): execution state on planned tasks ----
// "1 unit" vs "N units" — grammar fix for every count display.
export const unitCount=(n,t)=>`${n} ${n===1?t('unitSing'):t('unitCount')}`;
export const plannedUnitIds=task=>task.scope?.unit_ids||[];
export const completedUnitIds=task=>task.completed_unit_ids||[];
export const remainingUnitIds=task=>{const done=new Set(completedUnitIds(task));return plannedUnitIds(task).filter(id=>!done.has(id));};
// Full replacement list for PATCH {completed_unit_ids} after toggling one chip.
export const toggleCompletedIds=(task,id)=>{const cur=completedUnitIds(task);return cur.includes(id)?cur.filter(x=>x!==id):[...cur,id];};
// Client-side staleness: a scope unit is stale when its live stage differs
// from the planned stage_index, or its RTO state is 'rework'.
export const staleUnits=(task,data)=>{const s=task.scope||{};return (s.unit_ids||[]).map(id=>data.units.find(u=>u.id===id)).filter(Boolean).filter(u=>u.rto==='rework'||u.stage!==s.stage_index);};
export const isPlannedTask=x=>(x.kind==='planned'||(!x.kind&&x.plan_date))&&!!x.plan_date;
