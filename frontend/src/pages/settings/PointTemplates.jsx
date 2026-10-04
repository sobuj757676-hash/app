import {useState,useEffect,useMemo} from 'react';
import {useNavigate,useParams,Navigate} from 'react-router-dom';
import {Save,Plus,X,ChevronRight,ChevronLeft} from 'lucide-react';
import {useWorkspace} from '../../lib/store';
import {useLanguage} from '../../lib/i18n';
import {useAuth,canProjects} from '../../lib/auth';
import {Action} from '../../components/Common';
import {api,errorText} from '../../lib/api';
import {toast} from 'sonner';
import {ROOM_TYPES,POINT_KINDS,Stepper} from '../../components/BlockModal';
import {SubHeader} from './shared';

const countOf=r=>Number(r.count)||0;
const totalOf=rows=>rows.reduce((s,r)=>s+countOf(r),0);
const kindsOf=rows=>POINT_KINDS.map(k=>({kind:k,n:rows.filter(r=>r.kind===k).reduce((s,r)=>s+countOf(r),0)})).filter(x=>x.n>0);

function groupsOf(rows){
 const groups=[];
 rows.forEach((r,i)=>{
  const name=(r.room||'').trim();
  let g=groups.find(g=>g.name===name);
  if(!g){g={name,idx:[]};groups.push(g);}
  g.idx.push(i);
 });
 return groups;
}

export default function PointTemplates(){
 const {t}=useLanguage();const {data}=useWorkspace();const navigate=useNavigate();
 const templates=data.project.point_templates||{};
 return <div className="page-enter">
  <SubHeader title={t('pointTemplates')} subtitle={t('tplCardsSub')}/>
  <div className="tpl-cards" data-testid="tpl-cards">
   {ROOM_TYPES.map(rt=>{
    const rows=templates[rt]||[];const total=totalOf(rows);const kinds=kindsOf(rows);
    return <button key={rt} type="button" data-testid={`tpl-card-${rt}`} className="tpl-card" onClick={()=>navigate(`/settings/point-templates/${rt}`)}>
     <span className="tpl-card-top"><b>{t(rt)}</b><span className="tpl-card-total">{total} {t('points')}</span></span>
     <span className="tpl-card-kinds">{kinds.length?kinds.map(k=>`${t(k.kind)} ${k.n}`).join(' · '):t('noPoints')}</span>
     <ChevronRight size={17} className="tpl-card-chevron"/>
    </button>;
   })}
  </div>
 </div>;
}

export function PointTemplateEditor(){
 const {t}=useLanguage();const {data,pid,refresh}=useWorkspace();const {user}=useAuth();const proj=canProjects(user);
 const {roomType}=useParams();const navigate=useNavigate();
 const valid=ROOM_TYPES.includes(roomType);
 const saved=useMemo(()=>data.project.point_templates||{},[data.project]);
 const initial=useMemo(()=>saved[roomType]||[],[saved,roomType]);
 const [rows,setRows]=useState(initial),[busy,setBusy]=useState(false);
 useEffect(()=>setRows(saved[roomType]||[]),[saved,roomType]);
 if(!valid)return <Navigate to="/settings/point-templates" replace/>;
 const dirty=JSON.stringify(rows)!==JSON.stringify(initial);
 const groups=groupsOf(rows);
 const total=totalOf(rows);
 const editRow=(i,patch)=>setRows(rs=>rs.map((r,j)=>j===i?{...r,...patch}:r));
 const delRow=i=>setRows(rs=>rs.filter((_,j)=>j!==i));
 const renameGroup=(oldName,next)=>setRows(rs=>rs.map(r=>(r.room||'').trim()===oldName?{...r,room:next}:r));
 const addPoint=name=>setRows(rs=>[...rs,{room:name,kind:'power',count:1}]);
 const addRoom=()=>setRows(rs=>[...rs,{room:'',kind:'power',count:1}]);
 const save=async()=>{if(!proj||busy)return;setBusy(true);try{await api.put(`/projects/${pid}/settings/point-templates`,{templates:{...saved,[roomType]:rows}});await refresh();toast.success(t('templateUpdated'));}catch(e){toast.error(errorText(e));}finally{setBusy(false);}};
 return <div className="page-enter">
  <button type="button" className="settings-back" data-testid="settings-back" onClick={()=>navigate('/settings/point-templates')}>
   <ChevronLeft size={17}/>{t('back')}
  </button>
  <div className="tpl-editor-head">
   <div><h1 data-testid="tpl-editor-title">{t(roomType)}</h1><p data-testid="tpl-editor-total">{total} {t('points')}{dirty&&<span className="dirty-badge">{t('unsavedChanges')}</span>}</p></div>
  </div>
  <div data-testid="tpl-editor">
   {!rows.length&&<p className="section-sub">{t('noPoints')}</p>}
   {groups.map((g,gi)=><div key={`${g.name}-${gi}`} className="tpl-group" data-testid={`tpl-group-${gi}`}>
    <div className="tpl-group-head">
     <input type="text" data-testid={`tpl-room-name-${gi}`} className="tpl-group-name" placeholder={t('room')} value={g.name} maxLength={40} disabled={!proj} onChange={e=>renameGroup(g.name,e.target.value)}/>
     <span className="tpl-group-total">{g.idx.reduce((s,i)=>s+countOf(rows[i]),0)} {t('points')}</span>
    </div>
    {g.idx.map(i=>{const r=rows[i];return <div key={i} className="tpl-mini-row" data-testid={`tpl-row-${i}`}>
     <select data-testid={`tpl-kind-${i}`} value={r.kind} disabled={!proj} onChange={e=>editRow(i,{kind:e.target.value})}>{POINT_KINDS.map(k=><option key={k} value={k}>{t(k)}</option>)}</select>
     <Stepper value={countOf(r)} max={50} testid={`tpl-count-${i}`} onChange={v=>editRow(i,{count:v})}/>
     {proj&&<button type="button" className="icon-button" data-testid={`tpl-del-${i}`} onClick={()=>delRow(i)}><X size={15}/></button>}
    </div>;})}
    {proj&&<button type="button" className="tpl-add-point" data-testid={`tpl-add-point-${gi}`} onClick={()=>addPoint(g.name)}><Plus size={14}/>{t('addPoint')}</button>}
   </div>)}
   {proj&&<div className="tpl-editor-actions">
    <button type="button" className="tpl-add-room" data-testid="tpl-add-room" onClick={addRoom}><Plus size={15}/>{t('addRoom')}</button>
    <Action id="tpl-save" icon={Save} disabled={busy} onClick={save}>{t('save')}</Action>
   </div>}
  </div>
 </div>;
}
