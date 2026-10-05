import {useEffect,useMemo,useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Grid2X2,List,Search,ArrowUpRight,Check,Clock3,AlertTriangle,Building2} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {useAuth,canWrite} from '../lib/auth';
import {label,status,percent} from '../lib/api';
import {PageTitle,ExportButton,Action,StatusBadge,ProgressBar,Empty,FormModal} from '../components/Common';

const statuses=['completed','inProgress','pending','rework','notStarted'];
export default function UnitTracker(){
 const {t}=useLanguage();
 const {data,selectedUnit,setSelectedUnit,mutate}=useWorkspace();
 const {user}=useAuth();const ro=!canWrite(user);
 const [params,setParams]=useSearchParams();
 const [block,setBlock]=useState(params.get('block')||(params.has('q')?'all':data.blocks[0]?.id||''));
 const [q,setQ]=useState(params.get('q')||'');
 const [mode,setMode]=useState('matrix');
 const [filter,setFilter]=useState('all');
 const [level,setLevel]=useState('all');
 const [modal,setModal]=useState(false);
 const wasOpen=useRef(false);
 // Deep-link: ?unit=<uid> opens the drawer (and selects its block tab) on load/param change
 useEffect(()=>{
  setQ(params.get('q')||'');
  if(params.get('block'))setBlock(params.get('block'));
  else if(params.has('q')){setBlock('all');setLevel('all');setFilter('all');}
  const uid=params.get('unit');
  if(uid){const u=data.units.find(x=>x.id===uid);if(u){setBlock(u.block_id);setSelectedUnit(uid);}}
 },[params,data.units,setSelectedUnit]);
 // Clear ?unit= when the drawer closes (guarded so a fresh deep-link load isn't wiped)
 useEffect(()=>{
  if(selectedUnit){wasOpen.current=true;}
  else if(wasOpen.current){wasOpen.current=false;if(params.get('unit')){const p=Object.fromEntries(params.entries());delete p.unit;setParams(p);}}
 },[selectedUnit,params,setParams]);
 const allBlocks=block==='all';
 const chosen=data.blocks.find(b=>b.id===block);
 const blockUnits=data.units.filter(u=>allBlocks||u.block_id===chosen?.id);
 const filtered=blockUnits.filter(u=>(filter==='all'||status(u)===filter)&&(level==='all'||u.level===Number(level))&&`${label(u)} ${u.block} ${u.assigned_to}`.toLowerCase().includes(q.toLowerCase()));
 const floors=[...new Set(blockUnits.map(u=>u.level))].sort((a,b)=>b-a);
 const stacks=[...new Set(blockUnits.map(u=>u.number))].sort((a,b)=>Number(a)-Number(b));
 const cells=useMemo(()=>Object.fromEntries(filtered.map(u=>[`${u.level}-${u.number}`,u])),[filtered]);
 const chooseBlock=id=>{setBlock(id);setLevel('all');setParams({...Object.fromEntries(params.entries()),block:id});};
 const openUnit=u=>{setSelectedUnit(u.id);setParams({block:u.block_id,unit:u.id});};
 return <div className="page-enter">
  <PageTitle title={t('units')} subtitle={t('blockOverview')}>
   <ExportButton/>{!ro&&<span title={!chosen?t('selectBlockFirst'):undefined}><Action id="add-unit" onClick={()=>setModal(true)} disabled={!chosen}>{t('addUnit')}</Action></span>}
  </PageTitle>
  <div className="block-tabs">
   <button data-testid="block-tab-all" className={allBlocks?'active':''} onClick={()=>chooseBlock('all')}><Building2 size={16}/>{t('allBlocks')}<span>{data.units.length}</span></button>
   {data.blocks.map(b=><button data-testid={`block-tab-${b.name}`} key={b.id} className={chosen?.id===b.id?'active':''} onClick={()=>chooseBlock(b.id)}><Building2 size={16}/>{t('block')} {b.name}<span>{data.units.filter(u=>u.block_id===b.id).length}</span></button>)}
  </div>
  <div className="tracker-overview">
   <div><h2 data-testid="selected-block">{allBlocks?t('allBlocks'):`${t('block')} ${chosen?.name||'—'}`}</h2><span>{allBlocks?`${data.blocks.length} ${t('block')}`:`${chosen?.levels||0} ${t('levels')}`} <i>·</i> {blockUnits.length} {t('unitCount')}</span></div>
   <div className="tracker-progress"><span>{t('overallProgress')}<b>{percent(blockUnits)}%</b></span><ProgressBar id="tracker-block-progress" value={percent(blockUnits)}/></div>
  </div>
  <div className="tracker-legend">{statuses.map(s=><button key={s} data-testid={`status-filter-${s}`} onClick={()=>setFilter(filter===s?'all':s)} className={filter===s?'selected':''}><StatusBadge id={`legend-${s}`} value={s}/><b>{blockUnits.filter(u=>status(u)===s).length}</b></button>)}</div>
  <div className="filter-bar">
   <div className="search-field"><Search size={16}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder={t('searchUnits')} data-testid="unit-search"/></div>
   <select data-testid="level-filter" value={level} onChange={e=>setLevel(e.target.value)}><option value="all">{t('allLevels')}</option>{floors.slice().reverse().map(l=><option key={l} value={l}>{t('level')} {l}</option>)}</select>
   <select value={filter} onChange={e=>setFilter(e.target.value)} data-testid="unit-status-filter"><option value="all">{t('allStatuses')}</option>{statuses.map(s=><option key={s} value={s}>{t(s)}</option>)}</select>
   <div className="view-toggle"><button title={t('matrix')} disabled={allBlocks} data-testid="matrix-view" onClick={()=>setMode('matrix')} className={mode==='matrix'&&!allBlocks?'active':''}><Grid2X2 size={17}/></button><button title={t('list')} data-testid="list-view" onClick={()=>setMode('list')} className={mode==='list'||allBlocks?'active':''}><List size={18}/></button></div>
  </div>
  {!filtered.length?<Empty text={t('noUnits')}/>:mode==='matrix'&&!allBlocks?
   <div className="matrix-scroll" data-testid="floor-matrix"><div className="floor-matrix" style={{gridTemplateColumns:`64px repeat(${stacks.length}, minmax(50px, 1fr))`}}>
    <div className="matrix-corner">{t('level')}</div>{stacks.map(n=><div className="matrix-column" key={n}>#{n}</div>)}
    {floors.filter(l=>level==='all'||l===Number(level)).map(l=><div className="matrix-row" key={l}>
     <div className="matrix-level">{String(l).padStart(2,'0')}</div>
     {stacks.map(n=>{const u=cells[`${l}-${n}`];return u?<button key={n} data-testid={`matrix-unit-${u.id}`} aria-label={`${t('block')} ${u.block} ${label(u)} ${t(status(u))}`} title={`${label(u)} · ${t(u.stage===9?'completed':`stage${u.stage}`)}`} className={`unit-cell ${status(u)}`} onClick={()=>openUnit(u)}>{u.stage===9?<Check size={16}/>:u.rto==='pending'?<Clock3 size={16}/>:u.rto==='rework'?<AlertTriangle size={16}/>:<span>{u.stage}<small>/9</small></span>}</button>:<div className="unit-cell unavailable" key={n}>—</div>;})}
    </div>)}
   </div></div>:
   <div className="table-scroll tracker-list"><table data-testid="units-table">
    <thead><tr>{['block','unit','unitType','currentStage','team','status','progress'].map(k=><th key={k}>{t(k)}</th>)}<th/></tr></thead>
    <tbody>{filtered.map(u=><tr key={u.id} data-testid={`unit-row-${u.id}`}>
     <td>{u.block}</td><td><button className="unit-link" data-testid={`open-unit-${u.id}`} onClick={()=>openUnit(u)}>{label(u)}</button></td><td>{u.unit_type}</td><td>{t(u.stage===9?'completed':`stage${u.stage}`)}</td><td>{u.assigned_to||t('unassigned')}</td><td><StatusBadge id={`unit-status-${u.id}`} value={status(u)}/></td><td><span className="mono">{u.stage}/9</span></td><td><button className="icon-button" title={t('view')} data-testid={`unit-detail-${u.id}`} onClick={()=>openUnit(u)}><ArrowUpRight size={17}/></button></td>
    </tr>)}</tbody>
   </table></div>
  }
  <div className="table-footer" data-testid="unit-result-count">{filtered.length} / {blockUnits.length} {t('unitCount')}<span>{chosen?.sample_layout?t('sample'):t('recorded')}</span></div>
  {modal&&chosen&&!ro&&<FormModal open onClose={()=>setModal(false)} title={t('addUnit')} initial={{level:1,number:'',unit_type:'4-room',assigned_to:'',note:''}} fields={[{name:'level',label:t('level'),type:'number',min:1,max:chosen.levels},{name:'number',label:t('unit')},{name:'unit_type',label:t('unitType'),options:['2-room Flexi','3-room','4-room','5-room']},{name:'assigned_to',label:t('team'),required:false}]} onSubmit={v=>mutate('post',`/blocks/${chosen.id}/units`,v)}/>}
 </div>;
}