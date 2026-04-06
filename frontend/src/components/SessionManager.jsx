import { useEffect, useRef } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { getLocalStorageItem } from "../lib/storage";
import { SESSION_TOKEN_KEY, clearSession } from "../lib/session";

/**
 * Enforces session TTL after login (interval + tab focus) and clears stale auth
 * when session_token is missing or expired. Must render inside BrowserRouter.
 */
export default function SessionManager() {
  const navigate = useNavigate();
  const location = useLocation();
  const pathnameRef = useRef(location.pathname);
  pathnameRef.current = location.pathname;

  useEffect(() => {
    const checkAndLogoutIfExpired = () => {
      const hadAuth = !!localStorage.getItem("auth");
      const token = getLocalStorageItem(SESSION_TOKEN_KEY);
      if (hadAuth && !token) {
        clearSession();
        if (pathnameRef.current !== "/") {
          navigate("/", { replace: true });
        }
      }
    };

    checkAndLogoutIfExpired();
    const intervalId = window.setInterval(checkAndLogoutIfExpired, 30 * 1000);

    const onVisibility = () => {
      if (!document.hidden) checkAndLogoutIfExpired();
    };
    document.addEventListener("visibilitychange", onVisibility);

    const onStorage = (e) => {
      if (e.key === SESSION_TOKEN_KEY || e.key === "auth") {
        checkAndLogoutIfExpired();
      }
    };
    window.addEventListener("storage", onStorage);

    return () => {
      clearInterval(intervalId);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("storage", onStorage);
    };
  }, [navigate]);

  return null;
}
