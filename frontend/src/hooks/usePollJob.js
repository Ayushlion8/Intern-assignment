import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from '../api/client';

export function usePollJob(jobId, apiKey, interval = 2000) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [polling, setPolling] = useState(false);
  const timerRef = useRef(null);

  const startPolling = useCallback(() => {
    if (!jobId || !apiKey) return;
    setPolling(true);
    setError(null);

    const poll = async () => {
      try {
        const data = await api.getJob(jobId, apiKey);
        setJob(data);
        if (data.status === 'completed' || data.status === 'failed') {
          setPolling(false);
          return;
        }
        timerRef.current = setTimeout(poll, interval);
      } catch (e) {
        setError(e);
        setPolling(false);
      }
    };

    poll();
  }, [jobId, apiKey, interval]);

  const stopPolling = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setPolling(false);
  }, []);

  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, []);

  return { job, error, polling, startPolling, stopPolling };
}
