import {useState,useEffect} from 'react';
import {useLocation} from 'react-router-dom';
import {OctagonAlert,Search,Plus} from 'lucide-react';
import {useWorkspace} from '../lib/store';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import {label} from '../lib/api';
import {PageTitle,Metric,Action,StatusBadge,Empty,FormModal} from '../components/Common';
import {DefectDrawer} from '../components/DefectDrawer';

const CATS=['workmanship','material','design-drawing','safety','other'],SEVS=['critical','major','minor'];
const canReport=u=>['admin','manager','engineer','supervisor','worker'].includes(u?.role);

export default function Defects(){
 const {t}=useLanguage();const {data,mutate}=useWorkspace();const {user}=useAuth();const location=useLocation();
 const [status,setStatus]=useState('all'),[severity,setSeverity]=useState('all'),[block,setBlock]=useState('all'),[q,setQ]=useState(''),[add,setAdd]=useState(false),[openId,setOpenId]=useState(null);
 useEffect(()=>{if(location.state?.openId)setOpenId(location.state.openId);},[location.state]);
 const rows=data.defects.filter(d=>(status==='all'||d.status===status)&&(severity==='all'||d.severity===severity)&&(block==='all'||d.block===block)&&`${d.title} ${d.reported_by?.name||''}`.toLowerCase().includes(q.toLowerCase())).sort((a,b)=>b.created_at.localeCompare(a.created_at));
 const open=data.defects.filter(d=>!['verified','cancelled'].includes(d.status));
 const critical=open.filter(d=>d.severity==='critical');
 const unitOptions=data.units.map(u=>({value:u.id,label:`Blk ${u.block} · ${label(u)}`}));
 return <div className="page-enter"><PageTitle title={t('defects')} subtitle={t('defectsSub')}>{canReport(user)&&<Action id="report-defect" icon={Plus} onClick={()=>setAdd(true)}>{t('reportDefect')}</Action>}</PageTitle>
 <div className="metrics-grid three">
  <Metric id="defects-open" title={t('openDefects')} value={open.length} sub={t('defectsSub')} icon={OctagonAlert} tone="amber"/>
  <Metric id="defects-critical" title={t('critical')} value={critical.length} sub={t('criticalDefects')} icon={OctagonAlert} tone="red"/>
  <Metric id="defects-verified" title={t('verified')} value={data.defects.filter(d=>d.status==='verified').length} sub={t('defectDetail')} icon={OctagonAlert} tone="green"/>
 </div>
 <div className="page-tabs">{['all','open','assigned','in_progress','rectified','verified','cancelled'].map(s=><button key={s} data-testid={`defect-tab-${s}`} className={status===s?'active':''} onClick={()=>setStatus(s)}>{t(s==='all'?'all':s)} <span>{s==='all'?data.defects.length:data.defects.filter(d=>d.status===s).length}</span></button>)}</div>
 <div className="filter-bar"><div className="search-field"><Search size={16}/><input data-testid="defect-search" placeholder={t('search')} value={q} onChange={e=>setQ(e.target.value)}/></div>
  <select data-testid="defect-severity-filter" value={severity} onChange={e=>setSeverity(e.target.value)}><option value="all">{t('allSeverities')}</option>{SEVS.map(s=><option key={s} value={s}>{t(s)}</option>)}</select>
  <select data-testid="defect-block-filter" value={block} onChange={e=>setBlock(e.target.value)}><option value="all">{t('allBlocks')}</option>{data.blocks.map(b=><option key={b.id} value={b.name}>{b.name}</option>)}</select></div>
 <div className="table-scroll"><table data-testid="defects-table"><thead><tr>{['defectDetail','unit','severity','status','assignee','dueDate'].map(k=><th key={k}>{t(k)}</th>)}</tr></thead><tbody>
  {rows.map(d=><tr key={d.id} data-testid={`defect-row-${d.id}`}><td><button className="unit-link" data-testid={`open-defect-${d.id}`} onClick={()=>setOpenId(d.id)}>{d.title}</button><small className="row-sub">{t(d.category)} · {d.reported_by?.name}</small></td>
   <td>{d.block?`Blk ${d.block} · #${String(d.level).padStart(2,'0')}-${d.number}`:'—'}</td>
   <td><span className={`severity-tag ${d.severity}`} data-testid={`defect-sev-${d.id}`}>{t(d.severity)}</span></td>
   <td><StatusBadge value={d.status} id={`defect-status-${d.id}`}/></td><td>{d.assigned_to||t('unassigned')}</td><td className="mono">{d.due_date||'—'}</td></tr>)}
 </tbody></table>{!rows.length&&<Empty text={t('noDefects')}/>}</div>
 <div className="table-footer">{rows.length} {t('records')}</div>
 {add&&<FormModal open title={t('reportDefect')} onClose={()=>setAdd(false)}
  initial={{title:'',description:'',category:'workmanship',severity:'major',unit_id:'',due_date:''}}
  fields={[{name:'title',label:t('defectDetail'),maxLength:150},{name:'description',label:t('description'),type:'textarea',wide:true,required:false},{name:'category',label:t('category'),options:CATS.map(c=>({value:c,label:t(c)}))},{name:'severity',label:t('severity'),options:SEVS.map(s=>({value:s,label:t(s)}))},{name:'unit_id',label:t('unit'),required:false,options:[{value:'',label:'—'},...unitOptions]},{name:'due_date',label:t('dueDate'),type:'date',required:false}]}
  onSubmit={v=>mutate('post',`/projects/${data.project.id}/defects`,{...v,unit_id:v.unit_id||null,due_date:v.due_date||null})}/>}
 {openId&&<DefectDrawer defectId={openId} onClose={()=>setOpenId(null)}/>}
 </div>;
}
