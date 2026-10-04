import {useState} from 'react';
import {useWorkspace} from '../../lib/store';
import {useLanguage} from '../../lib/i18n';
import {useAuth} from '../../lib/auth';
import {Action,Field} from '../../components/Common';
import {errorText} from '../../lib/api';
import {toast} from 'sonner';
import {SubHeader} from './shared';

export default function PasswordSettings(){
 const {t}=useLanguage();const {data}=useWorkspace();const {changePassword}=useAuth();
 const [pw,setPw]=useState({cur:'',nw:'',nw2:''}),[pwMsg,setPwMsg]=useState('');
 const doPw=async e=>{e.preventDefault();setPwMsg('');if(pw.nw!==pw.nw2){setPwMsg(t('passwordMismatch'));return;}if(pw.nw.length<8){setPwMsg(t('passwordMin'));return;}try{await changePassword(pw.cur,pw.nw);setPw({cur:'',nw:'',nw2:''});toast.success(t('passwordChanged'));}catch(err){setPwMsg(errorText(err));}};
 return <div className="page-enter">
  <SubHeader title={t('changePassword')} subtitle={data.project.name}/>
  <form className="settings-form" data-testid="change-password-form" onSubmit={doPw}>
   <div className="form-fields">
    <label>{t('currentPassword')}<Field field={{name:'cur',type:'password'}} value={pw.cur} onChange={v=>setPw({...pw,cur:v})}/></label>
    <label>{t('newPassword')}<Field field={{name:'nw',type:'password'}} value={pw.nw} onChange={v=>setPw({...pw,nw:v})}/></label>
    <label>{t('confirmPassword')}<Field field={{name:'nw2',type:'password'}} value={pw.nw2} onChange={v=>setPw({...pw,nw2:v})}/></label>
   </div>
   {pwMsg&&<div className="form-error" data-testid="change-password-msg">{pwMsg}</div>}
   <Action id="change-password-submit" type="submit">{t('changePassword')}</Action>
  </form>
 </div>;
}
