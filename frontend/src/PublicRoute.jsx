import { Navigate } from "react-router-dom";

function PublicRoute({ children }) {
  const token = localStorage.getItem("session_token");

  return token ?  <Navigate to="/dashboard" /> : children;
}

export default PublicRoute;