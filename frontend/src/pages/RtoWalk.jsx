import {useEffect,useMemo,useState} from 'react';
import {ClipboardCheck,Footprints,Lock,Check,TriangleAlert} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {useAuth,canWrite,canDecideRto} from '../lib/auth';
import {api,label,today,stagesOf,stageName} from '../lib/api';
import {gateIndexOf,pendingInspectionByUnit,proposedUnitIds,walkBlocks,walkFloors,applyFloorPass,loadWalkDraft,saveWalkDraft} from '../lib/rtoWalk';
import {PageTitle,Empty,Action} from '../components/Common';
import {toast} from 'sonner';

// RTO Walk (spec v2 §4 + v2.1 §D): a batch front-end over the existing RTO
// machinery. Nothing is pre-passed — a unit is marked fail by tapping it,
// and passes come only from the per-floor "Floor inspected" action after
// that floor's readiness checklist is confirmed. Marks live locally
// ("On this phone — not submitted") until Commit sends them: requests
// first, then outcomes — decisions for DECIDE roles, proposals recorded
// on the inspection records for everyone else.
export default function RtoWalk(){
 const {t}=useLanguage();const {data,pid,refresh}=useWorkspace();const {user}=useAuth();
 const date=today();
 const draftRef=useMemo(()=>loadWalkDraft(pid,date),[pid,date]);
 const blocks=walkBlocks(data);
 const [block,setBlock]=useState(draftRef?.block||blocks[0]||'');
 const [marks,setMarks]=useState(draftRef?.marks||{});
 const [inspector,setInspector]=useState(draftRef?.inspector||'');
 const [floorChecks,setFloorChecks]=useState(draftRef?.floorChecks||{});
 const [busy,setBusy]=useState(false);
 const [report,setReport]=useState(null);
 const decide=canDecideRto(user);
 const template=data.project.rto_checklist_template||[];
 const stages=stagesOf(data),gate=gateIndexOf(data),gateStage=gate>=0?stages[gate]:null;
 const floors=useMemo(()=>walkFloors(data,block),[data,block]);
 const pendingByUnit=useMemo(()=>pendingInspectionByUnit(data),[data]);
 const proposedIds=useMemo(()=>proposedUnitIds(data),[data]);
 const activeBlock=blocks.includes(block)?block:(blocks[0]||'');

 // Persist the local draft whenever it changes (pre-submission scratchpad).
 useEffect(()=>{saveWalkDraft(pid,date,{block:activeBlock,marks,inspector,floorChecks});},[pid,date,activeBlock,marks,inspector,floorChecks]);

 const floorKey=(b,l)=>`${b}|${l}`;
 const checksFor=(b,l)=>floorChecks[floorKey(b,l)]||template.map(()=>false);
 const floorConfirmed=(b,l)=>template.length>0&&checksFor(b,l).every(Boolean);
 const setCheck=(b,l,i,v)=>setFloorChecks(fc=>{const cur=(fc[floorKey(b,l)]||template.map(()=>false)).slice();cur[i]=v;return {...fc,[floorKey(b,l)]:cur};});

 const toggleMark=u=>{
  if(proposedIds.has(u.id))return; // server proposal already submitted — locked
  setMarks(m=>{const next={...m};if(next[u.id])delete next[u.id];else next[u.id]='fail';return next;});
 };
 const passRest=floor=>{
  if(!floorConfirmed(activeBlock,floor.level))return;
  setMarks(m=>applyFloorPass(m,floor,proposedIds));
 };

 const markedUnits=useMemo(()=>Object.keys(marks).map(id=>(data.units||[]).find(u=>u.id===id)).filter(u=>u&&u.stage===gate),[marks,data,gate]);
 if(!canWrite(user))return <div className="page-enter"><PageTitle title={t('rtoWalk')} subtitle={t('walkSub')}/><Empty text={t('noAccess')}/></div>;
 const commit=async()=>{
  if(busy||!markedUnits.length)return;
  // Group marked units by floor; a floor commits only with its checklist confirmed.
  const byFloor=new Map();
  for(const u of markedUnits){
   const k=floorKey(u.block,u.level);
   if(!byFloor.has(k))byFloor.set(k,{block:u.block,level:u.level,units:[]});
   byFloor.get(k).units.push(u);
  }
  const skipped=[...byFloor.values()].filter(f=>!floorConfirmed(f.block,f.level));
  const ready=[...byFloor.values()].filter(f=>floorConfirmed(f.block,f.level));
  if(!ready.length){toast.error(t('checklistFirst'));return;}
  const unrequested=ready.flatMap(f=>f.units).filter(u=>u.rto!=='pending');
  if(unrequested.length&&inspector.trim().length<2){toast.error(t('enterInspector'));return;}
  setBusy(true);setReport(null);
  const inspByUnit=new Map([...pendingByUnit].map(([uid,i])=>[uid,i.id]));
  let requested=0;const failedFloors=[];
  try{
   // Phase 1 — requests, one call per floor (that floor's confirmed checklist).
   for(const f of ready){
    const ids=f.units.filter(u=>u.rto!=='pending').map(u=>u.id);
    if(!ids.length)continue;
    try{
     const res=await api.post(`/projects/${pid}/rto-walk/requests`,{unit_ids:ids,inspector:inspector.trim(),date,note:'',checklist:template.map((item,i)=>({item,checked:checksFor(f.block,f.level)[i]}))});
     for(const r of res.data.results){if(r.inspection_id)inspByUnit.set(r.unit_id,r.inspection_id);if(r.status==='requested')requested++;}
    }catch{failedFloors.push(`Blk ${f.block} · L${f.level}`);}
   }
   // Phase 2 — outcomes for every marked unit that now has a pending inspection.
   const items=ready.flatMap(f=>f.units).filter(u=>inspByUnit.get(u.id)).map(u=>({inspection_id:inspByUnit.get(u.id),result:marks[u.id]==='pass'?'approved':'rework',unit_id:u.id}));
   let decidedCount=0,proposedCount=0;const doneUnits=new Set();
   if(items.length){
    try{
     if(decide){
      const officer=inspector.trim()||(pendingByUnit.get(items[0].unit_id)?.inspector)||user.name;
      const res=await api.post(`/projects/${pid}/rto-walk/decisions`,{items:items.map(({inspection_id,result})=>({inspection_id,result})),inspector:officer,note:'RTO walk'});
      const byInsp=new Map(res.data.results.map(r=>[r.inspection_id,r]));
      for(const it of items)if(byInsp.get(it.inspection_id)?.status==='decided'){decidedCount++;doneUnits.add(it.unit_id);}
     }else{
      const res=await api.post(`/projects/${pid}/rto-walk/proposals`,{items:items.map(({inspection_id,result})=>({inspection_id,result}))});
      const byInsp=new Map(res.data.results.map(r=>[r.inspection_id,r]));
      for(const it of items)if(byInsp.get(it.inspection_id)?.status==='proposed'){proposedCount++;doneUnits.add(it.unit_id);}
     }
    }catch{/* outcomes stay as local marks below */ }
   }
   // Units fully processed lose their local marks; the rest stay on this phone.
   setMarks(m=>{const next={...m};for(const id of doneUnits)delete next[id];
    // Units on failed request floors keep their marks too (not in doneUnits).
    return next;});
   setReport({requested,decided:decidedCount,proposed:proposedCount,skipped:skipped.map(f=>`Blk ${f.block} · L${f.level}`),failed:failedFloors,awaitingDecision:!decide&&proposedCount>0});
   if(decidedCount||proposedCount||requested)toast.success(t('walkDone'));
   await refresh();
  }finally{setBusy(false);}
 };

 return <div className="page-enter" data-testid="rto-walk">
  <PageTitle title={t('rtoWalk')} subtitle={gateStage?`${stageName(gateStage,t)} · ${t('walkSub')}`:t('walkSub')}>
   <Action id="walk-commit-top" onClick={commit} disabled={busy||!markedUnits.length}>{t('commitWalk')}</Action>
  </PageTitle>
  {Object.keys(marks).length>0&&<div className="walk-local-banner" data-testid="walk-local-banner"><TriangleAlert size={15}/>{t('onThisPhone')} · {Object.keys(marks).length}</div>}
  <div className="filter-chips" data-testid="walk-blocks">{blocks.map(b=><button key={b} type="button" data-testid={`walk-block-${b}`} className={activeBlock===b?'active':''} onClick={()=>setBlock(b)}>Blk {b}</button>)}</div>
  <label className="walk-inspector">{t('inspector')}<input data-testid="walk-inspector" value={inspector} onChange={e=>setInspector(e.target.value)} placeholder={t('inspector')}/></label>
  <p className="form-hint">{t('tapToFail')}</p>
  {!floors.length?<Empty text={t('noWalkUnits')}/>:<div className="walk-floors">
   {floors.map(floor=><section key={floor.level} className="walk-floor" data-testid={`walk-floor-${floor.level}`}>
    <h3>{t('level')} {floor.level} <span className="count-pill">{floor.units.length}</span></h3>
    <div className="checklist-confirm" data-testid={`walk-checklist-${floor.level}`}><h4><ClipboardCheck size={15}/>{t('rtoChecklist')}</h4>
     {template.length===0?<p className="form-hint">{t('rtoTemplateEmpty')}</p>:template.map((item,i)=><label key={i} className="check-item"><input type="checkbox" data-testid={`walk-check-${floor.level}-${i}`} checked={checksFor(activeBlock,floor.level)[i]} onChange={e=>setCheck(activeBlock,floor.level,i,e.target.checked)}/><span>{item}</span></label>)}
    </div>
    <div className="walk-units">
     {floor.units.map(u=>{
      const proposed=proposedIds.has(u.id);
      const insp=pendingByUnit.get(u.id);
      const mark=marks[u.id];
      const sub=proposed?t('proposedAwaiting'):insp?t('awaitingDecision'):u.rto==='rework'?t('rework'):t('notRequestedYet');
      return <button key={u.id} type="button" data-testid={`walk-unit-${u.id}`} className={`walk-unit${mark?' '+mark:''}${proposed?' locked':''}`} disabled={proposed} onClick={()=>toggleMark(u)}>
       <span className="walk-unit-label">{label(u)}</span>
       <span className="walk-unit-sub">{sub}{insp?.proposed_by?` · ${insp.proposed_by.name}`:''}</span>
       {proposed?<Lock size={14}/>:mark==='pass'?<span className="walk-mark pass"><Check size={13}/>{t('passMark')}</span>:mark==='fail'?<span className="walk-mark fail">{t('failMark')}</span>:null}
      </button>;
     })}
    </div>
    <button type="button" className="attend-submit small" data-testid={`walk-pass-rest-${floor.level}`} disabled={!floorConfirmed(activeBlock,floor.level)} onClick={()=>passRest(floor)}><Footprints size={15}/>{t('floorPassRest')}</button>
    {!floorConfirmed(activeBlock,floor.level)&&template.length>0&&<p className="form-hint">{t('checklistFirst')}</p>}
   </section>)}
  </div>}
  {report&&<div className="walk-report" data-testid="walk-report">
   {report.requested>0&&<p>{t('saved')}: {report.requested} · {t('awaitingDecision')}</p>}
   {report.decided>0&&<p>{t('walkDone')}: {report.decided}</p>}
   {report.awaitingDecision&&<p data-testid="walk-awaiting-decider"><strong>{t('awaitingDecider')}</strong></p>}
   {report.proposed>0&&!report.awaitingDecision&&<p>{t('proposedAwaiting')}: {report.proposed}</p>}
   {report.skipped.map(s=><p key={s} className="form-hint">{s} — {t('checklistFirst')}</p>)}
   {report.failed.map(s=><p key={s} className="form-hint">{s} — {t('onThisPhone')}</p>)}
  </div>}
  <div className="walk-commit-bar"><Action id="walk-commit" onClick={commit} disabled={busy||!markedUnits.length}>{busy?t('save'):t('commitWalk')}</Action></div>
 </div>;
}
