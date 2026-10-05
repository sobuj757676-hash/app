import {useState} from 'react';
import {Grid2X2,ClipboardCheck,Activity,Users,CalendarDays,Package,Wallet,Download,ArrowDownToLine,FileSpreadsheet} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import {download,errorText} from '../lib/api';
import {PageTitle} from '../components/Common';
import {toast} from 'sonner';
const types=[['units','units',Grid2X2],['inspections','inspections',ClipboardCheck],['tests','testing',Activity],['workers','workforce',Users],['attendance','attendance',CalendarDays],['materials','materials',Package],['expenses','expenses',Wallet]];
export default function Reports(){const {t}=useLanguage();const {user}=useAuth();const {data,pid}=useWorkspace();const [busy,setBusy]=useState('');const cards=user?.role==='supervisor'?types.filter(([kind])=>kind!=='expenses'):types;return <div className="page-enter"><PageTitle title={t('reports')} subtitle={t('reportsSub')}/><div className="reports-topline"><FileSpreadsheet size={20}/><span>{data.project.name}</span><b>CSV · UTF-8</b></div><div className="reports-grid">{cards.map(([kind,key,Icon],i)=><article className="report-card" key={kind} data-testid={`report-${kind}`}><div className="report-top"><span className={`report-icon tone-${i%4}`}><Icon size={23}/></span><span className="file-tag">.CSV</span></div><h2>{t(key)}</h2><p data-testid={`report-count-${kind}`}>{data[kind].length} {t('records')}</p><button data-testid={`download-report-${kind}`} disabled={busy===kind} onClick={async()=>{setBusy(kind);try{await download(pid,kind);}catch(e){toast.error(errorText(e));}finally{setBusy('');}}}>{t('download')}<ArrowDownToLine size={16}/></button></article>)}</div></div>;}