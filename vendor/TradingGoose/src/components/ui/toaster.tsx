import React from 'react';
import { useToast } from "@/hooks/use-toast";

export type ToastProps = {
  variant?: 'default' | 'destructive';
  className?: string;
};

export type ToastActionElement = React.ReactElement;

export function Toaster() {
  const { toasts, dismiss } = useToast();

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto p-4 rounded-lg shadow-lg border text-sm transition-all ${
            toast.variant === 'destructive'
              ? 'bg-destructive text-destructive-foreground border-destructive/50'
              : 'bg-card text-card-foreground border-border'
          }`}
          onClick={() => dismiss(toast.id)}
        >
          {toast.title && <div className="font-semibold">{toast.title}</div>}
          {toast.description && (
            <div className="text-xs opacity-90 mt-1">{toast.description}</div>
          )}
          {toast.action}
        </div>
      ))}
    </div>
  );
}
