import {useState,useEffect} from 'react';
import {Save,Plus,Trash2,ArrowUp,ArrowDown,ShieldCheck} from 'lucide-react';
import {useWorkspace} from '../../lib/store';
import {useLanguage} from '../../lib/i18n';
import {useAuth,canProjects} from '../../lib/auth';
import {Action} from '../../components/Common';
import {api,errorText,stageName,DEFAULT_STAGES} from '../../lib/api';
import {toast} from 'sonner';
import {SubHeader} from './shared';

const fresh=()=>DEFAULT_STAGES.map(s=>({...s}));

export default function WorkflowStages(){
 const {t}=useLanguage();const {data,pid,refresh}=useWorkspace();const {user}=useAuth();const proj=canProjects(user);
 const [stages,setStages]=useState(data.project.workflow_stages?.length?data.project.workflow_stages.map(s=>({...s})):fresh()),[busy,setBusy]=useState(false);
 const units=data.units||[];
 useEffect(()=>setStages(data.project.workflow_stages?.length?data.project.workflow_stages.map(s=>({...s})):fresh()),[data.project,pid]);
 const started=units.filter(u=>u.stage>0).length;
 // Renaming detaches a built-in from its translation key: the typed name shows in every language.
 const rename=(i,name)=>setStages(stages.map((s,j)=>j===i?{...s,name,name_key:null}:s));
 const toggleRto=i=>setStages(stages.map((s,j)=>j===i?{...s,requires_rto:!s.requires_rto}:s));
 const move=(i,dir)=>{const j=i+dir;if(j<0||j>=stages.length)return;if(started&&!window.confirm(t('reorderStagesConfirm').replace('{count}',started)))return;const next=[...stages];[next[i],next[j]]=[next[j],next[i]];setStages(next);};
 const del=i=>{const n=units.filter(u=>u.stage>=i).length;if(n>0){toast.error(t('deleteStageBlocked').replace('{count}',n));return;}setStages(stages.filter((_,j)=>j!==i));};
 const add=()=>setStages([...stages,{id:`stg${Date.now().toString(36)}`,name:'',name_key:null,requires_rto:false}]);
 const save=async()=>{if(!proj||busy)return;if(!stages.length){toast.error(t('minOneStage'));return;}if(stages.some(s=>!s.name.trim())){toast.error(t('stageNameRequired'));return;}setBusy(true);try{await api.put(`/projects/${pid}/stages`,{stages:stages.map(s=>({id:s.id,name:s.name.trim(),name_key:s.name_key||null,requires_rto:!!s.requires_rto}))});await refresh();toast.success(t('stagesSaved'));}catch(e){toast.error(errorText(e,t));}finally{setBusy(false);}};
 return <div className="page-enter">
  <SubHeader title={t('workflowStages')} subtitle={t('workflowStagesSub')}/>
  <div data-testid="workflow-stages-screen">
   <div className="checklist-editor">{stages.map((s,i)=><div key={s.id||i} className="checklist-row compact stage-row" data-testid={`stage-row-${i}`}>
    <span className="checklist-num">{i+1}</span>
    {proj?<input data-testid={`stage-name-${i}`} className="stage-name-input" placeholder={t('stageNamePh')} value={s.name} maxLength={80} onChange={e=>rename(i,e.target.value)}/>:<span className="checklist-text">{stageName(s,t)}</span>}
    <button type="button" className={`rto-toggle ${s.requires_rto?'on':''}`} data-testid={`stage-rto-${i}`} title={t('requiresRto')} aria-pressed={!!s.requires_rto} disabled={!proj} onClick={()=>toggleRto(i)}><ShieldCheck size={16}/><span>{t('requiresRto')}</span></button>
    {proj&&<span className="checklist-actions">
     <button type="button" className="icon-button" data-testid={`stage-up-${i}`} disabled={i===0} onClick={()=>move(i,-1)}><ArrowUp size={15}/></button>
     <button type="button" className="icon-button" data-testid={`stage-down-${i}`} disabled={i===stages.length-1} onClick={()=>move(i,1)}><ArrowDown size={15}/></button>
     <button type="button" className="icon-button" data-testid={`stage-del-${i}`} onClick={()=>del(i)}><Trash2 size={15}/></button>
    </span>}
   </div>)}</div>
   {proj&&<>
    <div className="checklist-add"><Action id="stage-add" icon={Plus} onClick={add}>{t('addStage')}</Action></div>
    <Action id="stage-save" icon={Save} disabled={busy} onClick={save}>{t('save')}</Action>
   </>}
  </div>
 </div>;
}
