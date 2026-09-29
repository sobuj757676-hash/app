import {useState,useEffect} from 'react';
import {CheckCircle2,Clock3,CalendarDays} from 'lucide-react';
import {useAuth} from '../lib/auth';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {api,today,percent,errorText} from '../lib/api';
import {PageTitle,Metric,ProgressBar} from '../components/Common';
import {toast} from 'sonner';

export default function WorkerHome(){
 const {t}=useLanguage();const {user}=useAuth();const {data,refresh}=useWorkspace();
 const [me,setMe]=useState(null),[status,setStatus]=useState('present'),[hours,setHours]=useState(8),[busy,setBusy]=useState(false);
 useEffect(()=>{api.get('/workers/me').then(r=>{setMe(r.data);if(r.data.today_attendance){setStatus(r.data.today_attendance.status);setHours(r.data.today_attendance.hours);}}).catch(()=>{});},[]);
 const marked=me?.today_attendance;
 const submit=async()=>{
  setBusy(true);
  try{const {data:d}=await api.put('/workers/me/attendance',{status,hours:Number(hours)||0});setMe(m=>({...m,today_attendance:d}));toast.success(t('attendanceMarked'));refresh();}
  catch(e){toast.error(errorText(e));}
  finally{setBusy(false);}
 };
 const pending=data.inspections.filter(i=>i.status==='pending').length;
 return <div className="page-enter worker-home" data-testid="worker-home">
  <PageTitle title={`${t('hello')}, ${user?.name?.split(' ')[0]||''}`} subtitle={`${t('today')}: ${today()}${me?.trade?` · ${me.trade}`:''}`}/>
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
 </div>;
}
