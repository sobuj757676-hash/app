import {useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {Zap,Loader2,Lock} from 'lucide-react';
import {useAuth} from '../lib/auth';
import {useLanguage} from '../lib/i18n';
import {errorText} from '../lib/api';
import {Input} from '../components/ui/input';
import {Button} from '../components/ui/button';

export function ForceChangePassword({onDone}){
 const {t}=useLanguage();const {changePassword}=useAuth();
 const [cur,setCur]=useState(''),[nw,setNw]=useState(''),[nw2,setNw2]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const submit=async e=>{
  e.preventDefault();setError('');
  if(nw!==nw2){setError(t('passwordMismatch'));return;}
  if(nw.length<8){setError(t('passwordMin'));return;}
  setBusy(true);
  try{await changePassword(cur,nw);onDone&&onDone();}
  catch(e){setError(errorText(e));}
  finally{setBusy(false);}
 };
 return <div className="login-card" data-testid="force-change-password">
  <span className="login-icon"><Lock size={22}/></span>
  <h1>{t('mustChangePassword')}</h1><p>{t('mustChangePasswordSub')}</p>
  <form onSubmit={submit}>
   <label>{t('currentPassword')}<Input data-testid="field-current-password" type="password" value={cur} onChange={e=>setCur(e.target.value)} required/></label>
   <label>{t('newPassword')}<Input data-testid="field-new-password" type="password" value={nw} onChange={e=>setNw(e.target.value)} required minLength={8}/></label>
   <label>{t('confirmPassword')}<Input data-testid="field-confirm-password" type="password" value={nw2} onChange={e=>setNw2(e.target.value)} required minLength={8}/></label>
   {error&&<div className="form-error" data-testid="change-password-error">{error}</div>}
   <Button type="submit" className="action login-submit" disabled={busy} data-testid="change-password-submit">{busy&&<Loader2 className="spin" size={15}/>} {t('changePassword')}</Button>
  </form>
 </div>;
}

export default function Login(){
 const {t}=useLanguage();const {login}=useAuth();const navigate=useNavigate();
 const [identifier,setIdentifier]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[mustChange,setMustChange]=useState(false);
 const submit=async e=>{
  e.preventDefault();setError('');setBusy(true);
  try{
   const u=await login(identifier,password);
   if(u.must_change_password)setMustChange(true);
   else navigate('/',{replace:true});
  }catch(e){setError(errorText(e));}
  finally{setBusy(false);}
 };
 return <div className="login-page" data-testid="login-page">
  {mustChange?<ForceChangePassword onDone={()=>navigate('/',{replace:true})}/>:
  <div className="login-card">
   <span className="login-icon"><Zap size={24}/></span>
   <h1>voltcraft</h1><p>{t('loginSub')}</p>
   <form onSubmit={submit}>
    <label>{t('identifier')}<Input data-testid="field-identifier" value={identifier} onChange={e=>setIdentifier(e.target.value)} placeholder={t('identifierHint')} required autoComplete="username"/></label>
    <label>{t('password')}<Input data-testid="field-password" type="password" value={password} onChange={e=>setPassword(e.target.value)} required autoComplete="current-password"/></label>
    {error&&<div className="form-error" data-testid="login-error">{error}</div>}
    <Button type="submit" className="action login-submit" disabled={busy} data-testid="login-submit">{busy&&<Loader2 className="spin" size={15}/>} {t('signIn')}</Button>
   </form>
  </div>}
 </div>;
}
