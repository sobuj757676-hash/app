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
// Stage-aware remaining (spec v2 §3): scope units not checked AND still at
// the planned stage. Checked units belong to the advance flow; units whose
// live stage moved (advanced or changed elsewhere) are the tracker's truth,
// never re-offered as remaining work. `data` optional for legacy callers.
export const remainingUnitIds=(task,data)=>{
 const done=new Set(completedUnitIds(task));const si=task.scope?.stage_index;
 return plannedUnitIds(task).filter(id=>{
  if(done.has(id))return false;
  if(!data)return true;
  const u=(data.units||[]).find(x=>x.id===id);
  return !!u&&u.stage===si;
 });
};
// ---- Top-notch Phase 1 (spec v2.1): history-proven advance state ----
// Mirror of the backend recognition rule: an event's resulting stage is
// to_stage when present; decision events move +1 only when approved;
// otherwise stage + 1. A unit counts as advanced BY A TASK only when the
// last stage-changing transition into its current stage is that task's
// plan_advance history event.
export const eventResultingStage=h=>h.to_stage!=null?h.to_stage:('result' in h?(h.result==='approved'?h.stage+1:h.stage):h.stage+1);
export const lastTransitionInto=(unit,stage)=>{
 let found=null;
 for(const h of unit.history||[]){const r=eventResultingStage(h);if(r===stage&&r!==h.stage)found=h;}
 return found;
};
export const advancedByTask=(unit,stage,taskId)=>{const h=lastTransitionInto(unit,stage);return !!h&&h.source==='plan_advance'&&h.task_id===taskId;};
// Checked units of a task that this task already advanced (locked chips).
export const advancedUnitIds=(task,data)=>{
 const si=task.scope?.stage_index;if(si==null)return [];
 const done=new Set(completedUnitIds(task));
 return plannedUnitIds(task).filter(id=>{
  if(!done.has(id))return false;
  const u=(data.units||[]).find(x=>x.id===id);
  return !!u&&u.stage>si&&advancedByTask(u,u.stage,task.id);
 });
};
// Pending Advance derivation (spec v2.1 §C + addendum): checked units that
// still need advancement or review. Considers every planned task that is
// not cancelled — INCLUDING done tasks: a done status never strands a
// checked unit. Reasons: ready | rto | defect | tests | conflict.
// Returns [{unit, reason, detail}] for one task.
export const pendingAdvanceUnits=(task,data)=>{
 if(!task||task.status==='cancelled'||!task.scope)return [];
 const si=task.scope.stage_index;const stages=stagesOf(data);const done=new Set(completedUnitIds(task));
 const out=[];
 for(const id of plannedUnitIds(task)){
  if(!done.has(id))continue;
  const u=(data.units||[]).find(x=>x.id===id);
  if(!u)continue;
  if(u.stage>si){if(!advancedByTask(u,u.stage,task.id))out.push({unit:u,reason:'conflict'});continue;}
  if(u.stage<si){out.push({unit:u,reason:'conflict'});continue;}
  const st=stages[si];
  if(st&&st.requires_rto){out.push({unit:u,reason:'rto'});continue;}
  const defect=(data.defects||[]).find(d=>d.unit_id===id&&d.severity==='critical'&&!['verified','cancelled'].includes(d.status));
  if(defect){out.push({unit:u,reason:'defect',detail:defect.title});continue;}
  if(si===stages.length-1){
   const mine=(data.tests||[]).filter(x=>x.unit_id===id);
   const latest={};for(const x of mine)latest[x.point_id]=x;
   const ok=(u.points||[]).length>0&&(u.points||[]).every(p=>latest[p.id]?.result==='pass');
   if(!ok){out.push({unit:u,reason:'tests'});continue;}
  }
  out.push({unit:u,reason:'ready'});
 }
 return out;
};
export const pendingAdvanceGroups=(tasks,data)=>(tasks||[])
 .filter(x=>isPlannedTask(x))
 .map(task=>({task,items:pendingAdvanceUnits(task,data)}))
 .filter(g=>g.items.length>0);
// Full replacement list for PATCH {completed_unit_ids} after toggling one chip.
export const toggleCompletedIds=(task,id)=>{const cur=completedUnitIds(task);return cur.includes(id)?cur.filter(x=>x!==id):[...cur,id];};
// Client-side staleness: a scope unit is stale when its live stage differs
// from the planned stage_index, or its RTO state is 'rework'.
export const staleUnits=(task,data)=>{const s=task.scope||{};return (s.unit_ids||[]).map(id=>data.units.find(u=>u.id===id)).filter(Boolean).filter(u=>u.rto==='rework'||u.stage!==s.stage_index);};
export const isPlannedTask=x=>(x.kind==='planned'||(!x.kind&&x.plan_date))&&!!x.plan_date;
