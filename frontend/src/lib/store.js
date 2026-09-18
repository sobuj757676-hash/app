import {createContext,useContext,useState,useEffect,useCallback} from 'react';
import {api,errorText} from './api';
import {toast} from 'sonner';
const Context=createContext(null);
export function WorkspaceProvider({children}) {
 const [projects,setProjects]=useState([]),[pid,setPid]=useState(localStorage.getItem('voltcraft-project')||''),[data,setData]=useState(null),[error,setError]=useState(''),[selectedUnit,setSelectedUnit]=useState(null);
 const loadProjects=useCallback(async()=>{const {data:p}=await api.get('/projects');setProjects(p);setPid(id=>p.some(x=>x.id===id)?id:p[0]?.id||'');return p;},[]);
 useEffect(()=>{loadProjects().catch(e=>setError(errorText(e)));},[loadProjects]);
 const refresh=useCallback(async()=>{if(!pid)return; try {const {data:d}=await api.get(`/projects/${pid}/workspace`);setData(d);setError('');}catch(e){setError(errorText(e));}},[pid]);
 useEffect(()=>{setData(null);refresh();localStorage.setItem('voltcraft-project',pid);},[pid,refresh]);
 const mutate=async(method,url,payload)=>{try{const res=await api[method](url,payload);await refresh();return res.data;}catch(e){toast.error(errorText(e));throw e;}};
 return <Context.Provider value={{projects,pid,setPid,data,error,refresh,loadProjects,mutate,selectedUnit,setSelectedUnit}}>{children}</Context.Provider>;
}
export const useWorkspace=()=>useContext(Context);