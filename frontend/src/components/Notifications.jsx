import {useState,useEffect,useCallback,useRef} from 'react';
import {useNavigate} from 'react-router-dom';
import {Bell,ArrowUpRight} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {api,errorText,fmtDateTime} from '../lib/api';
import {toast} from 'sonner';

/** Header bell: unread badge (60s poll) + dropdown of notifications. */
export function NotificationsBell(){
 const {t,lang}=useLanguage();const navigate=useNavigate();const {data}=useWorkspace();
 const [open,setOpen]=useState(false),[count,setCount]=useState(0),[items,setItems]=useState([]);
 const anchor=useRef(null);
 const loadCount=useCallback(()=>api.get('/notifications/unread-count').then(r=>setCount(r.data.count)).catch(()=>{}),[]);
 useEffect(()=>{loadCount();const id=setInterval(loadCount,60000);return ()=>clearInterval(id);},[loadCount]);
 useEffect(()=>{if(!open)return;
  const onDown=e=>{if(anchor.current&&!anchor.current.contains(e.target))setOpen(false);};
  const onKey=e=>{if(e.key==='Escape')setOpen(false);};
  document.addEventListener('mousedown',onDown);document.addEventListener('keydown',onKey);
  return ()=>{document.removeEventListener('mousedown',onDown);document.removeEventListener('keydown',onKey);};
 },[open]);
 const toggle=async()=>{
  const next=!open;setOpen(next);
  if(next){try{const {data:d}=await api.get('/notifications');setItems(d);}catch(e){/* ignore */}}
 };
 const openItem=async n=>{
  // Optimistic read-marking, reverted on failure so the unread state never lies.
  const prevItems=items,prevCount=count;
  setItems(list=>list.map(x=>x.id===n.id?{...x,read:true}:x));setCount(c=>Math.max(0,c-1));setOpen(false);
  try{await api.post(`/notifications/${n.id}/read`);}
  catch(e){setItems(prevItems);setCount(prevCount);toast.error(errorText(e));}
  const page=n.link?.page;
  if(page==='defects')navigate(`/defects?open=${n.link.id}`);
  else if(page==='tasks')navigate(`/tasks?open=${n.link.id}`);
  else if(page==='inspections')navigate('/inspections');
 };
 const pending=data?.inspections.filter(i=>i.status==='pending').length||0;
 return <div className="alert-anchor" ref={anchor}>
  <button className="icon-button" data-testid="notifications-button" title={t('notificationsTitle')} onClick={toggle}><Bell size={19}/>{count>0&&<span className="notification-badge" data-testid="notifications-badge">{count>9?'9+':count}</span>}</button>
  {open&&<div className="notification-popover" data-testid="notifications-popover">
   <h3>{t('notificationsTitle')}{count>0&&<span className="count-pill">{count}</span>}</h3>
   <div className="notification-list">{items.length?items.slice(0,12).map(n=><button key={n.id} data-testid={`notification-${n.id}`} className={`notification-item ${n.read?'':'unread'}`} onClick={()=>openItem(n)}><div><strong>{n.title}</strong><small>{n.body}</small><time>{fmtDateTime(n.created_at,lang)}</time></div></button>):<p className="empty">{t('noNotifications')}</p>}</div>
   <div className="notification-alerts">
    <button data-testid="alert-inspections" onClick={()=>{setOpen(false);navigate('/inspections');}}>{t('pendingRto')}<b>{pending}</b><ArrowUpRight size={15}/></button>
    <button data-testid="alert-materials" onClick={()=>{setOpen(false);navigate('/materials');}}>{t('lowStock')}<b>{data?.materials.filter(m=>m.stock<m.minimum).length||0}</b><ArrowUpRight size={15}/></button>
   </div>
  </div>}
 </div>;
}
