import {useState,useEffect} from 'react';
import {Save,Plus,Trash2,ArrowUp,ArrowDown} from 'lucide-react';
import {useWorkspace} from '../../lib/store';
import {useLanguage} from '../../lib/i18n';
import {useAuth,canProjects} from '../../lib/auth';
import {Action} from '../../components/Common';
import {api,errorText} from '../../lib/api';
import {toast} from 'sonner';
import {SubHeader} from './shared';

export default function RtoChecklist(){
 const {t}=useLanguage();const {data,pid,refresh}=useWorkspace();const {user}=useAuth();const proj=canProjects(user);
 const [checklist,setChecklist]=useState(data.project.rto_checklist_template||[]),[newItem,setNewItem]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>setChecklist(data.project.rto_checklist_template||[]),[data.project]);
 const moveItem=(i,dir)=>{const j=i+dir;if(j<0||j>=checklist.length)return;const next=[...checklist];[next[i],next[j]]=[next[j],next[i]];setChecklist(next);};
 const save=async()=>{if(!proj||busy)return;setBusy(true);try{await api.put(`/projects/${pid}/settings/rto-checklist`,{template:checklist});await refresh();toast.success(t('checklistUpdated'));}catch(e){toast.error(errorText(e));}finally{setBusy(false);}};
 return <div className="page-enter">
  <SubHeader title={t('rtoChecklist')} subtitle={t('rtoChecklistSub')}/>
  <div data-testid="rto-checklist-screen">
   <div className="checklist-editor">{checklist.map((item,i)=><div key={i} className="checklist-row compact" data-testid={`checklist-item-${i}`}>
    <span className="checklist-num">{i+1}</span><span className="checklist-text">{item}</span>
    {proj&&<span className="checklist-actions">
     <button type="button" className="icon-button" data-testid={`checklist-up-${i}`} disabled={i===0} onClick={()=>moveItem(i,-1)}><ArrowUp size={15}/></button>
     <button type="button" className="icon-button" data-testid={`checklist-down-${i}`} disabled={i===checklist.length-1} onClick={()=>moveItem(i,1)}><ArrowDown size={15}/></button>
     <button type="button" className="icon-button" data-testid={`checklist-del-${i}`} onClick={()=>setChecklist(checklist.filter((_,j)=>j!==i))}><Trash2 size={15}/></button>
    </span>}
   </div>)}</div>
   {proj&&<>
    <div className="checklist-add"><input data-testid="checklist-new-item" placeholder={t('checklistItem')} value={newItem} maxLength={200} onChange={e=>setNewItem(e.target.value)}/><Action id="checklist-add" icon={Plus} disabled={!newItem.trim()} onClick={()=>{setChecklist([...checklist,newItem.trim()]);setNewItem('');}}>{t('addChecklistItem')}</Action></div>
    <Action id="checklist-save" icon={Save} disabled={busy||!checklist.length} onClick={save}>{t('save')}</Action>
   </>}
  </div>
 </div>;
}
