import {NavLink} from 'react-router-dom';
import {LayoutDashboard,Grid2X2,OctagonAlert,ListChecks,ClipboardCheck} from 'lucide-react';
import {useLanguage} from '../lib/i18n';
import {useAuth} from '../lib/auth';
import './TabBar.css';
const tabs=[['overview','/',LayoutDashboard],['units','/units',Grid2X2],['defects','/defects',OctagonAlert],['tasks','/tasks',ListChecks],['inspections','/inspections',ClipboardCheck]];
export const TabBar=()=>{
 const {t}=useLanguage();const {user}=useAuth();
 const visible=tabs.filter(([key])=>user?.role==='worker'?['overview','units','defects','tasks'].includes(key):true);
 return <nav className="tab-bar" data-testid="tab-bar">{visible.map(([key,path,Icon])=><NavLink key={key} end={path==='/'} to={path} data-testid={`tab-${key}`} className={({isActive})=>`tab-link ${isActive?'active':''}`}><Icon size={21}/><span>{t(user?.role==='worker'&&key==='overview'?'home':key)}</span></NavLink>)}</nav>;
};
