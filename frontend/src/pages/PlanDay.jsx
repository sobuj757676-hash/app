import {useState,useEffect} from 'react';
import {useSearchParams,useNavigate} from 'react-router-dom';
import {CalendarDays,Check,Plus,Loader2} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import {api,label,today,errorText} from '../lib/api';
import {resolveStage,assigneeNames,PRIW,plannedUnitIds,completedUnitIds,remainingUnitIds,toggleCompletedIds,unitCount,isPlannedTask} from '../lib/planTasks';
import {UnitCheckboxes,StaleFlag,PlanProgress} from '../components/PlanUnitChips';
import {PageTitle,StatusBadge,Empty} from '../components/Common';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from '../components/ui/dialog';
import {Button} from '../components/ui/button';
import {AssigneeMultiSelect} from '../components/AssigneeMultiSelect';
import {toast} from 'sonner';

const PRIS=['low','medium','high','urgent'];
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
 const allChecked=ids.length>0&&ids.every(id=>done.includes(id));
 const live=!['done','cancelled'].includes(task.status);
 const b=data.blocks.find(x=>x.id===s.block_id);
 const [priBusy,setPriBusy]=useState(false);
 const setPri=async p=>{if(p===task.priority||priBusy)return;setPriBusy(true);
  try{await mutate('patch',`/tasks/${task.id}`,{priority:p});}catch{/* toasted by mutate */}finally{setPriBusy(false);}};
 return <div className="plan-card" data-testid={`plan-item-${task.id}`}>
  <div className="task-top"><StatusBadge value={task.status} id={`plan-status-${task.id}`}/>
   <label className="plan-pri"><span>{t('priority')}</span><select data-testid={`plan-priority-${task.id}`} value={task.priority} disabled={priBusy} onChange={e=>setPri(e.target.value)}>{PRIS.map(p=><option key={p} value={p}>{t(p)}</option>)}</select></label></div>
  <strong>{t('blk')} {b?.name||s.block||'?'} · L{s.level??'?'} — {resolveStage(data,s.stage_index,t)}</strong>
  {task.description&&<p className="task-desc">{task.description}</p>}
  <StaleFlag task={task} data={data} testPrefix={`plan-stale-${task.id}`}/>
  <UnitCheckboxes task={task} data={data} checked={done} busy={toggling} onToggle={id=>onToggle(task,id)} testPrefix={`plan-unit-${task.id}`}/>
  <div className="task-meta"><PlanProgress task={task} testId={`plan-progress-${task.id}`}/><span data-testid={`plan-scope-${task.id}`}>{planScopeText(task,data,t)}</span><span>{assigneeNames(task,t)}</span></div>
  {adv?.taskId===task.id&&<ul className="adv-report" data-testid={`plan-adv-report-${task.id}`}>{adv.results.map((r,i)=>{const u=data.units.find(x=>x.id===(r.unit_id||r.id));return <li key={i} className={r.error?'adv-err':''}>{u?`${t('blk')} ${u.block} · ${label(u)}`:(r.unit_label||r.unit_id||'—')} — {r.error?r.error:t('done')}</li>;})}</ul>}
  <div className="plan-item-actions">
   <button type="button" className="table-action" data-testid={`plan-reassign-${task.id}`} onClick={onReassign}>{t('reassign')}</button>
   {live&&<button type="button" className="table-action danger" data-testid={`plan-cancel-${task.id}`} onClick={onCancel}>{t('cancel')}</button>}
   {allChecked&&live&&<button type="button" className="advance-prompt" data-testid={`plan-advance-${task.id}`} disabled={advBusy===task.id} onClick={onAdvance}>{advBusy===task.id?<Loader2 className="spin" size={15}/>:<Check size={15}/>}{advBusy===task.id?t('advancing'):t('reviewAndAdvance')}</button>}
  </div>
 </div>;
}

// Unfinished work from earlier dates: one tap re-plans only the remaining
// units as a brand-new task on the selected date; the old task is untouched.
function CarryOver({date}){
 const {t}=useLanguage();const {data,pid,mutate}=useWorkspace();
 const [carried,setCarried]=useState([]),[busy,setBusy]=useState(null);
 const rows=(data.tasks||[]).filter(x=>isPlannedTask(x)&&x.plan_date<date&&!['done','cancelled'].includes(x.status))
  .map(x=>({x,remaining:remainingUnitIds(x)})).filter(r=>r.remaining.length>0&&!carried.includes(r.x.id));
 if(!rows.length)return null;
 const total=rows.reduce((n,r)=>n+r.remaining.length,0);
 const add=async r=>{
  if(busy)return;setBusy(r.x.id);
  try{
   await mutate('post',`/projects/${pid}/tasks`,{title:r.x.title,description:r.x.description||'',kind:'planned',scope:{...(r.x.scope||{}),unit_ids:r.remaining},plan_date:date,due_date:date,assignees:r.x.assignees||[],priority:r.x.priority||'medium'});
   setCarried(c=>[...c,r.x.id]);toast.success(t('saved'));
  }catch{/* toasted by mutate */}finally{setBusy(null);}
 };
 return <div className="plan-carryover" data-testid="plan-carryover" role="alert">
  <p className="carry-head">{t('carriedOver').replace('{n}',String(total))}</p>
  {rows.map(r=><div key={r.x.id} className="carry-row" data-testid={`carry-${r.x.id}`}>
   <span className="carry-text">{r.x.title} · {unitCount(r.remaining.length,t)}</span>
   <button type="button" className="table-action" data-testid={`carry-add-${r.x.id}`} disabled={busy===r.x.id} onClick={()=>add(r)}>{busy===r.x.id?<Loader2 className="spin" size={15}/>:null}{t('addToToday')}</button>
  </div>)}
 </div>;
}

export default function PlanDay(){
 const {t}=useLanguage();const {data,pid,mutate}=useWorkspace();const {user}=useAuth();
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
 const doAdvance=async task=>{
  const ids=plannedUnitIds(task);if(!ids.length||advBusy)return;setAdvBusy(task.id);setAdv(null);
  try{
   const {data:r}=await api.post(`/projects/${pid}/units/bulk-advance`,{unit_ids:ids,to_stage:(task.scope?.stage_index??0)+1});
   const results=r?.results||[];
   setAdv({taskId:task.id,results});
   const ok=results.filter(x=>!x.error).length;
   const msg=t('advDone').replace('{ok}',String(ok)).replace('{n}',String(ids.length));
   if(results.length&&ok===ids.length){await mutate('post',`/tasks/${task.id}/transition`,{status:'done'});toast.success(msg);}
   else toast(msg);
  }catch(e){toast.error(errorText(e,t));}finally{setAdvBusy(null);}
 };
 const cancelTask=async task=>{if(!window.confirm(t('cancelTaskConfirm')))return;try{await mutate('post',`/tasks/${task.id}/transition`,{status:'cancelled'});toast.success(t('saved'));}catch{/* toasted by mutate */}};
 if(!canPlan(user))return <div className="page-enter"><Empty text={t('noAccess')}/></div>;
 const nPlanned=plans.reduce((n,x)=>n+plannedUnitIds(x).length,0);
 const nDone=plans.reduce((n,x)=>n+completedUnitIds(x).length,0);
 return <div className="page-enter" data-testid="plan-day">
  <PageTitle title={t('dailyPlan')} subtitle={t('dailyPlanSub')}><label className="plan-date-field"><CalendarDays size={15}/><input type="date" data-testid="plan-day-date" value={date} max="2099-12-31" onChange={e=>e.target.value&&setDate(e.target.value)}/></label></PageTitle>
  <div className="plan-strip" data-testid="plan-strip" role="status">
   <span data-testid="plan-strip-planned"><b className="mono">{nPlanned}</b> {t('planPlanned')} {nPlanned===1?t('unitSing'):t('unitCount')}</span>
   <span data-testid="plan-strip-done"><b className="mono">{nDone}</b> {t('planDone')}</span>
   <span data-testid="plan-strip-remaining"><b className="mono">{nPlanned-nDone}</b> {t('planRemaining')}</span>
  </div>
  <CarryOver date={date}/>
  <button type="button" className="plan-add" data-testid="plan-add-work" onClick={()=>nav('/units?select=1')}><Plus size={17}/>{t('addWork')}</button>
  <section className="plan-cards" data-testid="plan-list">
   {plans.length?plans.map(p=><PlanCard key={p.id} task={p} onToggle={toggleUnit} toggling={toggling} onAdvance={()=>doAdvance(p)} advBusy={advBusy} adv={adv} onReassign={()=>setReassign(p)} onCancel={()=>cancelTask(p)}/>):<Empty text={t('noPlanYet')}/>}
  </section>
  {reassign&&<ReassignDialog task={reassign} onClose={()=>setReassign(null)}/>}
 </div>;
}
