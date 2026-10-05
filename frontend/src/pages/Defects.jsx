import {useState,useEffect} from 'react';
import {useLocation,useSearchParams} from 'react-router-dom';
import {OctagonAlert,AlertTriangle,BadgeCheck,Search,Plus} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import {PageTitle,Metric,Action,StatusBadge,Empty} from '../components/Common';
import {DefectDrawer} from '../components/DefectDrawer';
import {DefectReportModal,DEFECT_CATS,DEFECT_SEVS} from '../components/DefectReportModal';

const canReport=u=>['admin','manager','engineer','supervisor','worker'].includes(u?.role);

export default function Defects(){
 const {t}=useLanguage();const {data}=useWorkspace();const {user}=useAuth();const location=useLocation();
 const [status,setStatus]=useState('all'),[severity,setSeverity]=useState('all'),[block,setBlock]=useState('all'),[q,setQ]=useState(''),[add,setAdd]=useState(false),[openId,setOpenId]=useState(null);
 const [params,setParams]=useSearchParams();
 // Deep-link: ?open=<id> restores the drawer on load/refresh/share (location.state kept as fallback)
 useEffect(()=>{const oid=params.get('open')||location.state?.openId;if(oid)setOpenId(oid);},[params,location.state]);
 const openDefect=id=>{setOpenId(id);setParams({open:id});};
 const closeDefect=()=>{setOpenId(null);setParams({});};
 const rows=data.defects.filter(d=>(status==='all'||d.status===status)&&(severity==='all'||d.severity===severity)&&(block==='all'||d.block===block)&&`${d.title} ${d.description||''} ${d.reported_by?.name||''}`.toLowerCase().includes(q.toLowerCase())).sort((a,b)=>b.created_at.localeCompare(a.created_at));
 const open=data.defects.filter(d=>!['verified','cancelled'].includes(d.status));
 const critical=open.filter(d=>d.severity==='critical');
 return <div className="page-enter"><PageTitle title={t('defects')} subtitle={t('defectsSub')}>{canReport(user)&&<Action id="report-defect" icon={Plus} onClick={()=>setAdd(true)}>{t('reportDefect')}</Action>}</PageTitle>
 <div className="metrics-grid three">
  <Metric id="defects-open" title={t('openDefects')} value={open.length} sub={t('needsAction')} icon={OctagonAlert} tone="amber"/>
  <Metric id="defects-critical" title={t('critical')} value={critical.length} sub={t('criticalDefects')} icon={AlertTriangle} tone="red"/>
  <Metric id="defects-verified" title={t('verified')} value={data.defects.filter(d=>d.status==='verified').length} icon={BadgeCheck} tone="green"/>
 </div>
 <div className="page-tabs">{['all','open','assigned','in_progress','rectified','verified','cancelled'].map(s=><button key={s} data-testid={`defect-tab-${s}`} className={status===s?'active':''} onClick={()=>setStatus(s)}>{t(s==='all'?'all':s)} <span>{s==='all'?data.defects.length:data.defects.filter(d=>d.status===s).length}</span></button>)}</div>
 <div className="filter-bar"><div className="search-field"><Search size={16}/><input data-testid="defect-search" placeholder={t('search')} value={q} onChange={e=>setQ(e.target.value)}/></div>
  <select data-testid="defect-severity-filter" value={severity} onChange={e=>setSeverity(e.target.value)}><option value="all">{t('allSeverities')}</option>{DEFECT_SEVS.map(s=><option key={s} value={s}>{t(s)}</option>)}</select>
  <select data-testid="defect-block-filter" value={block} onChange={e=>setBlock(e.target.value)}><option value="all">{t('allBlocks')}</option>{data.blocks.map(b=><option key={b.id} value={b.name}>{b.name}</option>)}</select></div>
 <div className="table-scroll"><table data-testid="defects-table"><thead><tr>{['defectTitle','unit','severity','status','assignee','dueDate'].map(k=><th key={k}>{t(k)}</th>)}</tr></thead><tbody>
  {rows.map(d=><tr key={d.id} data-testid={`defect-row-${d.id}`}><td><button className="unit-link" data-testid={`open-defect-${d.id}`} onClick={()=>openDefect(d.id)}>{d.title}</button><small className="row-sub">{t(d.category)} · {d.reported_by?.name}</small></td>
   <td>{d.block?`${t('blk')} ${d.block} · #${String(d.level).padStart(2,'0')}-${d.number}`:'—'}</td>
   <td><span className={`severity-tag ${d.severity}`} data-testid={`defect-sev-${d.id}`}>{t(d.severity)}</span></td>
   <td><StatusBadge value={d.status} id={`defect-status-${d.id}`}/></td><td>{d.assigned_to_name||d.assigned_to||t('unassigned')}</td><td className="mono">{d.due_date||'—'}</td></tr>)}
 </tbody></table>{!rows.length&&<div className="empty-cta"><Empty text={t('noDefects')}/>{canReport(user)&&<Action id="report-defect-empty" icon={Plus} onClick={()=>setAdd(true)}>{t('reportDefect')}</Action>}</div>}</div>
 <div className="table-footer">{rows.length} {t('records')}</div>
 {add&&<DefectReportModal onClose={()=>setAdd(false)}/>}
 {openId&&<DefectDrawer defectId={openId} onClose={closeDefect}/>}
 </div>;
}
