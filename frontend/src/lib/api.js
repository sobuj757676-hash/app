import axios from 'axios';
export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL || ''}/api` });
// Attach the session token to every request.
api.interceptors.request.use(c=>{const t=localStorage.getItem('voltcraft-token');if(t)c.headers.Authorization=`Bearer ${t}`;return c;});
// On 401 (missing/expired/invalid token) drop the session and go to login.
// Skip the login request itself so it can surface "invalid credentials".
// App.js registers a React-state-driven handler via setOnUnauthorized (navigate + toast);
// if none is registered (e.g. outside the router) we keep the old hard redirect.
let onUnauthorized=null;
export const setOnUnauthorized=cb=>{onUnauthorized=cb;};
api.interceptors.response.use(r=>r,e=>{
 if(e.response?.status===401&&!String(e.config?.url||'').includes('/auth/login')){
  localStorage.removeItem('voltcraft-token');
  if(typeof onUnauthorized==='function')onUnauthorized();
  else if(!window.location.pathname.startsWith('/login'))window.location.href='/login';
 }
 return Promise.reject(e);
});
export const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export const money = n => new Intl.NumberFormat('en-SG', { style: 'currency', currency: 'SGD', maximumFractionDigits: 2, minimumFractionDigits: 0 }).format(n || 0);
// Central date formatters: lang-mapped locale + Asia/Singapore (the Overview.jsx pattern).
// Use these everywhere instead of bare toLocaleString()/toLocaleDateString().
const _loc = l => l==='bn'?'bn-BD':l==='zh'?'zh-CN':'en-GB';
export const fmtDate = (v, lang='en') => { try { return new Intl.DateTimeFormat(_loc(lang),{day:'numeric',month:'short',year:'numeric',timeZone:'Asia/Singapore'}).format(new Date(v)); } catch { return String(v??''); } };
export const fmtDateTime = (v, lang='en') => { try { return new Intl.DateTimeFormat(_loc(lang),{day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'Asia/Singapore'}).format(new Date(v)); } catch { return String(v??''); } };
export const label = u => `#${String(u.level).padStart(2,'0')}-${u.number}`;
export const percent = (units, stageCount) => units.length && stageCount ? Math.round(units.reduce((n,u)=>n+Math.min(u.stage,stageCount),0)/(units.length*stageCount)*100) : 0;
export const status = (u, stageCount=9) => u.rto === 'rework' ? 'rework' : stageCount && u.stage >= stageCount ? 'completed' : u.rto === 'pending' ? 'pending' : u.stage === 0 ? 'notStarted' : 'inProgress';
// Dynamic workflow stages (Part A). The backend carries the project's ordered
// stage list on data.project.workflow_stages; these helpers resolve it with a
// built-in 9-stage fallback so the UI keeps working before the backend ships.
// stageName(stage, t): built-ins keep bn/zh via name_key; custom stages show
// as typed in every language.
export const stageName = (stage, t) => stage ? (stage.name_key ? t(stage.name_key) : stage.name) : '';
export const DEFAULT_STAGES = [
 {id:'s0',name:'Slab PVC laying',name_key:'stage0',requires_rto:false},{id:'s1',name:'Casting complete',name_key:'stage1',requires_rto:false},{id:'s2',name:'Point hacking',name_key:'stage2',requires_rto:false},{id:'s3',name:'Wire pulling',name_key:'stage3',requires_rto:false},{id:'s4',name:'GI/PVC & gang boxes',name_key:'stage4',requires_rto:false},{id:'s5',name:'RTO approval',name_key:'stage5',requires_rto:true},{id:'s6',name:'Cement plastering',name_key:'stage6',requires_rto:false},{id:'s7',name:'Accessories fitting',name_key:'stage7',requires_rto:false},{id:'s8',name:'Insulation testing',name_key:'stage8',requires_rto:false}];
export const stagesOf = data => data?.project?.workflow_stages?.length ? data.project.workflow_stages : DEFAULT_STAGES;
export const stageCountOf = data => stagesOf(data).length;
// Common backend `detail` strings mapped to i18n keys. errorText(e, t) localizes
// them when a t() is passed; without t it returns the raw detail (safe fallback).
const DETAIL_I18N={
 'Invalid credentials':'invalidCredentials',
 'Current password is incorrect':'wrongCurrentPassword',
 'Email or phone is required':'identifierRequired',
 'You do not have permission for this action':'noPermission',
 'Managers can only manage worker accounts':'managerWorkerOnly',
 'Managers can only create worker accounts':'managerWorkerOnly',
 'Managers can only reset worker passwords':'managerWorkerOnly',
 'Managers can only activate or deactivate workers':'managerWorkerOnly',
 'You cannot deactivate your own account':'cannotDeactivateSelf',
 'Worker is archived':'workerArchived',
 'Assignee not found or inactive':'assigneeInvalid',
 'Only the reporter or an engineer can edit this defect':'defectEditDenied',
 'Only JPEG, PNG or WebP photos are accepted':'photoTypeInvalid',
 'Photo must be 10 MB or smaller':'photoTooLarge',
 'File is not a valid image':'photoInvalid',
 'Unit changed. Refresh and retry.':'unitChangedRetry',
 'All readiness checklist items must be confirmed':'checklistConfirmAll',
 'RTO readiness checklist is required — confirm every item before requesting':'checklistRequired',
 'RTO approval required before plastering':'rtoApprovalRequired',
 'Inspection is already closed':'inspectionClosed',
 'Complete installation first; only one pending inspection is allowed':'inspectionOnePending',
 'Completed unit cannot accept new points':'unitCompletedNoPoints',
 'Only sample units can be reset':'onlySampleReset',
 'Unit has real inspection or test records and cannot be reset':'unitHasRecords',
 'Insufficient stock':'insufficientStock',
};
export const errorText = (e, t) => {
 const d = e?.response?.data?.detail;
 if (typeof d === 'string') { const k = DETAIL_I18N[d]; return (k && typeof t === 'function') ? (t(k) || d) : d; }
 if (Array.isArray(d)) return d.map(x => `${x.loc.at(-1)}: ${x.msg}`).join('; ');
 return typeof t === 'function' ? t('connectionError') : 'Connection error. Please try again.';
};
export async function download(pid,kind) { const {data}=await api.get(`/projects/${pid}/export/${kind}`,{responseType:'blob'});const url=URL.createObjectURL(data);const a=document.createElement('a');a.href=url;a.download=`voltcraft-${kind}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }