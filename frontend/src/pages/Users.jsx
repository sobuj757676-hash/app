import {useState,useEffect,useCallback} from 'react';
import {UserCog,Plus,Copy,Check,KeyRound,Power,Search} from 'lucide-react';
import {useAuth} from '../lib/auth';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {api,errorText} from '../lib/api';
import {PageTitle,Action,FormModal,Empty,StatusBadge} from '../components/Common';
import {Dialog,DialogContent,DialogHeader,DialogTitle} from '../components/ui/dialog';
import {Button} from '../components/ui/button';
import {toast} from 'sonner';

const ALL_ROLES=['admin','manager','engineer','supervisor','worker','viewer'];

export default function Users(){
 const {t}=useLanguage();const {user:me}=useAuth();const {data}=useWorkspace();
 const [users,setUsers]=useState([]),[modal,setModal]=useState(false),[tempPw,setTempPw]=useState(null),[copied,setCopied]=useState(false),[q,setQ]=useState('');
 const manager=me?.role==='manager';
 const load=useCallback(async()=>{try{const {data:d}=await api.get('/auth/users');setUsers(d);}catch(e){toast.error(errorText(e,t));}},[t]);
 useEffect(()=>{load();},[load]);
 const roles=manager?['worker']:ALL_ROLES;
 const fields=[
  {name:'name',label:t('name')},
  {name:'email',label:t('email'),required:false},
  {name:'phone',label:t('phone'),required:false},
  ...(manager?[]:[{name:'role',label:t('role'),options:roles.map(r=>({value:r,label:t(r)}))}]),
  {name:'worker_id',label:t('linkedWorker'),required:false,options:[{value:'',label:'—'},...data.workers.filter(w=>w.active).map(w=>({value:w.id,label:`${w.name} · ${w.trade}`}))]},
 ];
 const create=async v=>{
  if(manager)v.role='worker';
  if(!v.email&&!v.phone)throw new Error(t('emailOrPhoneRequired'));
  const {data:d}=await api.post('/auth/users',v);
  if(d.temp_password)setTempPw({name:d.user.name,temp:d.temp_password});
  load();
 };
 const toggle=async u=>{
  if(!window.confirm(t(u.active?'deactivateConfirm':'activateConfirm')))return;
  try{await api.patch(`/auth/users/${u.id}`,{active:!u.active});load();toast.success(t('saved'));}catch(e){toast.error(errorText(e,t));}
 };
 const resetPw=async u=>{
  if(!window.confirm(t('resetPasswordConfirm')))return;
  try{const {data:d}=await api.post(`/auth/users/${u.id}/reset-password`);setTempPw({name:u.name,temp:d.temp_password});setCopied(false);}catch(e){toast.error(errorText(e,t));}
 };
 const copy=async()=>{try{await navigator.clipboard.writeText(tempPw.temp);setCopied(true);}catch{}};
 return <div className="page-enter" data-testid="users-page">
  <PageTitle title={t('users')} subtitle={t('usersSub')}><Action id="add-user" icon={Plus} onClick={()=>setModal(true)}>{t('addUser')}</Action></PageTitle>
  <div className="filter-bar"><div className="search-field"><Search size={16}/><input data-testid="user-search" placeholder={t('search')} value={q} onChange={e=>setQ(e.target.value)}/></div></div>
  <div className="table-scroll"><table data-testid="users-table">
   <thead><tr>{['name','identifier','role','status','actions'].map(k=><th key={k}>{t(k)}</th>)}</tr></thead>
   <tbody>{users.filter(u=>`${u.name} ${u.email||''} ${u.phone||''}`.toLowerCase().includes(q.toLowerCase())).map(u=><tr key={u.id} data-testid={`user-row-${u.id}`}>
    <td><span className="worker-avatar color-1"><UserCog size={15}/></span><strong>{u.name}</strong>{u.must_change_password&&<span className="status-badge pending">{t('tempPassword')}</span>}</td>
    <td className="mono">{u.email||u.phone||'—'}</td>
    <td><StatusBadge value={u.role} id={`user-role-${u.id}`}/></td>
    <td><StatusBadge value={u.active?'active':'inactive'} id={`user-status-${u.id}`}/></td>
    <td><div className="row-actions">
     <button className="icon-button" title={t('resetPassword')} data-testid={`reset-password-${u.id}`} onClick={()=>resetPw(u)}><KeyRound size={15}/></button>
     {u.id!==me?.id&&<button className="icon-button" title={t(u.active?'deactivate':'activate')} data-testid={`toggle-user-${u.id}`} onClick={()=>toggle(u)}><Power size={15}/></button>}
    </div></td>
   </tr>)}</tbody>
  </table>{!users.length&&<Empty text={t('noRecords')}/>}</div>
  {modal&&<FormModal open title={t('addUser')} onClose={()=>setModal(false)} fields={fields} initial={{name:'',email:'',phone:'',role:'worker',worker_id:''}} onSubmit={create} submitLabel={t('create')}/>}
  {tempPw&&<Dialog open onOpenChange={v=>!v&&setTempPw(null)}><DialogContent className="form-modal" data-testid="temp-password-modal">
   <DialogHeader><DialogTitle>{t('tempPasswordTitle')}</DialogTitle></DialogHeader>
   <p>{t('tempPasswordHint')} <b>{tempPw.name}</b></p>
   <div className="temp-password" data-testid="temp-password-value"><code>{tempPw.temp}</code><Button type="button" variant="outline" data-testid="copy-temp-password" onClick={copy}>{copied?<Check size={15}/>:<Copy size={15}/>} {t(copied?'copied':'copy')}</Button></div>
   <div className="form-footer"><Button className="action" data-testid="temp-password-done" onClick={()=>setTempPw(null)}>{t('done')}</Button></div>
  </DialogContent></Dialog>}
 </div>;
}
