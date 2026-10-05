import {useEffect,useRef} from 'react';
import {BrowserRouter,Routes,Route,Navigate,useLocation} from 'react-router-dom';
import {LanguageProvider,useLanguage} from './lib/i18n';
import {AuthProvider,useAuth} from './lib/auth';
import {WorkspaceProvider} from './lib/store';
import {setOnUnauthorized} from './lib/api';
import {toast} from 'sonner';
import {Toaster} from './components/ui/sonner';
import {Layout} from './components/Layout';
import {ForceChangePassword} from './pages/Login';
import Overview from './pages/Overview';
import WorkerHome from './pages/WorkerHome';
import UnitTracker from './pages/UnitTracker';
import Inspections from './pages/Inspections';
import Defects from './pages/Defects';
import Tasks from './pages/Tasks';
import Testing from './pages/Testing';
import Workforce from './pages/Workforce';
import Materials from './pages/Materials';
import Expenses from './pages/Expenses';
import Projects from './pages/Projects';
import Reports from './pages/Reports';
import References from './pages/References';
import Settings from './pages/Settings';
import ProjectSettings from './pages/settings/ProjectSettings';
import RtoChecklist from './pages/settings/RtoChecklist';
import PointTemplates,{PointTemplateEditor} from './pages/settings/PointTemplates';
import PasswordSettings from './pages/settings/PasswordSettings';
import LanguageSettings from './pages/settings/LanguageSettings';
import Users from './pages/Users';
import Login from './pages/Login';
import './App.css';
import './fixes-a.css';

// Wires the api.js 401 interceptor into React state: instead of a hard page
// reload (which destroys in-progress forms), we clear the session, show a
// "session expired" toast and route to /login via the router.
function UnauthorizedWatcher(){
 const navigate=useNavigate();const {t}=useLanguage();const loc=useLocation();const {logout}=useAuth();
 const s=useRef();s.current={navigate,t,logout,pathname:loc.pathname};
 const fired=useRef(false);
 useEffect(()=>{fired.current=false;},[loc.pathname]); // re-arm on each route change
 useEffect(()=>{
  setOnUnauthorized(()=>{
   const {navigate,t,logout,pathname}=s.current;
   if(fired.current||pathname.startsWith('/login'))return;
   fired.current=true;
   logout();
   toast.error(t('sessionExpired'));
   navigate('/login',{replace:true});
  });
  return ()=>setOnUnauthorized(null);
 },[]);
 return null;
}

function DenyRedirect(){
 const {t}=useLanguage();
 useEffect(()=>{toast.info(t('noAccess'));},[t]);
 return <Navigate to="/" replace/>;
}
function RequireAuth({children}){
 const {user,ready}=useAuth();const loc=useLocation();
 if(!ready)return <div className="loading-state" data-testid="auth-loading">…</div>;
 if(!user)return <Navigate to="/login" replace/>;
 if(user.must_change_password)return <div className="login-page"><ForceChangePassword onDone={()=>window.location.reload()}/></div>;
 const {role}=user,path=loc.pathname;
 if(role==='worker'&&!['/','/units','/defects','/tasks'].includes(path))return <DenyRedirect/>;
 if(path==='/users'&&!['admin','manager'].includes(role))return <DenyRedirect/>;
 if(path==='/expenses'&&role==='supervisor')return <DenyRedirect/>;
 if(path.startsWith('/settings')&&path!=='/settings/password'&&role==='worker')return <DenyRedirect/>;
 return children;
}
function Home(){
 const {user}=useAuth();
 return user?.role==='worker'?<WorkerHome/>:<Overview/>;
}
function Shell(){
 return <Routes>
  <Route path="/login" element={<Login/>}/>
  <Route element={<RequireAuth><Layout/></RequireAuth>}>
   <Route path="/" element={<Home/>}/>
   <Route path="/projects" element={<Projects/>}/>
   <Route path="/units" element={<UnitTracker/>}/>
   <Route path="/inspections" element={<Inspections/>}/>
   <Route path="/defects" element={<Defects/>}/>
   <Route path="/tasks" element={<Tasks/>}/>
   <Route path="/testing" element={<Testing/>}/>
   <Route path="/workforce" element={<Workforce/>}/>
   <Route path="/materials" element={<Materials/>}/>
   <Route path="/expenses" element={<Expenses/>}/>
   <Route path="/reports" element={<Reports/>}/>
   <Route path="/references" element={<References/>}/>
   <Route path="/settings" element={<Settings/>}/>
   <Route path="/settings/project" element={<ProjectSettings/>}/>
   <Route path="/settings/rto-checklist" element={<RtoChecklist/>}/>
   <Route path="/settings/point-templates" element={<PointTemplates/>}/>
   <Route path="/settings/point-templates/:roomType" element={<PointTemplateEditor/>}/>
   <Route path="/settings/password" element={<PasswordSettings/>}/>
   <Route path="/settings/language" element={<LanguageSettings/>}/>
   <Route path="/users" element={<Users/>}/>
   <Route path="*" element={<Navigate to="/" replace/>}/>
  </Route>
 </Routes>;
}
function App(){return <LanguageProvider><AuthProvider><WorkspaceProvider><BrowserRouter><UnauthorizedWatcher/><Shell/><Toaster richColors position="bottom-right"/></BrowserRouter></WorkspaceProvider></AuthProvider></LanguageProvider>;}export default App;
