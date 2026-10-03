import {useState,useEffect,useCallback} from 'react';
import {useNavigate} from 'react-router-dom';
import {Bell,ArrowUpRight} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {useWorkspace} from '../lib/store';
import {api,errorText} from '../lib/api';

/** Header bell: unread badge (60s poll) + dropdown of notifications. */
export function NotificationsBell(){
 const {t}=useLanguage();const navigate=useNavigate();const {data}=useWorkspace();
 const [open,setOpen]=useState(false),[count,setCount]=useState(0),[items,setItems]=useState([]);
 const loadCount=useCallback(()=>api.get('/notifications/unread-count').then(r=>setCount(r.data.count)).catch(()=>{}),[]);
 useEffect(()=>{loadCount();const id=setInterval(loadCount,60000);return ()=>clearInterval(id);},[loadCount]);
 const toggle=async()=>{
  const next=!open;setOpen(next);
  if(next){try{const {data:d}=await api.get('/notifications');setItems(d);}catch(e){/* ignore */}}
 };
 const openItem=async n=>{
  try{await api.post(`/notifications/${n.id}/read`);}catch(e){/* ignore */}
  setItems(list=>list.map(x=>x.id===n.id?{...x,read:true}:x));setCount(c=>Math.max(0,c-1));setOpen(false);
  const page=n.link?.page;
  if(page==='defects')navigate('/defects',{state:{openId:n.link.id}});
  else if(page==='tasks')navigate('/tasks',{state:{openId:n.link.id}});
  else if(page==='inspections')navigate('/inspections');
 };
 const pending=data?.inspections.filter(i=>i.status==='pending').length||0;
 return <div className="alert-anchor">
  <button className="icon-button" data-testid="notifications-button" title={t('notificationsTitle')} onClick={toggle}><Bell size={19}/>{count>0&&<i className="notification-dot" data-testid="notifications-badge"/>}</button>
  {open&&<div className="notification-popover" data-testid="notifications-popover">
   <h3>{t('notificationsTitle')}{count>0&&<span className="count-pill">{count}</span>}</h3>
   <div className="notification-list">{items.length?items.slice(0,12).map(n=><button key={n.id} data-testid={`notification-${n.id}`} className={`notification-item ${n.read?'':'unread'}`} onClick={()=>openItem(n)}><div><strong>{n.title}</strong><small>{n.body}</small><time>{new Date(n.created_at).toLocaleString()}</time></div></button>):<p className="empty">{t('noNotifications')}</p>}</div>
   <div className="notification-alerts">
    <button data-testid="alert-inspections" onClick={()=>{setOpen(false);navigate('/inspections');}}>{t('pendingRto')}<b>{pending}</b><ArrowUpRight size={15}/></button>
    <button data-testid="alert-materials" onClick={()=>{setOpen(false);navigate('/materials');}}>{t('lowStock')}<b>{data?.materials.filter(m=>m.stock<m.minimum).length||0}</b><ArrowUpRight size={15}/></button>
   </div>
  </div>}
 </div>;
}
