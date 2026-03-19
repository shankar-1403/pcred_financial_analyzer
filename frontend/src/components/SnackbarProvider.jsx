import React, { useState, useCallback, useEffect } from 'react';
import { Alert, Stack } from '@mui/material';
import { SnackbarNotificationContext } from './SnackbarContext';

// StackedSnackbarProvider component
export function StackedSnackbarProvider({ children, defaultDuration = 5000 }) {
  const [snackbars, setSnackbars] = useState([]);

  const showSnackbar = useCallback((message, severity = 'info', options = {}) => {
    const { key = null, autoHideDuration = defaultDuration } = typeof options === 'object' ? options : { key: options };
    const id = key || (new Date().getTime() + Math.random());
    
    setSnackbars((prev) => [...prev, { 
      id, 
      message, 
      severity,
      open: true,
      createdAt: Date.now(),
      autoHideDuration
    }]);
    
    return id;
  }, [defaultDuration]);

  

  const removeSnackbar = useCallback((id) => {
    setSnackbars((prev) => prev.filter(snack => snack.id !== id));
  }, []);


  const handleClose = useCallback((id, reason) => {
    if (reason === 'clickaway') {
      return;
    }
    
    setSnackbars((prev) => 
      prev.map(snack => 
        snack.id === id ? { ...snack, open: false } : snack
      )
    );
    
    // Schedule removal after animation completes
    setTimeout(() => {
      removeSnackbar(id);
    }, 200); // Slightly longer than the transition duration
  }, []);
  // Auto-hide functionality using useEffect
  useEffect(() => {
    const timers = snackbars.map(snack => {
      if (snack.open && snack.autoHideDuration) {
        return setTimeout(() => {
          handleClose(snack.id, 'timeout');
        }, snack.autoHideDuration);
      }
      return null;
    }).filter(Boolean);
    
    // Cleanup timers on unmount or when snackbars change
    return () => {
      timers.forEach(timer => clearTimeout(timer));
    };
  }, [snackbars, handleClose]);

  return (
    <SnackbarNotificationContext.Provider value={{ showSnackbar }}>
      {children}
      <Stack 
        spacing={2} 
        sx={{ 
          position: 'fixed', 
          top: 80,
          right: 16,
          zIndex: 9999,
          width: '20em',
          alignItems: 'flex-end',
        }}
      >
        {snackbars.map((snack) => (
          <Alert 
            key={snack.id}
            onClose={() => handleClose(snack.id, 'close')} 
            severity={snack.severity} 
            variant="filled"
            sx={{ 
              boxShadow: '1px 3px 5px rgba(0, 0, 0, 0.3)',
              width: '100%',
              transition: 'all 195ms cubic-bezier(0.4, 0, 0.2, 1) 0ms',
              opacity: snack.open ? 1 : 0,
              transform: snack.open ? 'translateY(0)' : 'translateY(-20px)',
              height: snack.open ? 'auto' : '0',
              overflow: 'hidden',
              marginBottom: snack.open ? 'inherit' : '-8px',
            }}
          >
            {snack.message}
          </Alert>
        ))}
      </Stack>
    </SnackbarNotificationContext.Provider>
  );
}
