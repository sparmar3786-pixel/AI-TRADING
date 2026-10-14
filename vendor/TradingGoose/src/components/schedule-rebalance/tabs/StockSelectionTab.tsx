import React from 'react';
import { TabsContent } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';

export function StockSelectionTab({
  loading,
  positions = [],
  selectedPositions,
  togglePosition,
}: any) {
  return (
    <TabsContent value="stocks" className="space-y-4 px-6 py-4 max-h-72 overflow-y-auto">
      <div className="space-y-2">
        <Label>Available Portfolio Positions</Label>
        {positions.length === 0 ? (
          <p className="text-xs text-muted-foreground">No current open positions found.</p>
        ) : (
          positions.map((p: any) => (
            <div key={p.symbol} className="flex items-center justify-between p-2 rounded border border-border/50">
              <div className="flex items-center gap-2">
                <Checkbox
                  checked={selectedPositions.has(p.symbol)}
                  onCheckedChange={() => togglePosition(p.symbol)}
                />
                <span className="font-semibold text-sm">{p.symbol}</span>
                <span className="text-xs text-muted-foreground">{p.qty} shares</span>
              </div>
              <Badge variant="outline">{p.current_price ? `$${p.current_price}` : '$0.00'}</Badge>
            </div>
          ))
        )}
      </div>
    </TabsContent>
  );
}
