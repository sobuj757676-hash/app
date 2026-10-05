import {useState,useEffect} from 'react';
import {UserCheck,History,Camera,ListChecks,Plus} from 'lucide-react';
import {Sheet,SheetContent,SheetHeader,SheetTitle,SheetDescription} from './ui/sheet';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {useAuth} from '../lib/auth';
import {api,errorText,label,fmtDateTime} from '../lib/api';
import {StatusBadge,Action,Empty} from './Common';
import {PhotoUpload,PhotoGallery} from './Photos';
import {TaskModal} from './TaskModal';
import {toast} from 'sonner';
import {useNavigate} from 'react-router-dom';
import '../fixes-c.css';

const TRANSITIONS={open:['assigned','cancelled'],assigned:['in_progress','open','cancelled'],in_progress:['rectified','assigned','cancelled'],rectified:['verified','in_progress','cancelled'],verified:[],cancelled:[]};
const mayTransition=(user,defect,next)=>{
 const role=user?.role;
 if(['admin','manager','engineer'].includes(role))return true;
 if(role==='supervisor')return next!=='verified';
 if(role==='worker')return defect.assigned_to===user.id&&((defect.status==='assigned'&&next==='in_progress')||(defect.status==='in_progress'&&next==='rectified'));
 return false;
};

export const DefectDrawer=({defectId,onClose})=>{
 const {t,lang}=useLanguage();const {data,mutate,setSelectedUnit}=useWorkspace();const {user}=useAuth();const navigate=useNavigate();
 const [directory,setDirectory]=useState([]),[assignee,setAssignee]=useState(''),[busy,setBusy]=useState(false),[note,setNote]=useState(''),[photoTick,setPhotoTick]=useState(0);
 const [linkedTasks,setLinkedTasks]=useState([]),[taskModal,setTaskModal]=useState(false),[linkError,setLinkError]=useState(false);
 const defect=data?.defects.find(d=>d.id===defectId);
 useEffect(()=>{setNote('');setAssignee('');},[defectId]);
 useEffect(()=>{if(defect&&['admin','manager','engineer','supervisor'].includes(user?.role))api.get('/auth/directory').then(r=>setDirectory(r.data)).catch(()=>{});},[defect,user]);
 const loadLinked=()=>{if(!defect)return;setLinkError(false);api.get(`/defects/${defect.id}/tasks`).then(r=>setLinkedTasks(r.data)).catch(()=>setLinkError(true));};
 // eslint-disable-next-line react-hooks/exhaustive-deps
 useEffect(()=>{setLinkedTasks([]);loadLinked();},[defect]);
 if(!defect)return null;
 const unit=defect.unit_id?data.units.find(u=>u.id===defect.unit_id):null;
 const canAssign=['admin','manager','engineer','supervisor'].includes(user?.role);
 const nexts=(TRANSITIONS[defect.status]||[]).filter(s=>mayTransition(user,defect,s));
 const assigneeName=defect.assigned_to_name||directory.find(u=>u.id===defect.assigned_to)?.name;
 const doTransition=async s=>{
  setBusy(true);
  try{await mutate('post',`/defects/${defect.id}/transition`,{status:s,note});setNote('');toast.success(t('saved'));}
  catch{/* error toasted by mutate */}finally{setBusy(false);}
 };
 const doAssign=async()=>{
  if(!assignee)return;setBusy(true);
  try{await mutate('post',`/defects/${defect.id}/assign`,{assignee_id:assignee});setAssignee('');toast.success(t('saved'));}
  catch{}finally{setBusy(false);}
 };
 return <><Sheet open={!!defect} onOpenChange={v=>!v&&onClose()}><SheetContent className="unit-drawer defect-drawer" data-testid="defect-drawer">
  <SheetHeader>
   <div className="drawer-eyebrow">{defect.block?`${t('blk')} ${defect.block} · #${String(defect.level).padStart(2,'0')}-${defect.number}`:t('defects')}</div>
   <SheetTitle data-testid="defect-drawer-title">{defect.title}</SheetTitle>
   <SheetDescription>{t(defect.category)} · {t(defect.severity)}</SheetDescription>
  </SheetHeader>
  <div className="drawer-status"><StatusBadge id="defect-drawer-status" value={defect.status}/><span className={`severity-tag ${defect.severity}`} data-testid="defect-severity">{t(defect.severity)}</span></div>
  {defect.description&&<p className="defect-desc" data-testid="defect-description">{defect.description}</p>}
  <dl className="defect-meta">
   <div><dt>{t('reportedBy')}</dt><dd data-testid="defect-reporter">{defect.reported_by?.name}</dd></div>
   <div><dt>{t('assignee')}</dt><dd data-testid="defect-assignee">{assigneeName||defect.assigned_to||t('unassigned')}</dd></div>
   {defect.due_date&&<div><dt>{t('dueDate')}</dt><dd className="mono">{defect.due_date}</dd></div>}
   {unit&&<div><dt>{t('unit')}</dt><dd><button className="unit-link" data-testid="defect-unit-link" onClick={()=>{onClose();setSelectedUnit(unit.id);}}>{label(unit)}</button></dd></div>}
  </dl>
  {canAssign&&<div className="defect-assign" data-testid="defect-assign-box">
   <label className="field-label">{t('assignTo')}
    <select data-testid="defect-assignee-select" value={assignee} onChange={e=>setAssignee(e.target.value)}>
     <option value="">—</option>{directory.map(u=><option key={u.id} value={u.id}>{u.name} · {t(u.role)}</option>)}
    </select></label>
   <Action id="defect-assign-submit" icon={UserCheck} disabled={!assignee||busy} onClick={doAssign}>{t('assign')}</Action>
  </div>}
  {nexts.length>0&&<div className="defect-transitions" data-testid="defect-transitions">
   <label className="field-label">{t('note')}<textarea data-testid="defect-transition-note" rows={2} value={note} onChange={e=>setNote(e.target.value)} placeholder={t('moveTo')}/></label>
   <div className="transition-buttons">{nexts.map(s=><Action key={s} id={`defect-to-${s}`} secondary={s!=='verified'} disabled={busy} onClick={()=>doTransition(s)}>{t('moveTo')}: {t(s)}</Action>)}</div>
  </div>}
  <div className="drawer-section"><h3><Camera size={16}/>{t('photos')}</h3>
   <PhotoGallery entityType="defect" entityId={defect.id} refreshKey={photoTick} canDelete={['admin','manager'].includes(user?.role)} id="defect-photos"/>
   {['admin','manager','engineer','supervisor'].includes(user?.role)||defect.assigned_to===user?.id||defect.reported_by?.id===user?.id
    ?<PhotoUpload entityType="defect" entityId={defect.id} onUploaded={()=>setPhotoTick(k=>k+1)} id="defect-photo-upload"/>
    :null}
  </div>
  <div className="drawer-section" data-testid="defect-linked-tasks"><h3><ListChecks size={16}/>{t('linkedTasks')} <span>{linkedTasks.length}</span></h3>
   {linkError
    ?<div className="inline-error" data-testid="linked-tasks-error"><span>{t('linkedTasksLoadFailed')}</span><button type="button" className="text-link" onClick={loadLinked}>{t('retry')}</button></div>
    :linkedTasks.length?linkedTasks.map(x=><button key={x.id} type="button" className="linked-task-row" data-testid={`linked-task-${x.id}`} onClick={()=>{onClose();navigate(`/tasks?open=${x.id}`);}}>
    <strong>{x.title}</strong><span className="linked-task-meta"><StatusBadge value={x.status} id={`linked-task-status-${x.id}`}/><small>{x.assigned_to_name||x.assigned_to||t('unassigned')}</small></span>
   </button>):<Empty text={t('noTasks')}/>}
   {canAssign&&<Action id="defect-followup-task" icon={Plus} secondary onClick={()=>setTaskModal(true)}>{t('followupTask')}</Action>}
  </div>
  <div className="drawer-section"><h3><History size={16}/>{t('defectHistory')}</h3>
   <div className="unit-history">{defect.history?.length?defect.history.slice().reverse().map((h,i)=><div key={i} data-testid={`defect-history-${i}`}><span className="history-dot"/><strong>{t(h.status)}</strong><p>{h.note||'—'}</p><small>{h.by_name}</small><time>{fmtDateTime(h.at,lang)}</time></div>):<Empty text={t('noHistory')}/>}</div>
  </div>
 </SheetContent></Sheet>
 {taskModal&&<TaskModal open defectId={defect.id} requireAssignee={false} onClose={()=>{setTaskModal(false);loadLinked();}}/>}
 </>;
};
