import { useEffect, useRef, useState } from 'react';
import { getHealth } from '../search.js';

export function useHealth() {
  const [health, setHealth] = useState({ status: 'checking', data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  const controller = useRef(null);

  useEffect(() => {
    const current = new AbortController();
    controller.current = current;
    setHealth({ status: 'checking', data: null, error: null });
    getHealth(current.signal).then(data => {
      if (!current.signal.aborted) setHealth({ status: 'ready', data, error: null });
    }).catch(error => {
      if (!current.signal.aborted) setHealth({ status: 'error', data: null, error });
    });
    return () => current.abort();
  }, [attempt]);

  const retry = () => {
    controller.current?.abort();
    setHealth({ status: 'checking', data: null, error: null });
    setAttempt(value => value + 1);
  };
  return { health, retry };
}
