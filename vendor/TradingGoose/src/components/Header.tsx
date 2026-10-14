import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { TrendingUp, BarChart3, Clock, Settings, LogOut, User, Activity } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/lib/auth';

export default function Header() {
  const { user, signOut, isAuthenticated } = useAuth();
  const location = useLocation();

  const navLinks = [
    { name: 'Dashboard', path: '/dashboard', icon: BarChart3 },
    { name: 'Trade History', path: '/trade-history', icon: TrendingUp },
    { name: 'Analysis', path: '/analysis-records', icon: Activity },
    { name: 'Rebalance', path: '/rebalance-records', icon: Clock },
    { name: 'Settings', path: '/settings', icon: Settings },
  ];

  return (
    <header className="border-b border-border/50 bg-background/80 backdrop-blur sticky top-0 z-40">
      <div className="container mx-auto px-4 h-16 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <Link to="/dashboard" className="flex items-center gap-2 font-bold text-lg">
            <div className="h-8 w-8 rounded-lg bg-[#FFCC00] flex items-center justify-center text-black font-extrabold text-sm shadow">
              TG
            </div>
            <span className="tracking-tight hidden sm:inline">TradingGoose</span>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {navLinks.map((link) => {
              const Icon = link.icon;
              const isActive = location.pathname === link.path;
              return (
                <Link
                  key={link.path}
                  to={link.path}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-muted text-foreground font-semibold'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted/50'
                  }`}
                >
                  <Icon className="h-3.5 w-3.5" />
                  {link.name}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="flex items-center gap-3">
          {isAuthenticated ? (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground hidden lg:inline">
                {user?.email}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => signOut()}
                className="h-8 text-xs text-muted-foreground hover:text-foreground gap-1.5"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Link to="/login">
                <Button variant="ghost" size="sm" className="h-8 text-xs">
                  Login
                </Button>
              </Link>
              <Link to="/register">
                <Button size="sm" className="h-8 text-xs bg-[#FFCC00] text-black hover:bg-[#FFCC00]/90">
                  Get Started
                </Button>
              </Link>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
