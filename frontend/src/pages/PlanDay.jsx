import {useState,useEffect} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Loader2,CalendarDays,Check} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import {api,label,today,errorText,stageName} from '../lib/api';
import {resolveStage,assigneeNames,groupText,PRIW} from '../lib/planTasks';
import {PageTitle,StatusBadge,Empty} from '../components/Common';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '../components/ui/dialog';
import {Button} from '../components/ui/button';
import {Input} from '../components/ui/input';
import {AssigneeMultiSelect} from '../components/AssigneeMultiSelect';
import {toast} from 'sonner';

const PRIS=['low','medium','high','urgent'];
const canPlan=u=>['admin','manager','engineer','supervisor'].includes(u?.role);
const isPlanned=x=>(x.kind==='planned'||(!x.kind&&x.plan_date))&&!!x.plan_date;

// "Blk 40A · L12 · Wire pulling — 5 units" for a planned task's scope.
export const planScopeText=(task,data,t)=>{const s=task.scope||{};const b=data.blocks.find(x=>x.id===s.block_id);return `${t('blk')} ${b?.name||s.block||'?'} · L${s.level??'?'} · ${resolveStage(data,s.stage_index,t)} — ${(s.unit_ids||[]).length} ${t('unitCount')}`;};

function PlanSheet({group,date,onClose}){
 const {t}=useLanguage();const {data,mutate}=useWorkspace();
 const [dir,setDir]=useState([]),[dirErr,setDirErr]=useState(false);
 const [ids,setIds]=useState([]),[pri,setPri]=useState('medium'),[note,setNote]=useState(''),[assErr,setAssErr]=useState(false),[busy,setBusy]=useState(false);
 const loadDir=()=>{setDirErr(false);api.get('/auth/directory').then(r=>setDir(r.data)).catch(()=>setDirErr(true));};
 useEffect(loadDir,[]);
 const title=`${t('blk')} ${group.block} · L${group.level} · ${stageName({name:group.stage_name,name_key:group.stage_name_key},t)}`;
 const submit=async e=>{
  e.preventDefault();if(busy)return;
  if(!ids.length){setAssErr(true);return;}
  setBusy(true);
  try{
   await mutate('post',`/projects/${data.project.id}/tasks`,{title,description:note||null,kind:'planned',scope:{block_id:group.block_id,level:group.level,stage_index:group.stage_index,unit_ids:group.unit_ids},plan_date:date,assignees:ids,priority:pri});
   toast.success(t('saved'));onClose();
  }catch{/* toasted by mutate */}finally{setBusy(false);}
 };
 return <Dialog open onOpenChange={x=>!x&&onClose()}><DialogContent className="form-modal" data-testid="plan-sheet">
  <DialogHeader><DialogTitle data-testid="plan-sheet-title">{t('addToPlan')}</DialogTitle><DialogDescription className="sr-only">{title}</DialogDescription></DialogHeader>
  <p className="plan-group-line" data-testid="plan-sheet-group">{groupText(group,t)}</p>
  <form onSubmit={submit} data-testid="plan-sheet-form"><div className="form-fields">
   <label className="wide">{t('defectTitle')}<Input data-testid="plan-title" className="field-input" required maxLength={150} value={title} onChange={()=>{}} readOnly/></label>
   <div className="wide"><span className="field-label">{t('assignees')}<small>{t('selectWorkersHint')}</small></span>
    <AssigneeMultiSelect directory={dir} value={ids} onChange={x=>{setIds(x);setAssErr(false);}} id="plan-assignees"/>
    {assErr&&<div className="inline-error" role="alert" data-testid="plan-assignees-error"><span>{t('selectAtLeastOne')}</span></div>}
    {dirErr&&<div className="inline-error" role="alert" data-testid="plan-directory-error"><span>{t('directoryLoadFailed')}</span><button type="button" className="text-link" onClick={loadDir}>{t('retry')}</button></div>}
   </div>
   <label>{t('priority')}<select data-testid="plan-priority" className="field-input" value={pri} onChange={e=>setPri(e.target.value)}>{PRIS.map(p=><option key={p} value={p}>{t(p)}</option>)}</select></label>
   <label>{t('planFor')}<Input data-testid="plan-date" className="field-input" type="date" value={date} readOnly/></label>
   <label className="wide">{t('note')}<textarea data-testid="plan-note" rows={3} maxLength={2000} value={note} onChange={e=>setNote(e.target.value)} placeholder={t('planNoteHint')}/></label>
  </div><div className="form-footer">
   <Button type="button" variant="outline" data-testid="plan-sheet-cancel" onClick={onClose}>{t('cancel')}</Button>
   <Button type="submit" className="action" disabled={busy} data-testid="plan-sheet-submit">{busy&&<Loader2 className="spin" size={15}/>} {t('addToPlan')}</Button>
  </div></form>
 </DialogContent></Dialog>;
}

function ReassignDialog({task,onClose}){
 const {t}=useLanguage();const {mutate}=useWorkspace();
 const [dir,setDir]=useState([]),[ids,setIds]=useState(task.assignees||[]),[busy,setBusy]=useState(false),[assErr,setAssErr]=useState(false);
 useEffect(()=>{api.get('/auth/directory').then(r=>setDir(r.data)).catch(()=>{});},[]);
 const save=async()=>{if(busy)return;if(!ids.length){setAssErr(true);return;}setBusy(true);
  try{await mutate('patch',`/tasks/${task.id}`,{assignees:ids});toast.success(t('saved'));onClose();}catch{/* toasted by mutate */}finally{setBusy(false);}};
 return <Dialog open onOpenChange={x=>!x&&onClose()}><DialogContent className="form-modal" data-testid="reassign-dialog">
  <DialogHeader><DialogTitle>{t('reassign')}</DialogTitle><DialogDescription className="sr-only">{task.title}</DialogDescription></DialogHeader>
  <div className="form-fields"><div className="wide"><span className="field-label">{t('assignees')}</span>
   <AssigneeMultiSelect directory={dir} value={ids} onChange={x=>{setIds(x);setAssErr(false);}} id="reassign-assignees"/>
   {assErr&&<div className="inline-error" role="alert"><span>{t('selectAtLeastOne')}</span></div>}
  </div></div><div className="form-footer">
   <Button type="button" variant="outline" onClick={onClose}>{t('cancel')}</Button>
   <Button type="button" className="action" disabled={busy} data-testid="reassign-save" onClick={save}>{busy&&<Loader2 className="spin" size={15}/>} {t('save')}</Button>
  </div>
 </DialogContent></Dialog>;
}

function PlanItem({task,adv,advBusy,onAdvance,onReassign,onCancel}){
 const {t}=useLanguage();const {data}=useWorkspace();
 const s=task.scope||{};const ids=s.unit_ids||[];
 const advanced=ids.length>0&&ids.every(id=>{const u=data.units.find(x=>x.id===id);return u&&u.stage>s.stage_index;});
 const prompt=t('advancePrompt').replace('{n}',String(ids.length)).replace('{stage}',resolveStage(data,s.stage_index,t));
 return <div className="plan-item" data-testid={`plan-item-${task.id}`}>
  <div className="task-top"><StatusBadge value={task.status} id={`plan-status-${task.id}`}/><span className={`priority-tag ${task.priority}`}>{t(task.priority)}</span></div>
  <strong>{task.title}</strong>
  {task.description&&<p className="task-desc">{task.description}</p>}
  <div className="task-meta"><span data-testid={`plan-scope-${task.id}`}>{planScopeText(task,data,t)}</span><span>{assigneeNames(task,t)}</span></div>
  {task.status==='done'&&!advanced&&<button type="button" className="advance-prompt" data-testid={`plan-advance-${task.id}`} disabled={advBusy===task.id} onClick={onAdvance}><Check size={15}/>{advBusy===task.id?t('advancing'):prompt}</button>}
  {task.status==='done'&&advanced&&<p className="advance-done" data-testid={`plan-advanced-${task.id}`}>{t('advanced')}</p>}
  {adv?.taskId===task.id&&<ul className="adv-report" data-testid={`plan-adv-report-${task.id}`}>{adv.results.map((r,i)=>{const u=data.units.find(x=>x.id===(r.unit_id||r.id));return <li key={i} className={r.error?'adv-err':''}>{u?`${t('blk')} ${u.block} · ${label(u)}`:(r.unit_label||r.unit_id||'—')} — {r.error?r.error:t('done')}</li>;})}</ul>}
  <div className="plan-item-actions">
   <button type="button" className="table-action" data-testid={`plan-reassign-${task.id}`} onClick={onReassign}>{t('reassign')}</button>
   {!['done','cancelled'].includes(task.status)&&<button type="button" className="table-action danger" data-testid={`plan-cancel-${task.id}`} onClick={onCancel}>{t('cancel')}</button>}
  </div>
 </div>;
}

export default function PlanDay(){
 const {t}=useLanguage();const {data,pid,mutate,refresh}=useWorkspace();const {user}=useAuth();
 const [params,setParams]=useSearchParams();
 const date=params.get('date')||today();
 const setDate=d=>setParams(p=>{const n=new URLSearchParams(p);d===today()?n.delete('date'):n.set('date',d);return n;});
 const [groups,setGroups]=useState([]),[gBusy,setGBusy]=useState(true),[gErr,setGErr]=useState(false);
 const [sheet,setSheet]=useState(null),[reassign,setReassign]=useState(null);
 const [adv,setAdv]=useState(null),[advBusy,setAdvBusy]=useState(null);
 const loadGroups=()=>{setGBusy(true);setGErr(false);api.get(`/projects/${pid}/stage-groups`).then(r=>setGroups(r.data||[])).catch(()=>setGErr(true)).finally(()=>setGBusy(false));};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 useEffect(()=>{loadGroups();},[pid]);
 const plans=(data.tasks||[]).filter(x=>isPlanned(x)&&x.plan_date===date).sort((a,b)=>PRIW[a.priority]-PRIW[b.priority]||(a.created_at||'').localeCompare(b.created_at||''));
 const plannedFor=g=>plans.some(p=>p.scope&&p.scope.block_id===g.block_id&&p.scope.level===g.level&&p.scope.stage_index===g.stage_index);
 const doAdvance=async task=>{
  const ids=task.scope?.unit_ids||[];if(!ids.length||advBusy)return;setAdvBusy(task.id);setAdv(null);
  try{
   const {data:r}=await api.post(`/projects/${pid}/units/bulk-advance`,{unit_ids:ids,to_stage:(task.scope?.stage_index??0)+1});
   const results=r?.results||r||[];
   setAdv({taskId:task.id,results});
   toast.success(t('advDone').replace('{ok}',String(results.filter(x=>!x.error).length)).replace('{n}',String(ids.length)));
   refresh();
  }catch(e){toast.error(errorText(e,t));}finally{setAdvBusy(null);}
 };
 const cancelTask=async task=>{if(!window.confirm(t('cancelTaskConfirm')))return;try{await mutate('post',`/tasks/${task.id}/transition`,{status:'cancelled'});toast.success(t('saved'));}catch{/* toasted by mutate */}};
 if(!canPlan(user))return <div className="page-enter"><Empty text={t('noAccess')}/></div>;
 return <div className="page-enter" data-testid="plan-day">
  <PageTitle title={t('dailyPlan')} subtitle={t('dailyPlanSub')}><label className="plan-date-field"><CalendarDays size={15}/><input type="date" data-testid="plan-day-date" value={date} max="2099-12-31" onChange={e=>e.target.value&&setDate(e.target.value)}/></label></PageTitle>
  <div className="plan-columns">
   <section className="plan-groups" data-testid="plan-groups">
    <h2>{t('workWaiting')}</h2>
    {gErr
     ?<div className="inline-error" role="alert" data-testid="plan-groups-error"><span>{t('groupsLoadFailed')}</span><button type="button" className="text-link" onClick={loadGroups}>{t('retry')}</button></div>
     :gBusy?<p className="empty">{t('loading')}</p>
     :groups.length?groups.map(g=><button key={`${g.block_id}-${g.level}-${g.stage_index}`} type="button" className="group-row" data-testid={`plan-group-${g.block_id}-${g.level}-${g.stage_index}`} onClick={()=>setSheet(g)}>
       <span className={`group-check${plannedFor(g)?' checked':''}`} aria-hidden="true">{plannedFor(g)&&<Check size={14}/>}</span>
       <span className="group-text">{groupText(g,t)}</span>
      </button>):<Empty text={t('noGroups')}/>}
   </section>
   <section className="plan-list" data-testid="plan-list">
    <h2>{t('planTasks')} · <span className="mono">{date}</span> <span className="count-pill">{plans.length}</span></h2>
    {plans.length?plans.map(p=><PlanItem key={p.id} task={p} adv={adv} advBusy={advBusy} onAdvance={()=>doAdvance(p)} onReassign={()=>setReassign(p)} onCancel={()=>cancelTask(p)}/>):<Empty text={t('noPlanYet')}/>}
   </section>
  </div>
  {sheet&&<PlanSheet group={sheet} date={date} onClose={()=>setSheet(null)}/>}
  {reassign&&<ReassignDialog task={reassign} onClose={()=>setReassign(null)}/>}
 </div>;
}
