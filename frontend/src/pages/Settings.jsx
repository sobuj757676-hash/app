import {useNavigate} from 'react-router-dom';
import {Building2,ClipboardCheck,Zap,Lock,Globe,ChevronRight} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {PageTitle} from '../components/Common';
import {ROOM_TYPES} from '../components/BlockModal';

const LANG_LABEL={en:'English',bn:'বাংলা',zh:'中文'};

export default function Settings(){
 const {t,lang}=useLanguage();const {data}=useWorkspace();const navigate=useNavigate();
 const p=data.project||{};
 const checklist=p.rto_checklist_template||[];
 const groups=[
  {label:t('projectSection'),rows:[
   {icon:Building2,title:t('settings'),summary:[p.name,p.location].filter(Boolean).join(' · '),to:'/settings/project',id:'menu-project'},
  ]},
  {label:t('quality'),rows:[
   {icon:ClipboardCheck,title:t('rtoChecklist'),summary:`${checklist.length} ${t('items')}`,to:'/settings/rto-checklist',id:'menu-rto'},
   {icon:Zap,title:t('pointTemplates'),summary:`${ROOM_TYPES.length} ${t('roomTypes')}`,to:'/settings/point-templates',id:'menu-templates'},
  ]},
  {label:t('account'),rows:[
   {icon:Lock,title:t('changePassword'),summary:'',to:'/settings/password',id:'menu-password'},
   {icon:Globe,title:'Language / ভাষা / 语言',summary:LANG_LABEL[lang]||'English',to:'/settings/language',id:'menu-language'},
  ]},
 ];
 return <div className="page-enter">
  <PageTitle title={t('settingsHome')} subtitle={p.name}/>
  {groups.map(g=><div key={g.label} className="settings-menu-group">
   <div className="settings-group-label">{g.label}</div>
   <div className="settings-menu">{g.rows.map(r=><button key={r.id} type="button" data-testid={r.id} className="settings-menu-row" onClick={()=>navigate(r.to)}>
    <span className="menu-row-icon"><r.icon size={19}/></span>
    <span className="menu-row-text"><b>{r.title}</b>{r.summary&&<small>{r.summary}</small>}</span>
    <ChevronRight size={17} className="menu-row-chevron"/>
   </button>)}</div>
  </div>)}
 </div>;
}
