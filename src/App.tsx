import React from 'react';
import { TradingProvider, useTrading } from './context/TradingContext';
import { AndroidStatusBar } from './components/AndroidStatusBar';
import { TopAppBar } from './components/TopAppBar';
import { IndexSelector } from './components/IndexSelector';
import { BottomNavBar } from './components/BottomNavBar';
import { NavigationDrawer } from './components/NavigationDrawer';

import { DashboardPage } from './pages/DashboardPage';
import { MarketPage } from './pages/MarketPage';
import { OptionChainPage } from './pages/OptionChainPage';
import { SignalsPage } from './pages/SignalsPage';
import { QuantEngineLabPage } from './pages/QuantEngineLabPage';
import { BrokerHomePage } from './pages/BrokerHomePage';
import { IndicatorsPage } from './pages/IndicatorsPage';
import { OILabPage } from './pages/OILabPage';
import { RiskPage } from './pages/RiskPage';
import { BacktestingPage } from './pages/BacktestingPage';
import { MarketIntelligencePage } from './pages/MarketIntelligencePage';
import { DataHealthPage } from './pages/DataHealthPage';
import { ApiSettingsPage } from './pages/ApiSettingsPage';
import { SettingsPage } from './pages/SettingsPage';

const MainContent: React.FC = () => {
  const { activeTab } = useTrading();

  const renderCurrentView = () => {
    switch (activeTab) {
      case 'Dashboard':
        return <DashboardPage />;
      case 'Market':
        return <MarketPage />;
      case 'Option Chain':
        return <OptionChainPage />;
      case 'Signals':
        return <SignalsPage />;
      case '5-Layer Quant':
        return <QuantEngineLabPage />;
      case 'Paper Trading':
        return <BrokerHomePage />;
      case 'Indicators':
        return <IndicatorsPage />;
      case 'OI Lab':
        return <OILabPage />;
      case 'Risk Calculator':
        return <RiskPage />;
      case 'Backtesting':
      case 'Strategy Library':
        return <BacktestingPage />;
      case 'Market Intelligence':
      case 'AI Memory':
        return <MarketIntelligencePage />;
      case 'Data Health':
        return <DataHealthPage />;
      case 'Settings':
      case 'API Settings':
        return <SettingsPage />;
      default:
        return <DashboardPage />;
    }
  };

  return (
    <div className="flex flex-col min-h-screen bg-[#070B12] text-slate-100 antialiased overflow-x-hidden font-sans">
      {/* Android System Status Bar */}
      <AndroidStatusBar />

      {/* Material 3 Top App Bar */}
      <TopAppBar />

      {/* Index Selector (NIFTY, BANKNIFTY, etc.) */}
      <IndexSelector />

      {/* Main Screen Content View */}
      <main className="flex-1 overflow-y-auto">
        {renderCurrentView()}
      </main>

      {/* Android Bottom Navigation Bar */}
      <BottomNavBar />

      {/* Android Drawer Menu with All 25 Modules */}
      <NavigationDrawer />
    </div>
  );
};

export default function App() {
  return (
    <TradingProvider>
      <MainContent />
    </TradingProvider>
  );
}
