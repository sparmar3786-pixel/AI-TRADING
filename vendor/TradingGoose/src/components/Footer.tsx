import React from 'react';
import { Link } from 'react-router-dom';

export default function Footer() {
  return (
    <footer className="border-t border-border/40 bg-muted/20 py-6 mt-auto">
      <div className="container mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-4 text-xs text-muted-foreground">
        <div className="flex items-center gap-2">
          <span>&copy; {new Date().getFullYear()} TradingGoose. Algorithmic trade execution & research.</span>
        </div>
        <div className="flex items-center gap-4">
          <Link to="/terms-of-service" className="hover:text-foreground transition-colors">
            Terms
          </Link>
          <Link to="/privacy" className="hover:text-foreground transition-colors">
            Privacy
          </Link>
          <Link to="/faq" className="hover:text-foreground transition-colors">
            FAQ
          </Link>
        </div>
      </div>
    </footer>
  );
}
