import { useEffect, useRef, useState } from 'react';
import { getHealth } from '../search.js';

export function useHealth() {
  const [health, setHealth] = useState({ status: 'checking', data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  const controller = useRef(null);
  const failures = useRef(0);

  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    setHealth({ status: 'checking', data: null, error: null });
    getHealth(current.signal).then(data => {
      if (!current.signal.aborted) { failures.current = 0; setHealth({ status: 'ready', data, error: null }); }
    }).catch(error => {
      if (!current.signal.aborted) setHealth({ status: 'error', data: null, error });
    });
    return () => current.abort();
  }, [attempt]);

  useEffect(() => {
    if (health.status !== 'error') return;
    const recover = () => setAttempt(value => value+1);
    const timer = setTimeout(recover,Math.min(30000,2000 * 2 ** Math.min(failures.current++,4)));
    window.addEventListener('online',recover);
    window.addEventListener('focus',recover);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('online',recover);
      window.removeEventListener('focus',recover);
    };
  }, [health.status,attempt]);

  const retry = () => {
    controller.current?.abort();
    setHealth({ status: 'checking', data: null, error: null });
    setAttempt(value => value + 1);
  };
  return { health, retry };
}
