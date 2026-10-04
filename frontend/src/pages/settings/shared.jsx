import {useNavigate} from 'react-router-dom';
import {ChevronLeft} from 'lucide-react';
import {useLanguage} from '../../lib/i18n';
import {PageTitle} from '../../components/Common';

export function SubHeader({title,subtitle,children}){
 const {t}=useLanguage();const navigate=useNavigate();
 return <>
  <button type="button" className="settings-back" data-testid="settings-back" onClick={()=>navigate('/settings')}>
   <ChevronLeft size={17}/>{t('back')}
  </button>
  <PageTitle title={title} subtitle={subtitle}>{children}</PageTitle>
 </>;
}
