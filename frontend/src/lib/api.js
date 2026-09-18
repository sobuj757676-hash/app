import axios from 'axios';
export const api = axios.create({ baseURL: `${process.env.REACT_APP_BACKEND_URL}/api` });
export const today = () => new Intl.DateTimeFormat('en-CA', {timeZone:'Asia/Singapore',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
export const money = n => new Intl.NumberFormat('en-SG', { style: 'currency', currency: 'SGD', maximumFractionDigits: 2, minimumFractionDigits: 0 }).format(n || 0);
export const label = u => `#${String(u.level).padStart(2,'0')}-${u.number}`;
export const percent = units => units.length ? Math.round(units.reduce((n,u)=>n+u.stage,0)/(units.length*9)*100) : 0;
export const status = u => u.rto === 'rework' ? 'rework' : u.stage === 9 ? 'completed' : u.rto === 'pending' ? 'pending' : u.stage === 0 ? 'notStarted' : 'inProgress';
export const errorText = e => { const d=e.response?.data?.detail; return typeof d==='string'?d:Array.isArray(d)?d.map(x=>`${x.loc.at(-1)}: ${x.msg}`).join('; '):'Connection error. Please try again.'; };
export async function download(pid,kind) { const {data}=await api.get(`/projects/${pid}/export/${kind}`,{responseType:'blob'});const url=URL.createObjectURL(data);const a=document.createElement('a');a.href=url;a.download=`voltcraft-${kind}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }