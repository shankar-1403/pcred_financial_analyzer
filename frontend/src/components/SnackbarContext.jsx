import { createContext, useContext } from "react";

export const SnackbarNotificationContext = createContext({
  showSnackbar: () => {
    throw new Error("showSnackbar must be used within StackedSnackbarProvider");
  }
});

export const useSnackbar = () => {
  const context = useContext(SnackbarNotificationContext);
  if (!context) {
    throw new Error('useSnackbar must be used within a StackedSnackbarProvider');
  }
  return context;
};