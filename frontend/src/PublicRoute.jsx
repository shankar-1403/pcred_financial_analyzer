import { Navigate } from "react-router-dom";
import { getLocalStorageItem } from "./lib/storage";
import { SESSION_TOKEN_KEY } from "./lib/session";

function PublicRoute({ children }) {
  const token = getLocalStorageItem(SESSION_TOKEN_KEY);

  return token ? <Navigate to="/dashboard" replace /> : children;
}

export default PublicRoute;