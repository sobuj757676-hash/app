import {useState,useEffect} from 'react';
import {ListChecks,Plus,Search,Clock3} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import {api,label,today} from '../lib/api';
import {PageTitle,Metric,Action,StatusBadge,Empty,FormModal} from '../components/Common';
import {toast} from 'sonner';

const PRIS=['low','medium','high','urgent'];
const NEXT={todo:['in_progress','cancelled'],in_progress:['todo','done','cancelled'],done:[],cancelled:[]};
const canCreate=u=>['admin','manager','engineer','supervisor'].includes(u?.role);
const mayMove=(u,task,next)=>{
 if(['admin','manager','engineer','supervisor'].includes(u?.role))return true;
 return u?.role==='worker'&&task.assigned_to===u.id&&next!=='cancelled';
};

function TaskCard({task}){
 const {t}=useLanguage();const {data,mutate}=useWorkspace();const {user}=useAuth();const [busy,setBusy]=useState(false);
 const nexts=(NEXT[task.status]||[]).filter(s=>mayMove(user,task,s));
 const move=async s=>{setBusy(true);try{await mutate('post',`/tasks/${task.id}/transition`,{status:s});toast.success(t('saved'));}catch{}finally{setBusy(false);};};
 const overdue=task.due_date&&task.due_date<today()&&!['done','cancelled'].includes(task.status);
 return <div className={`task-card ${overdue?'overdue':''}`} data-testid={`task-${task.id}`}>
  <div className="task-top"><StatusBadge value={task.status} id={`task-status-${task.id}`}/><span className={`priority-tag ${task.priority}`}>{t(task.priority)}</span></div>
  <strong data-testid={`task-title-${task.id}`}>{task.title}</strong>
  {task.description&&<p className="task-desc">{task.description}</p>}
  <div className="task-meta"><span>{task.assigned_to_name||task.assigned_to}</span>{task.unit_label&&<span>{task.unit_label}</span>}{task.due_date&&<span className={`mono ${overdue?'overdue-text':''}`}><Clock3 size={12}/>{task.due_date}</span>}</div>
  {nexts.length>0&&<div className="transition-buttons">{nexts.map(s=><button key={s} type="button" className="table-action" data-testid={`task-to-${s}-${task.id}`} disabled={busy} onClick={()=>move(s)}>{t(s==='todo'?'todo':s)}</button>)}</div>}
 </div>;
}

export default function Tasks(){
 const {t}=useLanguage();const {data,mutate}=useWorkspace();const {user}=useAuth();
 const [priority,setPriority]=useState('all'),[q,setQ]=useState(''),[add,setAdd]=useState(false),[directory,setDirectory]=useState([]);
 useEffect(()=>{if(canCreate(user))api.get('/auth/directory').then(r=>setDirectory(r.data)).catch(()=>{});},[user]);
 const rows=data.tasks.filter(x=>(priority==='all'||x.priority===priority)&&`${x.title} ${x.assigned_to_name||''}`.toLowerCase().includes(q.toLowerCase()));
 const groups=['todo','in_progress','done','cancelled'].map(s=>({status:s,items:rows.filter(x=>x.status===s)}));
 const overdueCount=data.tasks.filter(x=>x.due_date&&x.due_date<today()&&!['done','cancelled'].includes(x.status)).length;
 const unitOptions=data.units.map(u=>({value:u.id,label:`Blk ${u.block} · ${label(u)}`}));
 return <div className="page-enter"><PageTitle title={t('tasks')} subtitle={t('tasksSub')}>{canCreate(user)&&<Action id="new-task" icon={Plus} onClick={()=>setAdd(true)}>{t('newTask')}</Action>}</PageTitle>
 <div className="metrics-grid three">
  <Metric id="tasks-open" title={t('todo')} value={data.tasks.filter(x=>x.status==='todo').length} sub={t('tasksSub')} icon={ListChecks} tone="blue"/>
  <Metric id="tasks-progress" title={t('in_progress')} value={data.tasks.filter(x=>x.status==='in_progress').length} sub={t('tasksSub')} icon={ListChecks} tone="amber"/>
  <Metric id="tasks-overdue" title={t('overdueTasks')} value={overdueCount} sub={t('dueSoon')} icon={Clock3} tone="red"/>
 </div>
 <div className="filter-bar"><div className="search-field"><Search size={16}/><input data-testid="task-search" placeholder={t('search')} value={q} onChange={e=>setQ(e.target.value)}/></div>
  <select data-testid="task-priority-filter" value={priority} onChange={e=>setPriority(e.target.value)}><option value="all">{t('allStatuses')}</option>{PRIS.map(p=><option key={p} value={p}>{t(p)}</option>)}</select></div>
 <div className="task-board">{groups.map(g=><section key={g.status} className="task-column" data-testid={`task-column-${g.status}`}><h3>{t(g.status)} <span>{g.items.length}</span></h3>{g.items.map(x=><TaskCard key={x.id} task={x}/>)}{!g.items.length&&<Empty text={t('noTasks')}/>}</section>)}</div>
 {add&&<FormModal open title={t('newTask')} onClose={()=>setAdd(false)}
  initial={{title:'',description:'',assigned_to:directory[0]?.id||'',priority:'medium',unit_id:'',due_date:''}}
  fields={[{name:'title',label:t('defectDetail'),maxLength:150},{name:'description',label:t('description'),type:'textarea',wide:true,required:false},{name:'assigned_to',label:t('assignee'),options:directory.map(u=>({value:u.id,label:`${u.name} · ${t(u.role)}`}))},{name:'priority',label:t('priority'),options:PRIS.map(p=>({value:p,label:t(p)}))},{name:'unit_id',label:t('unit'),required:false,options:[{value:'',label:'—'},...unitOptions]},{name:'due_date',label:t('dueDate'),type:'date',required:false}]}
  onSubmit={v=>mutate('post',`/projects/${data.project.id}/tasks`,{...v,unit_id:v.unit_id||null,due_date:v.due_date||null})}/>}
 </div>;
}
