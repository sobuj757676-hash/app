import {useState,useEffect} from 'react';
import {Loader2} from 'lucide-react';
import {Dialog,DialogContent,DialogHeader,DialogTitle,DialogDescription} from './ui/dialog';
import {Button} from './ui/button';
import {Input} from './ui/input';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {api,label} from '../lib/api';
import {toast} from 'sonner';

const PRIS=['low','medium','high','urgent'];

/** Shared task create modal.
 *  Props: open, onClose, defectId? (locked follow-up flow from a defect),
 *  requireAssignee? (default true; false in follow-up flow).
 *  Posts to /defects/{id}/tasks when defectId is set, else /projects/{pid}/tasks. */
export function TaskModal({open,onClose,defectId=null,requireAssignee=true}){
 const {t}=useLanguage();const {data,mutate}=useWorkspace();
 const [directory,setDirectory]=useState([]);
 const [v,setV]=useState({title:'',description:'',assigned_to:'',priority:'medium',unit_id:'',defect_id:'',due_date:''});
 const [defectQ,setDefectQ]=useState('');
 const [busy,setBusy]=useState(false);
 useEffect(()=>{if(open){setV({title:'',description:'',assigned_to:'',priority:'medium',unit_id:'',defect_id:'',due_date:''});setDefectQ('');api.get('/auth/directory').then(r=>setDirectory(r.data)).catch(()=>{});}},[open]);
 useEffect(()=>{if(open&&directory.length)setV(p=>({...p,assigned_to:p.assigned_to||directory[0].id}));},[open,directory]);
 const set=(k,val)=>setV(p=>({...p,[k]:val}));
 const lockedDefect=defectId?data?.defects.find(d=>d.id===defectId):null;
 const defectOptions=(data?.defects||[]).filter(d=>`${d.title} ${d.status} ${d.severity}`.toLowerCase().includes(defectQ.toLowerCase()));
 const unitOptions=(data?.units||[]).map(u=>({value:u.id,label:`Blk ${u.block} · ${label(u)}`}));
 const submit=async e=>{
  e.preventDefault();if(busy)return;setBusy(true);
  try{
   if(defectId){
    await mutate('post',`/defects/${defectId}/tasks`,{title:v.title,description:v.description||null,assigned_to:v.assigned_to||null,priority:v.priority,due_date:v.due_date||null});
   }else{
    await mutate('post',`/projects/${data.project.id}/tasks`,{title:v.title,description:v.description||null,unit_id:v.unit_id||null,defect_id:v.defect_id||null,assigned_to:v.assigned_to,priority:v.priority,due_date:v.due_date||null});
   }
   toast.success(t('saved'));onClose();
  }catch{/* toasted by mutate */}finally{setBusy(false);}
 };
 const fld='field-input';
 return <Dialog open={open} onOpenChange={x=>!x&&onClose()}><DialogContent className="form-modal" data-testid="task-modal">
  <DialogHeader><DialogTitle data-testid="task-modal-title">{defectId?t('followupTask'):t('newTask')}</DialogTitle><DialogDescription className="sr-only">{t('newTask')}</DialogDescription></DialogHeader>
  <form onSubmit={submit} data-testid="task-modal-form"><div className="form-fields">
   <label className="wide">{t('defectDetail')}<Input data-testid="task-title" className={fld} required maxLength={150} value={v.title} onChange={e=>set('title',e.target.value)}/></label>
   <label className="wide">{t('description')}<textarea data-testid="task-description" rows={3} maxLength={2000} value={v.description} onChange={e=>set('description',e.target.value)}/></label>
   <label>{t('assignee')}<select data-testid="task-assignee" className={fld} required={requireAssignee} value={v.assigned_to} onChange={e=>set('assigned_to',e.target.value)}>
    {!v.assigned_to&&<option value="">—</option>}{directory.map(u=><option key={u.id} value={u.id}>{u.name} · {t(u.role)}</option>)}</select></label>
   <label>{t('priority')}<select data-testid="task-priority" className={fld} value={v.priority} onChange={e=>set('priority',e.target.value)}>{PRIS.map(p=><option key={p} value={p}>{t(p)}</option>)}</select></label>
   {defectId
    ?<div className="wide"><span className="field-label">{t('linkToDefect')}</span><span className={`severity-tag ${lockedDefect?.severity||'minor'}`} data-testid="task-locked-defect">{lockedDefect?.title||defectId}</span></div>
    :<div className="wide"><span className="field-label">{t('linkToDefect')}</span>
     <Input data-testid="task-defect-search" className={fld} placeholder={t('search')} value={defectQ} onChange={e=>setDefectQ(e.target.value)}/>
     <select data-testid="task-defect" className={fld} value={v.defect_id} onChange={e=>set('defect_id',e.target.value)}>
      <option value="">—</option>{defectOptions.map(d=><option key={d.id} value={d.id}>{d.title} · {t(d.status)} · {t(d.severity)}</option>)}
     </select></div>}
   {!defectId&&<label>{t('unit')}<select data-testid="task-unit" className={fld} value={v.unit_id} onChange={e=>set('unit_id',e.target.value)}>
    <option value="">—</option>{unitOptions.map(o=><option key={o.value} value={o.value}>{o.label}</option>)}</select></label>}
   <label>{t('dueDate')}<Input data-testid="task-due-date" className={fld} type="date" value={v.due_date} onChange={e=>set('due_date',e.target.value)}/></label>
  </div><div className="form-footer">
   <Button type="button" variant="outline" data-testid="task-cancel" onClick={onClose}>{t('cancel')}</Button>
   <Button type="submit" className="action" disabled={busy} data-testid="task-submit">{busy&&<Loader2 className="spin" size={15}/>} {t('save')}</Button>
  </div></form>
 </DialogContent></Dialog>;
}
