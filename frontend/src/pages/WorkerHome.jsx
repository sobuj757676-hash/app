import {useState,useEffect} from 'react';
import {CheckCircle2,Clock3,CalendarDays,ListChecks,OctagonAlert} from 'lucide-react';
import {useAuth} from '../lib/auth';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {api,today,percent,errorText,fmtDate} from '../lib/api';
import {PageTitle,Metric,ProgressBar,StatusBadge,Empty} from '../components/Common';
import {DefectDrawer} from '../components/DefectDrawer';
import {DefectChip,mayMove} from './Tasks';
import {toast} from 'sonner';

const TASK_NEXT={todo:['in_progress'],in_progress:['todo','done'],done:[],cancelled:[]};
const DEFECT_NEXT={assigned:['in_progress'],in_progress:['rectified']};
const LIVE_DEFECT=['open','assigned','in_progress','rectified'];

export default function WorkerHome(){
 const {t,lang}=useLanguage();const {user}=useAuth();const {data,refresh,mutate}=useWorkspace();
 const [me,setMe]=useState(null),[status,setStatus]=useState('present'),[hours,setHours]=useState(8),[busy,setBusy]=useState(false);
 const [filter,setFilter]=useState('all'),[defectId,setDefectId]=useState(null);
 const [moveBusy,setMoveBusy]=useState([]);
 useEffect(()=>{api.get('/workers/me').then(r=>{setMe(r.data);if(r.data.today_attendance){setStatus(r.data.today_attendance.status);setHours(r.data.today_attendance.hours);}}).catch(()=>{});},[]);
 const marked=me?.today_attendance;
 const submit=async()=>{
  setBusy(true);
  try{const {data:d}=await api.put('/workers/me/attendance',{status,hours:Number(hours)||0});setMe(m=>({...m,today_attendance:d}));toast.success(t('attendanceMarked'));refresh();}
  catch(e){toast.error(errorText(e));}
  finally{setBusy(false);}
 };
 const moveTask=async(task,next)=>{
  setMoveBusy(b=>b.includes(task.id)?b:[...b,task.id]);
  try{await mutate('post',`/tasks/${task.id}/transition`,{status:next});toast.success(t('saved'));}
  catch{/* toasted by mutate */}
  finally{setMoveBusy(b=>b.filter(id=>id!==task.id));}
 };
 const moveDefect=async(defect,next)=>{
  try{await mutate('post',`/defects/${defect.id}/transition`,{status:next});toast.success(t('saved'));}
  catch{/* toasted by mutate */}
 };
 const myTasks=(data.tasks||[]).filter(x=>x.assigned_to===user?.id&&!['done','cancelled'].includes(x.status)).map(x=>({...x,kind:'task'}));
 const myDefects=(data.defects||[]).filter(d=>d.assigned_to===user?.id&&LIVE_DEFECT.includes(d.status)).map(d=>({...d,kind:'defect'}));
 const urgency=i=>{
  const live=i.kind==='task'?!['done','cancelled'].includes(i.status):LIVE_DEFECT.includes(i.status);
  const overdue=i.due_date&&i.due_date<today()&&live;
  if(overdue)return 0;
  if(i.kind==='defect'&&i.severity==='critical'&&live)return 0;
  return 1;
 };
 const byDue=(a,b)=>{
  if(!!a.due_date!==!!b.due_date)return a.due_date? -1:1;
  if(a.due_date&&b.due_date&&a.due_date!==b.due_date)return a.due_date<b.due_date?-1:1;
  return (b.created_at||'').localeCompare(a.created_at||'');
 };
 const work=[...myTasks,...myDefects]
  .filter(i=>filter==='all'||i.kind===filter)
  .sort((a,b)=>urgency(a)-urgency(b)||byDue(a,b));
 const pending=data.inspections.filter(i=>i.status==='pending').length;
 return <div className="page-enter worker-home" data-testid="worker-home">
  <PageTitle title={`${t('hello')}, ${user?.name?.split(' ')[0]||''}`} subtitle={`${t('today')}: ${fmtDate(new Date(),lang)}${me?.trade?` · ${me.trade}`:''}`}/>
  <section className="worker-attendance" data-testid="worker-attendance-card">
   <h2><CalendarDays size={18}/>{t('myAttendance')}</h2>
   {marked&&<div className="attendance-marked" data-testid="attendance-today-status"><CheckCircle2 size={17}/>{t(marked.status)} · {marked.hours} {t('hours')}</div>}
   <div className="attendance-options">{['present','absent','leave'].map(s=><button key={s} type="button" data-testid={`attend-${s}`} className={status===s?'active':''} onClick={()=>setStatus(s)}>{t(s)}</button>)}</div>
   {status==='present'&&<label className="hours-input">{t('hours')}<input data-testid="attend-hours" type="number" min={0} max={16} value={hours} onChange={e=>setHours(e.target.value)}/></label>}
   <button className="attend-submit" data-testid="attend-submit" disabled={busy} onClick={submit}>{t('markAttendance')}</button>
  </section>
  <section className="worker-site">
   <h2>{t('siteToday')}</h2>
   <div className="metrics-grid two">
    <Metric id="worker-progress" title={t('overallProgress')} value={`${percent(data.units)}%`} sub={t('stagesComplete')} icon={Clock3}/>
    <Metric id="worker-rto" title={t('pendingRto')} value={pending} sub={t('awaitingInspection')} icon={CheckCircle2} tone="amber"/>
   </div>
   <div className="worker-progress"><ProgressBar id="worker-progress-bar" value={percent(data.units)}/></div>
  </section>
  <section className="worker-tasks" data-testid="worker-work">
   <h2><ListChecks size={18}/>{t('myWork')}</h2>
   <p className="section-sub">{t('myWorkSub')}</p>
   <div className="filter-chips" data-testid="work-filter">
    {[['all',t('all')],['task',t('tasks')],['defect',t('defects')]].map(([k,label])=><button key={k} type="button" data-testid={`work-filter-${k}`} className={filter===k?'active':''} onClick={()=>setFilter(k)}>{label}</button>)}
   </div>
   {work.length?work.map(i=>i.kind==='task'
    ?<div key={i.id} className="worker-task" data-testid={`worker-task-${i.id}`}>
      <div><strong>{i.title}</strong><small>{i.unit_label||''}{i.due_date?` · ${i.due_date}`:''}</small></div>
      {i.defect&&<DefectChip defect={i.defect} onOpen={()=>setDefectId(i.defect.id)}/>}
      <StatusBadge value={i.status} id={`worker-task-status-${i.id}`}/>
      <div className="worker-task-actions">{(TASK_NEXT[i.status]||[]).filter(s=>mayMove(user,i,s)).map(s=><button key={s} type="button" data-testid={`worker-task-${s}-${i.id}`} className="attend-submit small" disabled={moveBusy.includes(i.id)} onClick={()=>moveTask(i,s)}>{t(s==='todo'?'todo':s)}</button>)}</div>
     </div>
    :<div key={i.id} className="worker-task worker-defect" data-testid={`worker-defect-${i.id}`}>
      <div><strong><OctagonAlert size={14}/> {i.title}</strong><small>{i.block?`Blk ${i.block} · #${String(i.level).padStart(2,'0')}-${i.number}`:''}{i.due_date?` · ${i.due_date}`:''}</small></div>
      <span className={`severity-tag ${i.severity}`}>{t(i.severity)}</span>
      <StatusBadge value={i.status} id={`worker-defect-status-${i.id}`}/>
      <div className="worker-task-actions">
       {(DEFECT_NEXT[i.status]||[]).map(s=><button key={s} type="button" data-testid={`worker-defect-${s}-${i.id}`} className="attend-submit small" onClick={()=>moveDefect(i,s)}>{t('moveTo')}: {t(s)}</button>)}
       <button type="button" data-testid={`worker-defect-open-${i.id}`} className="attend-submit small ghost" onClick={()=>setDefectId(i.id)}>{t('viewDefect')}</button>
      </div>
     </div>
   ):<Empty text={t('noWork')}/>}
  </section>
  {defectId&&<DefectDrawer defectId={defectId} onClose={()=>setDefectId(null)}/>}
 </div>;
}
