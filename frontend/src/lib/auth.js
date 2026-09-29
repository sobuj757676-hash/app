import {createContext,useContext,useState,useEffect,useCallback} from 'react';
import {api} from './api';
const Context=createContext(null);
export function AuthProvider({children}){
 const [token,setTokenState]=useState(()=>localStorage.getItem('voltcraft-token')||'');
 const [user,setUser]=useState(null);
 const [ready,setReady]=useState(false);
 const setToken=t=>{setTokenState(t);if(t)localStorage.setItem('voltcraft-token',t);else localStorage.removeItem('voltcraft-token');};
 const logout=useCallback(()=>{setToken('');setUser(null);},[]);
 const login=async(identifier,password)=>{
  const {data}=await api.post('/auth/login',{identifier,password});
  setToken(data.token);setUser(data.user);return data.user;
 };
 const changePassword=async(current_password,new_password)=>{
  await api.post('/auth/change-password',{current_password,new_password});
  setUser(u=>u?{...u,must_change_password:false}:u);
 };
 useEffect(()=>{(async()=>{
  if(!token){setReady(true);return;}
  try{const {data}=await api.get('/auth/me');setUser(data);}
  catch{setToken('');setUser(null);}
  setReady(true);
 })();},[token]);
 return <Context.Provider value={{user,token,ready,login,logout,changePassword}}>{children}</Context.Provider>;
}
export const useAuth=()=>useContext(Context);
// Role permission helpers (progressive enhancement — the API is the real guard)
export const canWrite=u=>['admin','manager','engineer','supervisor'].includes(u?.role);
export const canDecideRto=u=>['admin','manager','engineer'].includes(u?.role);
export const canMoney=u=>['admin','manager'].includes(u?.role);
export const canProjects=u=>['admin','manager'].includes(u?.role);
export const canUsers=u=>['admin','manager'].includes(u?.role);
export const isWorker=u=>u?.role==='worker';
export const isViewer=u=>u?.role==='viewer';
