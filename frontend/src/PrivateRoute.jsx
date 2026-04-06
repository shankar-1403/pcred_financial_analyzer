import { Navigate } from "react-router-dom";
import { getLocalStorageItem } from "./lib/storage";
import { SESSION_TOKEN_KEY } from "./lib/session";

function PrivateRoute({ children }) {
  const token = getLocalStorageItem(SESSION_TOKEN_KEY);

  return token ? children : <Navigate to="/" replace />;
}

export default PrivateRoute;