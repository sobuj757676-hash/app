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
export const groupText=(g,t)=>`${t('blk')} ${g.block} · L${g.level} · ${stageName({name:g.stage_name,name_key:g.stage_name_key},t)} — ${g.remaining_units} ${t('unitCount')}`;
export const PRIW={urgent:0,high:1,medium:2,low:3};
