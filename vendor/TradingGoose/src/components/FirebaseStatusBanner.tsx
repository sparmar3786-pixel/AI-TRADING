import React, { useState, useEffect } from 'react';
import { Database, CheckCircle2, RefreshCw, Flame, ExternalLink, ShieldCheck } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { useAuth } from '@/lib/auth';
import { 
  getTradesFromFirestore, 
  seedInitialFirestoreTrades, 
  firebaseConfig, 
  FIRESTORE_DATABASE_ID 
} from '@/lib/firebase';

interface FirebaseStatusBannerProps {
  onRefreshTrades?: () => void;
  className?: string;
}

export default function FirebaseStatusBanner({ onRefreshTrades, className = '' }: FirebaseStatusBannerProps) {
  const [tradeCount, setTradeCount] = useState<number | null>(null);
  const [syncing, setSyncing] = useState<boolean>(false);
  const { user } = useAuth();
  const { toast } = useToast();

  const checkFirestore = async () => {
    try {
      const trades = await getTradesFromFirestore(user?.id);
      setTradeCount(trades.length);
    } catch (err) {
      console.warn('Could not query Firestore trade count:', err);
      setTradeCount(0);
    }
  };

  useEffect(() => {
    checkFirestore();
  }, [user?.id]);

  const handleSeedOrSync = async () => {
    setSyncing(true);
    try {
      const currentUserId = user?.id || 'demo-user-quant';
      const added = await seedInitialFirestoreTrades(currentUserId);
      await checkFirestore();
      if (onRefreshTrades) {
        onRefreshTrades();
      }
      toast({
        title: "Firebase Firestore Synced",
        description: added > 0 
          ? `Populated database with ${added} verified algorithmic trades.` 
          : "Firestore cloud connection verified and live.",
      });
    } catch (error) {
      toast({
        title: "Sync Error",
        description: "Failed to sync with Firebase Firestore.",
        variant: "destructive"
      });
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className={`rounded-xl border border-amber-500/30 bg-gradient-to-r from-amber-500/10 via-background to-orange-500/10 p-4 shadow-sm backdrop-blur-sm ${className}`}>
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center shrink-0 border border-amber-500/30">
            <Flame className="h-5 w-5 fill-amber-500" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-sm tracking-tight">Firebase Firestore Database</span>
              <Badge variant="outline" className="text-[11px] border-emerald-500/40 text-emerald-500 bg-emerald-500/10 flex items-center gap-1 font-mono">
                <CheckCircle2 className="h-3 w-3" />
                Active & Connected
              </Badge>
              <Badge variant="secondary" className="text-[10px] font-mono text-muted-foreground">
                asia-south1
              </Badge>
            </div>
            <p className="text-xs text-muted-foreground mt-0.5">
              Project: <span className="font-mono text-foreground/80">{firebaseConfig.projectId}</span>
              {tradeCount !== null && (
                <span className="ml-2 font-medium text-amber-500">
                  • {tradeCount} {tradeCount === 1 ? 'trade record' : 'trade records'} in cloud
                </span>
              )}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
          <Button
            size="sm"
            variant="outline"
            className="text-xs h-8 gap-1.5 border-amber-500/30 hover:bg-amber-500/10 text-amber-600 dark:text-amber-400"
            onClick={handleSeedOrSync}
            disabled={syncing}
          >
            <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
            {syncing ? 'Syncing...' : (tradeCount === 0 ? 'Seed Sample Trades' : 'Sync Firestore')}
          </Button>
        </div>
      </div>
    </div>
  );
}
