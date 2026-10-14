import React from 'react';
import { TabsContent } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

export function SettingsTab({ rebalanceConfig, setRebalanceConfig }: any) {
  return (
    <TabsContent value="settings" className="space-y-4 px-6 py-4">
      <div className="flex items-center justify-between">
        <div>
          <Label>Auto-Execute Approved Rebalances</Label>
          <p className="text-xs text-muted-foreground">Automatically route rebalancing orders through Alpaca</p>
        </div>
        <Switch
          checked={rebalanceConfig?.autoExecute || false}
          onCheckedChange={(checked) =>
            setRebalanceConfig({ ...rebalanceConfig, autoExecute: checked })
          }
        />
      </div>
    </TabsContent>
  );
}
