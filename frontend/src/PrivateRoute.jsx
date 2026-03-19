import { Navigate } from "react-router-dom";

function PrivateRoute({ children }) {
  const token = localStorage.getItem("session_token");

  return token ? children : <Navigate to="/" />;
}

export default PrivateRoute;