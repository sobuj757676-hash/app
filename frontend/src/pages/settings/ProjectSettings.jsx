import {useState,useEffect} from 'react';
import {Save} from 'lucide-react';
import {useWorkspace} from '../../lib/store';
import {useLanguage} from '../../lib/i18n';
import {useAuth,canProjects} from '../../lib/auth';
import {Action,Field} from '../../components/Common';
import {toast} from 'sonner';
import {SubHeader} from './shared';

export default function ProjectSettings(){
 const {t}=useLanguage();const {data,pid,mutate,loadProjects}=useWorkspace();const {user}=useAuth();const proj=canProjects(user);
 const [values,setValues]=useState(data.project),[busy,setBusy]=useState(false);
 useEffect(()=>setValues(data.project),[data.project]);
 const fields=[{name:'name',label:t('projectName')},{name:'location',label:t('location')},{name:'company',label:t('company')},{name:'budget',label:`${t('budget')} (SGD)`,type:'number',min:0},{name:'target_date',label:t('targetDate'),type:'date'}];
 return <div className="page-enter">
  <SubHeader title={t('settings')} subtitle={data.project.name}/>
  <form className="settings-form" data-testid="project-settings-form" onSubmit={async e=>{e.preventDefault();if(!proj)return;setBusy(true);try{await mutate('patch',`/projects/${pid}`,values);await loadProjects();toast.success(t('saved'));}catch{}finally{setBusy(false);}}}>
   <div className="form-fields">{fields.map(f=><label key={f.name}>{f.label}<Field field={{...f,disabled:!proj}} value={values[f.name]} onChange={v=>setValues({...values,[f.name]:v})}/></label>)}</div>
   {proj&&<Action id="save-project-settings" icon={Save} type="submit" disabled={busy}>{t('save')}</Action>}
  </form>
 </div>;
}
