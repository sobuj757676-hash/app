import {useEffect,useMemo,useRef,useState} from 'react';
import {useSearchParams} from 'react-router-dom';
import {Grid2X2,List,Search,ArrowUpRight,Check,Clock3,AlertTriangle,Building2,ListChecks,X} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {useAuth,canWrite} from '../lib/auth';
import {label,status,percent,stageName,stagesOf,api,today} from '../lib/api';
import {PageTitle,ExportButton,Action,StatusBadge,ProgressBar,Empty,FormModal} from '../components/Common';
import {AssigneeMultiSelect} from '../components/AssigneeMultiSelect';
import {toast} from 'sonner';
import {ROOM_TYPES} from '../components/BlockModal';

const statuses=['completed','inProgress','pending','rework','notStarted'];
export default function UnitTracker(){
 const {t}=useLanguage();
 const {data,selectedUnit,setSelectedUnit,mutate}=useWorkspace();
 const stages=stagesOf(data),sc=stages.length||1;
 const {user}=useAuth();const ro=!canWrite(user);
 const [params,setParams]=useSearchParams();
 const [block,setBlock]=useState(params.get('block')||(params.has('q')?'all':data.blocks[0]?.id||''));
 const [q,setQ]=useState(params.get('q')||'');
 const [mode,setMode]=useState('matrix');
 const [filter,setFilter]=useState('all');
 const [level,setLevel]=useState('all');
 const [modal,setModal]=useState(false);
 // Daily-plan compose: select mode (toolbar toggle or ?select=1 deep-link from the plan tab's "Add work")
 const [selecting,setSelecting]=useState(params.get('select')==='1');
 const [selected,setSelected]=useState([]);
 const [sheet,setSheet]=useState(false);
 const toggleUnit=id=>setSelected(s=>s.includes(id)?s.filter(x=>x!==id):[...s,id]);
 const toggleSelect=()=>{const p=Object.fromEntries(params.entries());if(selecting){delete p.select;setSelecting(false);setSelected([]);}else{p.select='1';setSelecting(true);}setParams(p);};
 const wasOpen=useRef(false);
 // Deep-link: ?unit=<uid> opens the drawer (and selects its block tab) on load/param change
 useEffect(()=>{
  setQ(params.get('q')||'');
  if(params.get('block'))setBlock(params.get('block'));
  else if(params.has('q')){setBlock('all');setLevel('all');setFilter('all');}
  const uid=params.get('unit');
  if(uid){const u=data.units.find(x=>x.id===uid);if(u){setBlock(u.block_id);setSelectedUnit(uid);}}
  if(params.get('select')==='1')setSelecting(true);
 },[params,data.units,setSelectedUnit]);
 // Clear ?unit= when the drawer closes (guarded so a fresh deep-link load isn't wiped)
 useEffect(()=>{
  if(selectedUnit){wasOpen.current=true;}
  else if(wasOpen.current){wasOpen.current=false;if(params.get('unit')){const p=Object.fromEntries(params.entries());delete p.unit;setParams(p);}}
 },[selectedUnit,params,setParams]);
 const allBlocks=block==='all';
 const chosen=data.blocks.find(b=>b.id===block);
 const blockUnits=data.units.filter(u=>allBlocks||u.block_id===chosen?.id);
 const filtered=blockUnits.filter(u=>(filter==='all'||status(u,sc)===filter)&&(level==='all'||u.level===Number(level))&&`${label(u)} ${u.block} ${u.assigned_to}`.toLowerCase().includes(q.toLowerCase()));
 const floors=[...new Set(blockUnits.map(u=>u.level))].sort((a,b)=>b-a);
 const stacks=[...new Set(blockUnits.map(u=>u.number))].sort((a,b)=>Number(a)-Number(b));
 const cells=useMemo(()=>Object.fromEntries(filtered.map(u=>[`${u.level}-${u.number}`,u])),[filtered]);
 const chooseBlock=id=>{setBlock(id);setLevel('all');setParams({...Object.fromEntries(params.entries()),block:id});};
 const openUnit=u=>{setSelectedUnit(u.id);setParams({block:u.block_id,unit:u.id});};
 return <div className="page-enter">
  <PageTitle title={t('units')} subtitle={t('blockOverview')}>
   <ExportButton/>{!ro&&<Action id="select-mode" secondary icon={selecting?X:ListChecks} onClick={toggleSelect}>{t('selectMode')}</Action>}{!ro&&<span title={!chosen?t('selectBlockFirst'):undefined}><Action id="add-unit" onClick={()=>setModal(true)} disabled={!chosen}>{t('addUnit')}</Action></span>}
  </PageTitle>
  <div className="block-tabs">
   <button data-testid="block-tab-all" className={allBlocks?'active':''} onClick={()=>chooseBlock('all')}><Building2 size={16}/>{t('allBlocks')}<span>{data.units.length}</span></button>
   {data.blocks.map(b=><button data-testid={`block-tab-${b.name}`} key={b.id} className={chosen?.id===b.id?'active':''} onClick={()=>chooseBlock(b.id)}><Building2 size={16}/>{t('block')} {b.name}<span>{data.units.filter(u=>u.block_id===b.id).length}</span></button>)}
  </div>
  <div className="tracker-overview">
   <div><h2 data-testid="selected-block">{allBlocks?t('allBlocks'):`${t('block')} ${chosen?.name||'—'}`}</h2><span>{allBlocks?`${data.blocks.length} ${t('block')}`:`${chosen?.levels||0} ${t('levels')}`} <i>·</i> {blockUnits.length} {t('unitCount')}</span></div>
   <div className="tracker-progress"><span>{t('overallProgress')}<b>{percent(blockUnits,sc)}%</b></span><ProgressBar id="tracker-block-progress" value={percent(blockUnits,sc)}/></div>
  </div>
  <div className="tracker-legend">{statuses.map(s=><button key={s} data-testid={`status-filter-${s}`} onClick={()=>setFilter(filter===s?'all':s)} className={filter===s?'selected':''}><StatusBadge id={`legend-${s}`} value={s}/><b>{blockUnits.filter(u=>status(u,sc)===s).length}</b></button>)}</div>
  <div className="filter-bar">
   <div className="search-field"><Search size={16}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder={t('searchUnits')} data-testid="unit-search"/></div>
   <select data-testid="level-filter" value={level} onChange={e=>setLevel(e.target.value)}><option value="all">{t('allLevels')}</option>{floors.slice().reverse().map(l=><option key={l} value={l}>{t('level')} {l}</option>)}</select>
   <select value={filter} onChange={e=>setFilter(e.target.value)} data-testid="unit-status-filter"><option value="all">{t('allStatuses')}</option>{statuses.map(s=><option key={s} value={s}>{t(s)}</option>)}</select>
   <div className="view-toggle"><button title={t('matrix')} disabled={allBlocks} data-testid="matrix-view" onClick={()=>setMode('matrix')} className={mode==='matrix'&&!allBlocks?'active':''}><Grid2X2 size={17}/></button><button title={t('list')} data-testid="list-view" onClick={()=>setMode('list')} className={mode==='list'||allBlocks?'active':''}><List size={18}/></button></div>
  </div>
  {!filtered.length?<Empty text={t('noUnits')}/>:mode==='matrix'&&!allBlocks?
   <div className="matrix-scroll" data-testid="floor-matrix"><div className={`floor-matrix${selecting?' selecting':''}`} style={{gridTemplateColumns:`64px repeat(${stacks.length}, minmax(50px, 1fr))`}}>
    <div className="matrix-corner">{t('level')}</div>{stacks.map(n=><div className="matrix-column" key={n}>#{n}</div>)}
    {floors.filter(l=>level==='all'||l===Number(level)).map(l=><div className="matrix-row" key={l}>
     <div className="matrix-level">{String(l).padStart(2,'0')}</div>
     {stacks.map(n=>{const u=cells[`${l}-${n}`];if(!u)return <div className="unit-cell unavailable" key={n}>—</div>;const sel=selecting&&selected.includes(u.id);return <button key={n} data-testid={`matrix-unit-${u.id}`} aria-label={`${t('block')} ${u.block} ${label(u)} ${t(selecting?'selectMode':status(u,sc))}`} aria-pressed={selecting?sel:undefined} title={selecting?`${label(u)} · ${t('selectMode')}`:`${label(u)} · ${u.stage>=sc?t('completed'):stageName(stages[u.stage],t)}`} className={`unit-cell ${status(u,sc)}${sel?' selected':''}`} onClick={()=>selecting?toggleUnit(u.id):openUnit(u)}>{selecting?<span className="select-box">{sel&&<Check size={16}/>}</span>:u.stage>=sc?<Check size={16}/>:u.rto==='pending'?<Clock3 size={16}/>:u.rto==='rework'?<AlertTriangle size={16}/>:<span>{u.stage}<small>/{sc}</small></span>}</button>;})}
    </div>)}
   </div></div>:
   <div className="table-scroll tracker-list"><table data-testid="units-table">
    <thead><tr>{selecting&&<th/>}{['block','unit','unitType','currentStage','team','status','progress'].map(k=><th key={k}>{t(k)}</th>)}<th/></tr></thead>
    <tbody>{filtered.map(u=>{const sel=selecting&&selected.includes(u.id);return <tr key={u.id} data-testid={`unit-row-${u.id}`} className={sel?'selected':''}>
     {selecting&&<td><label className="row-select-wrap"><input type="checkbox" data-testid={`select-unit-${u.id}`} checked={sel} onChange={()=>toggleUnit(u.id)} aria-label={`${t('selectMode')} ${label(u)}`}/></label></td>}
     <td>{u.block}</td><td><button className="unit-link" data-testid={`open-unit-${u.id}`} onClick={()=>selecting?toggleUnit(u.id):openUnit(u)}>{label(u)}</button></td><td>{u.unit_type}</td><td>{u.stage>=sc?t('completed'):stageName(stages[u.stage],t)}</td><td>{u.assigned_to||t('unassigned')}</td><td><StatusBadge id={`unit-status-${u.id}`} value={status(u,sc)}/></td><td><span className="mono">{u.stage}/{sc}</span></td><td><button className="icon-button" title={t('view')} data-testid={`unit-detail-${u.id}`} onClick={()=>openUnit(u)}><ArrowUpRight size={17}/></button></td>
    </tr>;})}</tbody>
   </table></div>
  }
  <div className="table-footer" data-testid="unit-result-count">{filtered.length} / {blockUnits.length} {t('unitCount')}<span>{chosen?.sample_layout?t('sample'):t('recorded')}</span></div>
  {selecting&&!ro&&<div className="select-bar" data-testid="select-bar">
   <span data-testid="select-count">{t('selectedCount').replace('{n}',String(selected.length))}</span>
   <span className="select-bar-actions"><button type="button" className="text-link" data-testid="select-cancel" onClick={toggleSelect}>{t('cancel')}</button><Action id="add-to-plan" disabled={!selected.length} onClick={()=>setSheet(true)}>{t('addToPlan')}</Action></span>
  </div>}
  {sheet&&!ro&&<PlanSheet unitIds={selected} onClose={()=>setSheet(false)} onDone={()=>{setSheet(false);toggleSelect();}}/>}
  {modal&&chosen&&!ro&&<FormModal open onClose={()=>setModal(false)} title={t('addUnit')} initial={{level:1,number:'',unit_type:'4-room',assigned_to:'',note:''}} fields={[{name:'level',label:t('level'),type:'number',min:1,max:chosen.levels},{name:'number',label:t('unit')},{name:'unit_type',label:t('unitType'),options:ROOM_TYPES},{name:'assigned_to',label:t('team'),required:false}]} onSubmit={v=>mutate('post',`/blocks/${chosen.id}/units`,v)}/>}
 </div>;
}

// Plan sheet: auto-splits the tracker selection into one group per
// (block, level, stage); one planned task is created per group on submit.
// Full-screen overlay on mobile, centered dialog on desktop.
function PlanSheet({unitIds,onClose,onDone}){
 const {t}=useLanguage();const {data,pid,mutate}=useWorkspace();
 const stages=stagesOf(data),sc=stages.length||1;
 const byId=useMemo(()=>Object.fromEntries((data.units||[]).map(u=>[u.id,u])),[data.units]);
 const units=unitIds.map(id=>byId[id]).filter(Boolean);
 const groups=useMemo(()=>{const m=new Map();for(const u of units){const key=`${u.block_id}|${u.level}|${u.stage}`;if(!m.has(key))m.set(key,{key,block_id:u.block_id,block:u.block,level:u.level,stage_index:u.stage,units:[]});m.get(key).units.push(u);}return [...m.values()].sort((a,b)=>a.block===b.block?(a.level-b.level||a.stage_index-b.stage_index):String(a.block).localeCompare(String(b.block)));},[units]);
 const stageLabel=g=>g.stage_index>=sc?t('completed'):stageName(stages[g.stage_index],t);
 const [dir,setDir]=useState([]);const [dirErr,setDirErr]=useState(false);
 const [cfg,setCfg]=useState({});const [busy,setBusy]=useState(false);
 const loadDir=()=>{setDirErr(false);api.get('/auth/directory').then(r=>setDir(r.data)).catch(()=>setDirErr(true));};
 useEffect(loadDir,[]);
 const setG=(key,patch)=>setCfg(c=>({...c,[key]:{assignees:[],priority:'medium',note:'',...(c[key]||{}),...patch}}));
 const submit=async()=>{setBusy(true);try{const d=today();for(const g of groups){const c={assignees:[],priority:'medium',note:'',...(cfg[g.key]||{})};await mutate('post',`/projects/${pid}/tasks`,{title:`${stageLabel(g)} — ${t('blk')} ${g.block} L${g.level} (${g.units.length} units)`,description:c.note||null,kind:'planned',scope:{block_id:g.block_id,level:g.level,stage_index:g.stage_index,unit_ids:g.units.map(u=>u.id)},plan_date:d,due_date:d,assignees:c.assignees,priority:c.priority,completed_unit_ids:[]});}toast.success(t('saved'));onDone();}catch{}finally{setBusy(false);}};
 return <div className="plan-compose-overlay" data-testid="plan-sheet">
  <div className="plan-compose-sheet" role="dialog" aria-modal="true" aria-label={t('planSheetTitle')}>
   <div className="plan-compose-head"><strong data-testid="plan-sheet-title">{t('planSheetTitle')}</strong><button type="button" className="icon-button" data-testid="plan-sheet-close" onClick={onClose} aria-label={t('cancel')}><X size={20}/></button></div>
   <div className="plan-compose-body">
    {groups.map((g,gi)=>{const c={assignees:[],priority:'medium',note:'',...(cfg[g.key]||{})};return <div className="plan-group-card" key={g.key} data-testid={`plan-group-${gi}`}>
     <div className="plan-group-line" data-testid={`plan-group-title-${gi}`}>{t('blk')} {g.block} · L{g.level} · {stageLabel(g)} — {g.units.length} {t('unitCount')}</div>
     <span className="field-label">{t('workersLabel')}</span>
     <AssigneeMultiSelect directory={dir} value={c.assignees} onChange={ids=>setG(g.key,{assignees:ids})} id={`plan-group-${gi}-workers`}/>
     {dirErr&&<div className="inline-error" role="alert" data-testid={`plan-group-${gi}-directory-error`}><span>{t('directoryLoadFailed')}</span><button type="button" className="text-link" onClick={loadDir}>{t('retry')}</button></div>}
     <span className="field-label">{t('priority')}</span>
     <div className="seg-control" role="radiogroup" aria-label={t('priority')}>{['low','medium','high'].map(p=><button key={p} type="button" role="radio" aria-checked={c.priority===p} data-testid={`plan-group-${gi}-pri-${p}`} className={c.priority===p?'active':''} onClick={()=>setG(g.key,{priority:p})}>{t(p)}</button>)}</div>
     <span className="field-label">{t('noteOptional')}</span>
     <input className="plan-note" data-testid={`plan-group-${gi}-note`} value={c.note} onChange={e=>setG(g.key,{note:e.target.value})} maxLength={200} placeholder={t('noteOptional')}/>
    </div>;})}
   </div>
   <div className="plan-compose-foot"><Action id="plan-sheet-submit" disabled={busy||!groups.length} onClick={submit}>{busy?'…':`${units.length} · ${t('addToPlan')}`}</Action></div>
  </div>
 </div>;
}
