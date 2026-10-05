import {useNavigate} from 'react-router-dom';
import {ChevronLeft} from 'lucide-react';
import {useLanguage} from '../../lib/i18n';
import {useAuth} from '../../lib/auth';
import {PageTitle} from '../../components/Common';

export function SubHeader({title,subtitle,children}){
 const {t}=useLanguage();const {user}=useAuth();const navigate=useNavigate();
 // Workers only reach the password screen (the settings menu stays blocked for them),
 // so their back button returns home instead of bouncing off /settings.
 return <>
  <button type="button" className="settings-back" data-testid="settings-back" onClick={()=>navigate(user?.role==='worker'?'/':'/settings')}>
   <ChevronLeft size={17}/>{t('back')}
  </button>
  <PageTitle title={title} subtitle={subtitle}>{children}</PageTitle>
 </>;
}
