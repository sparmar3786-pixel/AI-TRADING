import React, { useEffect } from 'react';
import { initPostHog } from '@/lib/posthog';

interface PostHogProviderProps {
  children: React.ReactNode;
}

export function PostHogProvider({ children }: PostHogProviderProps) {
  useEffect(() => {
    initPostHog();
  }, []);

  return <>{children}</>;
}
