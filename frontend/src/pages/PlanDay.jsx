import {useState,useEffect} from 'react';
import {useSearchParams,useNavigate} from 'react-router-dom';
import {CalendarDays,Check,Plus,Loader2} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import {api,label,today,errorText} from '../lib/api';
import {resolveStage,assigneeNames,PRIW,plannedUnitIds,completedUnitIds,remainingUnitIds,toggleCompletedIds,unitCount,isPlannedTask,advancedUnitIds,pendingAdvanceGroups} from '../lib/planTasks';
import {UnitCheckboxes,StaleFlag,PlanProgress} from '../components/PlanUnitChips';
import {PageTitle,StatusBadge,Empty} from '../components/Common';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '../components/ui/dialog';
import {Button} from '../components/ui/button';
import {AssigneeMultiSelect} from '../components/AssigneeMultiSelect';
import {toast} from 'sonner';

const canPlan=u=>['admin','manager','engineer','supervisor'].includes(u?.role);

// "Blk 40A · L12 · Wire pulling — 5 units" for a planned task's scope (1 unit / N units grammar).
export const planScopeText=(task,data,t)=>{const s=task.scope||{};const b=data.blocks.find(x=>x.id===s.block_id);return `${t('blk')} ${b?.name||s.block||'?'} · L${s.level??'?'} · ${resolveStage(data,s.stage_index,t)} — ${unitCount((s.unit_ids||[]).length,t)}`;};

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

function PlanCard({task,onToggle,toggling,onAdvance,advBusy,adv,onReassign,onCancel}){
 const {t}=useLanguage();const {data,mutate}=useWorkspace();
 const s=task.scope||{};const ids=plannedUnitIds(task);const done=completedUnitIds(task);
 const advIds=advancedUnitIds(task,data);
 const checkedPending=done.filter(id=>!advIds.includes(id)).length;
 const live=!['done','cancelled'].includes(task.status);
 const b=data.blocks.find(x=>x.id===s.block_id);
 const [priBusy,setPriBusy]=useState(false);
 const [confirming,setConfirming]=useState(false);
 // Priority declutter (spec v2 Phase 2): no 4-way select on plan cards.
 // The tag renders only for high/urgent; urgency is toggled by one
 // explicit action (urgent <-> medium). Field and values are unchanged.
 const setUrgent=async on=>{if(priBusy)return;setPriBusy(true);
  try{await mutate('patch',`/tasks/${task.id}`,{priority:on?'urgent':'medium'});}catch{/* toasted by mutate */}finally{setPriBusy(false);}};
 return <div className="plan-card" data-testid={`plan-item-${task.id}`}>
  <div className="task-top"><StatusBadge value={task.status} id={`plan-status-${task.id}`}/>
   {['high','urgent'].includes(task.priority)&&<span className={`priority-tag ${task.priority}`} data-testid={`plan-priority-tag-${task.id}`}>{t(task.priority)}</span>}</div>
  <strong>{t('blk')} {b?.name||s.block||'?'} · L{s.level??'?'} — {resolveStage(data,s.stage_index,t)}</strong>
  {task.description&&<p className="task-desc">{task.description}</p>}
  <StaleFlag task={task} data={data} testPrefix={`plan-stale-${task.id}`}/>
  <UnitCheckboxes task={task} data={data} checked={done} busy={toggling} onToggle={id=>onToggle(task,id)} testPrefix={`plan-unit-${task.id}`} advancedIds={advIds}/>
  <div className="task-meta"><PlanProgress task={task} testId={`plan-progress-${task.id}`}/><span data-testid={`plan-scope-${task.id}`}>{planScopeText(task,data,t)}</span><span>{assigneeNames(task,t)}</span></div>
  {adv?.taskId===task.id&&<ul className="adv-report" data-testid={`plan-adv-report-${task.id}`}>{adv.results.map((r,i)=>{const u=data.units.find(x=>x.id===(r.unit_id||r.id));const ok=r.result==='advanced'||r.result==='already_advanced';const txt=r.result==='advanced'?t('done'):r.result==='already_advanced'?t('alreadyAdvanced'):r.result==='conflict_ahead'||r.result==='conflict_behind'?t('advConflict'):r.result==='blocked_rto'?t('advBlockedRto'):r.result==='blocked_defect'?`${t('advBlockedDefect')}${r.detail?`: ${r.detail}`:''}`:r.result==='blocked_tests'?t('advBlockedTests'):(r.detail||r.result||'—');return <li key={i} className={ok?'':'adv-err'}>{u?`${t('blk')} ${u.block} · ${label(u)}`:(r.unit_label||r.unit_id||'—')} — {txt}</li>;})}</ul>}
  <div className="plan-item-actions">
   <button type="button" className="table-action" data-testid={`plan-reassign-${task.id}`} onClick={onReassign}>{t('reassign')}</button>
   {live&&(task.priority==='urgent'
    ?<button type="button" className="table-action" data-testid={`plan-clear-urgent-${task.id}`} disabled={priBusy} onClick={()=>setUrgent(false)}>{t('clearUrgent')}</button>
    :<button type="button" className="table-action" data-testid={`plan-mark-urgent-${task.id}`} disabled={priBusy} onClick={()=>setUrgent(true)}>{t('markUrgent')}</button>)}
   {live&&(confirming
    ?<span className="confirm-inline" data-testid={`plan-cancel-confirm-${task.id}`}><span>{t('cancelTaskConfirm')}</span><button type="button" className="table-action danger" data-testid={`plan-cancel-yes-${task.id}`} onClick={()=>{setConfirming(false);onCancel();}}>{t('yes')}</button><button type="button" className="table-action" data-testid={`plan-cancel-no-${task.id}`} onClick={()=>setConfirming(false)}>{t('no')}</button></span>
    :<button type="button" className="table-action danger" data-testid={`plan-cancel-${task.id}`} onClick={()=>setConfirming(true)}>{t('cancel')}</button>)}
   {checkedPending>0&&task.status!=='cancelled'&&<button type="button" className="advance-prompt" data-testid={`plan-advance-${task.id}`} disabled={advBusy===task.id} onClick={onAdvance}>{advBusy===task.id?<Loader2 className="spin" size={15}/>:<Check size={15}/>}{advBusy===task.id?t('advancing'):t('advanceChecked').replace('{n}',String(checkedPending))}</button>}
  </div>
 </div>;
}

// Unfinished work from earlier dates (spec v2 §3): remaining is stage-aware
// (checked units belong to the advance flow; moved units are tracker truth).
// Add to Today re-plans the remaining units AND dismisses the source with
// the successor recorded, so the lineage closes exactly once. Skip dismisses
// the offer persistently — the units themselves stay in the Unit Tracker.
function CarryOver({date}){
 const {t}=useLanguage();const {data,pid,mutate}=useWorkspace();
 const [busy,setBusy]=useState(null);
 const rows=(data.tasks||[]).filter(x=>isPlannedTask(x)&&x.plan_date<date&&!['done','cancelled'].includes(x.status)&&!x.carryover_dismissed_at)
  .map(x=>({x,remaining:remainingUnitIds(x,data)})).filter(r=>r.remaining.length>0);
 if(!rows.length)return null;
 const total=rows.reduce((n,r)=>n+r.remaining.length,0);
 const add=async r=>{
  if(busy)return;setBusy(r.x.id);
  try{
   const created=await mutate('post',`/projects/${pid}/tasks`,{title:r.x.title,description:r.x.description||'',kind:'planned',scope:{...(r.x.scope||{}),unit_ids:r.remaining},plan_date:date,due_date:date,assignees:r.x.assignees||[],priority:r.x.priority||'medium'});
   if(created?.id)await mutate('post',`/tasks/${r.x.id}/dismiss-carryover`,{superseded_by_task_id:created.id});
   toast.success(t('saved'));
  }catch{/* toasted by mutate */}finally{setBusy(null);}
 };
 const skip=async r=>{
  if(busy)return;setBusy(r.x.id);
  try{await mutate('post',`/tasks/${r.x.id}/dismiss-carryover`,{});toast.success(t('saved'));}catch{/* toasted by mutate */}finally{setBusy(null);}
 };
 return <div className="plan-carryover" data-testid="plan-carryover" role="alert">
  <p className="carry-head">{t('carriedOver').replace('{n}',String(total))}</p>
  {rows.map(r=><div key={r.x.id} className="carry-row" data-testid={`carry-${r.x.id}`}>
   <span className="carry-text">{r.x.title} · {unitCount(r.remaining.length,t)}</span>
   <span className="carry-actions">
    <button type="button" className="table-action" data-testid={`carry-skip-${r.x.id}`} disabled={busy===r.x.id} onClick={()=>skip(r)}>{t('skip')}</button>
    <button type="button" className="table-action" data-testid={`carry-add-${r.x.id}`} disabled={busy===r.x.id} onClick={()=>add(r)}>{busy===r.x.id?<Loader2 className="spin" size={15}/>:null}{t('addToToday')}</button>
   </span>
  </div>)}
 </div>;
}

// Pending Advance (spec v2.1 §C + addendum): checked units that still need
// advancement or review, across ALL non-cancelled planned tasks — done tasks
// included. Derived live from the workspace payload; nothing here counts as
// project progress until the server actually advances the unit.
function PendingAdvance({onAdvanceTask,advBusy}){
 const {t}=useLanguage();const {data}=useWorkspace();const nav=useNavigate();
 const groups=pendingAdvanceGroups(data.tasks,data);
 if(!groups.length)return null;
 const total=groups.reduce((n,g)=>n+g.items.length,0);
 const reasonText=it=>it.reason==='ready'?t('paReady'):it.reason==='rto'?t('paRto'):it.reason==='defect'?`${t('paDefect')}${it.detail?`: ${it.detail}`:''}`:it.reason==='tests'?t('paTests'):t('paConflict');
 return <section className="pending-advance" data-testid="pending-advance">
  <div className="pending-head"><strong>{t('pendingAdvanceTitle')} · {total}</strong><span>{t('pendingAdvanceSub')}</span></div>
  {groups.map(({task,items})=><div key={task.id} className="pending-group" data-testid={`pending-group-${task.id}`}>
   <div className="pending-group-line"><span>{planScopeText(task,data,t)} · {assigneeNames(task,t)}</span>
    <button type="button" className="table-action" data-testid={`pending-advance-btn-${task.id}`} disabled={advBusy===task.id} onClick={()=>onAdvanceTask(task)}>{advBusy===task.id?<Loader2 className="spin" size={14}/>:null}{t('advanceNow')}</button></div>
   <ul className="pending-rows">{items.map(it=><li key={it.unit.id} data-testid={`pending-unit-${it.unit.id}`}>
    <button type="button" className="unit-link" onClick={()=>nav(`/units?unit=${it.unit.id}`)}>{`${t('blk')} ${it.unit.block} · ${label(it.unit)}`}</button>
    <span className={`pending-reason ${it.reason}`}>{reasonText(it)}</span>
   </li>)}</ul>
  </div>)}
 </section>;
}

export default function PlanDay(){
 const {t}=useLanguage();const {data,pid,mutate,refresh}=useWorkspace();const {user}=useAuth();
 const nav=useNavigate();
 const [params,setParams]=useSearchParams();
 const date=params.get('date')||today();
 const setDate=d=>setParams(p=>{const n=new URLSearchParams(p);d===today()?n.delete('date'):n.set('date',d);return n;});
 const [reassign,setReassign]=useState(null);
 const [adv,setAdv]=useState(null),[advBusy,setAdvBusy]=useState(null);
 const [toggling,setToggling]=useState(null);
 const plans=(data.tasks||[]).filter(x=>isPlannedTask(x)&&x.plan_date===date).sort((a,b)=>PRIW[a.priority]-PRIW[b.priority]||(a.created_at||'').localeCompare(b.created_at||''));
 const toggleUnit=async(task,id)=>{if(toggling)return;setToggling(task.id);
  try{await mutate('patch',`/tasks/${task.id}`,{completed_unit_ids:toggleCompletedIds(task,id)});}catch{/* toasted by mutate */}finally{setToggling(null);}};
 // Checked-unit advance (spec v2 §2 / v2.1 §B): the server classifies each
 // checked unit against its live stage; only eligible units move, one stage.
 const advanceOne=async task=>{const {data:r}=await api.post(`/projects/${pid}/tasks/${task.id}/advance`,{});return r;};
 const doAdvance=async task=>{
  if(advBusy)return;setAdvBusy(task.id);setAdv(null);
  try{
   const r=await advanceOne(task);
   const results=r?.results||[];
   setAdv({taskId:task.id,results});
   const ok=(r?.advanced||0)+(r?.already_advanced||0);
   const msg=t('advDone').replace('{ok}',String(ok)).replace('{n}',String(results.length));
   if(r?.all_advanced&&task.status!=='done'){await mutate('post',`/tasks/${task.id}/transition`,{status:'done'});toast.success(msg);}
   else{await refresh();toast(msg);}
  }catch(e){toast.error(errorText(e,t));}finally{setAdvBusy(null);}
 };
 const [advAllBusy,setAdvAllBusy]=useState(false);
 const advanceable=plans.filter(p=>p.status!=='cancelled')
  .map(p=>({p,n:completedUnitIds(p).filter(id=>!advancedUnitIds(p,data).includes(id)).length})).filter(x=>x.n>0);
 const advAllTotal=advanceable.reduce((n,x)=>n+x.n,0);
 const doAdvanceAll=async()=>{
  if(advAllBusy||!advanceable.length)return;setAdvAllBusy(true);
  let ok=0;
  try{
   for(const {p} of advanceable){
    const r=await advanceOne(p);
    ok+=(r?.advanced||0)+(r?.already_advanced||0);
    if(r?.all_advanced&&p.status!=='done')await mutate('post',`/tasks/${p.id}/transition`,{status:'done'});
   }
   await refresh();
   toast(t('advDone').replace('{ok}',String(ok)).replace('{n}',String(advAllTotal)));
  }catch(e){toast.error(errorText(e,t));}finally{setAdvAllBusy(false);}
 };
 const pendingTotal=pendingAdvanceGroups(data.tasks,data).reduce((n,g)=>n+g.items.length,0);
 const cancelTask=async task=>{try{await mutate('post',`/tasks/${task.id}/transition`,{status:'cancelled'});toast.success(t('saved'));}catch{/* toasted by mutate */}};
 if(!canPlan(user))return <div className="page-enter"><Empty text={t('noAccess')}/></div>;
 const nPlanned=plans.reduce((n,x)=>n+plannedUnitIds(x).length,0);
 const nDone=plans.reduce((n,x)=>n+completedUnitIds(x).length,0);
 return <div className="page-enter" data-testid="plan-day">
  <PageTitle title={t('dailyPlan')} subtitle={t('dailyPlanSub')}><label className="plan-date-field"><CalendarDays size={15}/><input type="date" data-testid="plan-day-date" value={date} max="2099-12-31" onChange={e=>e.target.value&&setDate(e.target.value)}/></label></PageTitle>
  <div className="plan-strip" data-testid="plan-strip" role="status">
   <span data-testid="plan-strip-planned"><b className="mono">{nPlanned}</b> {t('planPlanned')} {nPlanned===1?t('unitSing'):t('unitCount')}</span>
   <span data-testid="plan-strip-done"><b className="mono">{nDone}</b> {t('planDone')}</span>
   <span data-testid="plan-strip-remaining"><b className="mono">{nPlanned-nDone}</b> {t('planRemaining')}</span>
   {pendingTotal>0&&<span data-testid="plan-strip-pending" className="pending-count"><b className="mono">{pendingTotal}</b> {t('pendingAdvanceTitle')}</span>}
  </div>
  <PendingAdvance onAdvanceTask={doAdvance} advBusy={advBusy}/>
  <CarryOver date={date}/>
  <button type="button" className="plan-add" data-testid="plan-add-work" onClick={()=>nav('/units?select=1')}><Plus size={17}/>{t('addWork')}</button>
  <section className="plan-cards" data-testid="plan-list">
   {plans.length?plans.map(p=><PlanCard key={p.id} task={p} onToggle={toggleUnit} toggling={toggling} onAdvance={()=>doAdvance(p)} advBusy={advBusy} adv={adv} onReassign={()=>setReassign(p)} onCancel={()=>cancelTask(p)}/>):<Empty text={t('noPlanYet')}/>}
  </section>
  {reassign&&<ReassignDialog task={reassign} onClose={()=>setReassign(null)}/>}
  {advAllTotal>0&&<div className="plan-advance-bar" data-testid="plan-advance-bar">
   <span>{t('advanceAllChecked').replace('{n}',String(advAllTotal))}</span>
   <button type="button" className="advance-bar-btn" data-testid="plan-advance-all" disabled={advAllBusy} onClick={doAdvanceAll}>{advAllBusy?<Loader2 className="spin" size={15}/>:<Check size={15}/>}{t('advanceNow')}</button>
  </div>}
 </div>;
}
