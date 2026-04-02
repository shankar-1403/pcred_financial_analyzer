import { useRef, useState } from 'react'
import TextField from '@mui/material/TextField';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { useSnackbar } from '../components/SnackbarContext';

function Login() {
  const navigate = useNavigate();
  const { showSnackbar } = useSnackbar();
  const loginRef = useRef(null);
  const registerRef = useRef(null);
  const [loginLoading,setLoginLoading] = useState(false);
  const [registerLoading,setRegisterLoading] = useState(false);
  const [loginTab, setLoginTab] = useState(true);

  const SESSION_TTL_MS = 2 * 60 * 60 * 1000;
  const SESSION_TOKEN_KEY = "session_token";
  
  function setLocalStorageItem(key, value, ttlInMs) {
    const now = new Date();
    const item = {
      value: value,
      expiry: ttlInMs ? now.getTime() + ttlInMs : null,
    };
    localStorage.setItem(key, JSON.stringify(item));
  }

  function getLocalStorageItem(key) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function isExpiredStoredItem(key) {
    const item = getLocalStorageItem(key);
    if (!item) return true;
    if (item.expiry == null) return false;
    return Date.now() >= Number(item.expiry);
  }

  function createSessionToken() {
    // Cryptographically-strong random token (browser runtime)
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  }

  function logoutNow(redirectWithNavigate = false) {
    localStorage.removeItem("auth");
    localStorage.removeItem("name");
    localStorage.removeItem(SESSION_TOKEN_KEY);
    if (redirectWithNavigate) {
      navigate("/", { replace: true });
      return;
    }
    // Fallback (should be rare)
    window.location.href = "/";
  }

  function startSessionWatcher() {
    // Prevent multiple watchers in same tab
    if (window.__pcredSessionWatcherStarted) return;
    window.__pcredSessionWatcherStarted = true;

    const checkAndLogoutIfExpired = () => {
      if (isExpiredStoredItem(SESSION_TOKEN_KEY)) {
        logoutNow(true);
      }
    };

    // Check immediately, then periodically (covers sleep/wake without refresh)
    checkAndLogoutIfExpired();
    window.__pcredSessionIntervalId = window.setInterval(checkAndLogoutIfExpired, 30 * 1000);

    // Re-check when user returns to tab
    window.addEventListener("visibilitychange", () => {
      if (!document.hidden) checkAndLogoutIfExpired();
    });

    // Multi-tab: if another tab logs out, react here too
    window.addEventListener("storage", (e) => {
      if (e.key === SESSION_TOKEN_KEY || e.key === "auth") checkAndLogoutIfExpired();
    });
  }

  const formLogin = async(e) => {
    e.preventDefault();
    setLoginLoading(true);
    try{
      const payload = {
        email_id: loginRef.current.elements.namedItem("email_id").value,
        password: loginRef.current.elements.namedItem("password").value,
      }

      const response = await axios.post(`${import.meta.env.VITE_API_URL}/auth/login`,payload,{
        headers: {
          "Content-Type": "application/json",
        },
      });
      if(response.data.status == 200){
        navigate("/dashboard");
        localStorage.setItem("auth",response.data.email_id);
        localStorage.setItem("name",response.data.company_name);
        setLocalStorageItem(SESSION_TOKEN_KEY, createSessionToken(), SESSION_TTL_MS);
        startSessionWatcher();
        showSnackbar(response.data.message,"success");
      }else{
        showSnackbar(response.data.message,"error");
      }
    } catch(error){
      console.log(error);
    } finally{
      setLoginLoading(false)
    }
  }

  const formRegister = async(e) => {
    e.preventDefault();
    setRegisterLoading(true);
    try{
      const payload = {
        full_name: registerRef.current.elements.namedItem("full_name").value,
        email_id: registerRef.current.elements.namedItem("email_id").value,
        password: registerRef.current.elements.namedItem("password").value,
      }

      const response = await axios.post(`${import.meta.env.VITE_API_URL}/auth/register`,payload,
      {
        headers: {
          "Content-Type": "application/json",
        },
      });
      if(response.data.status == 200){
        navigate("/dashboard");
        localStorage.setItem("auth",response.data.email_id);
        localStorage.setItem("name",response.data.company_name);
        setLocalStorageItem(SESSION_TOKEN_KEY, createSessionToken(), SESSION_TTL_MS);
        startSessionWatcher();
      }else{
        console.log(response.message)
      }
    } catch(error){
      console.log(error);
    } finally{
      setRegisterLoading(false)
    }
  }
  return (
    <>
      <div className="flex justify-center items-center h-screen">
        {loginTab ?
          <div className='p-8 rounded-2xl shadow-2xl w-100'>
            <form ref={loginRef} onSubmit={formLogin}>
              <h1 className='text-2xl font-bold mb-8'>{loginTab ? 'Sign in to PCRED' : 'Sign Up to PCRED'}</h1>
              <div className="grid grid-cols-2 gap-7 mb-4">
                <div className="col-span-2">
                  <TextField label='Email ID' name='email_id' fullWidth size='small'/>
                </div>
                <div className="col-span-2">
                  <TextField label='Password' name='password' fullWidth size='small'/>
                </div>
                <div className="col-span-1">
                  <div className="flex items-center gap-2">
                    <div>
                        <input type="checkbox" id='communication_preference' name='communication_preference' className="w-3 h-3 accent-[#084b6f] focus:ring-[#084b6f] cursor-pointer"/>
                    </div>
                    <div>
                        <label htmlFor='communication_preference' className='text-gray-700 text-sm cursor-pointer'>Remember me</label>
                    </div>
                  </div>
                </div>
                <div className="col-span-1 flex justify-end">
                  <span className='text-blue-600 underline font-semibold text-right cursor-pointer text-sm'>Forgot Password</span>
                </div>
                <div className="col-span-2">
                  <button className='uppercase bg-[#084b6f] p-2 w-full rounded-lg text-white font-semibold cursor-pointer' type='submit'>{loginLoading?"Signing In":"Sign In"}</button>
                </div>
              </div>
            </form>
            <button onClick={()=>setLoginTab(false)} className='text-blue-600 text-sm font-semibold cursor-pointer underline'>Not registered? Sign Up</button>
          </div>
          :
          <div className='p-8 rounded-2xl shadow-2xl w-100'>
            <form ref={registerRef} onSubmit={formRegister}>
              <h1 className='text-2xl font-bold mb-8'>Sign Up to PCRED</h1>
              <div className="grid grid-cols-2 gap-7 mb-4">
                <div className="col-span-2">
                  <TextField label='Name' name='full_name' fullWidth size='small'/>
                </div>
                <div className="col-span-2">
                  <TextField label='Email ID' name='email_id' fullWidth size='small'/>
                </div>
                <div className="col-span-2">
                  <TextField label='Password' name='password' fullWidth size='small'/>
                </div>
                <div className="col-span-1">
                  <div className="flex items-center gap-2">
                    <div>
                        <input type="checkbox" id='communication_preference' name='communication_preference' className="w-3 h-3 accent-[#084b6f] focus:ring-[#084b6f] cursor-pointer"/>
                    </div>
                    <div>
                        <label htmlFor='communication_preference' className='text-gray-700 text-sm cursor-pointer'>Remember me</label>
                    </div>  
                  </div>
                </div>
                <div className="col-span-2">
                  <button className='uppercase bg-[#084b6f] p-2 w-full rounded-lg text-white font-semibold cursor-pointer' type='submit'>{registerLoading?"Signing Up":"Sign Up"}</button>
                </div>
              </div>  
            </form>
            <button onClick={()=>setLoginTab(true)} className='text-blue-600 text-sm font-semibold cursor-pointer underline'>Already Registered? Sign In</button>
          </div>
        }
      </div>
    </>
  )
}

export default Login