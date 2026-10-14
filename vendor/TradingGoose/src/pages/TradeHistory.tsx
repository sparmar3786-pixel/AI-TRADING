import React from 'react';
import { Link } from 'react-router-dom';
import Header from '@/components/Header';
import Footer from '@/components/Footer';
import TradeHistoryTable from '@/components/TradeHistoryTable';
import TradeAnalyticsSection from '@/components/TradeAnalyticsSection';
import FirebaseStatusBanner from '@/components/FirebaseStatusBanner';
import { TrendingUp, Sparkles } from 'lucide-react';
import { useAuth } from '@/lib/auth';

export default function TradeHistory() {
  const { isAuthenticated, isLoading } = useAuth();

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />
      
      <main className="flex-1 container mx-auto px-4 sm:px-6 py-8 max-w-7xl">
        <div className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-2 tracking-tight">
              <TrendingUp className="h-8 w-8 text-[#fc0]" />
              Trade History & Performance
            </h1>
            <p className="text-muted-foreground mt-1 text-sm">
              Comprehensive historical trading performance, cumulative PnL curve, win/loss distributions, and execution logs.
            </p>
          </div>

          {!isAuthenticated && !isLoading && (
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-muted/40 border border-border/50 text-xs">
              <Sparkles className="h-4 w-4 text-[#fc0] shrink-0" />
              <span>
                Viewing simulated benchmark trade history.{' '}
                <Link to="/login" className="text-primary hover:underline font-semibold">
                  Sign in
                </Link>{' '}
                for live broker sync.
              </span>
            </div>
          )}
        </div>
        
        {/* Firebase Firestore Database Banner */}
        <div className="mb-6">
          <FirebaseStatusBanner />
        </div>

        {/* Recharts Cumulative PnL Container & Win/Loss Ratio Analytics */}
        <TradeAnalyticsSection />

        {/* Detailed Trades Log Table with DateRangePicker */}
        <div className="mt-8">
          <TradeHistoryTable />
        </div>
      </main>
      
      <Footer />
    </div>
  );
}