import React from 'react';
import { TabsContent } from '@/components/ui/tabs';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';

interface ScheduleTabProps {
  loading: boolean;
  config: any;
  setConfig: (config: any) => void;
}

export function ScheduleTab({ loading, config, setConfig }: ScheduleTabProps) {
  return (
    <TabsContent value="schedule" className="space-y-4 px-6 py-4">
      <div className="space-y-2">
        <Label>Execution Frequency</Label>
        <select
          value={config?.frequency || 'weekly'}
          onChange={(e) => setConfig({ ...config, frequency: e.target.value })}
          className="w-full h-9 rounded-md border border-input bg-background px-3 text-sm"
        >
          <option value="daily">Daily (Market Close)</option>
          <option value="weekly">Weekly (Monday Open)</option>
          <option value="monthly">Monthly (1st Trading Day)</option>
        </select>
      </div>
      <div className="space-y-2">
        <Label>Time of Day</Label>
        <Input
          type="time"
          value={config?.time || '09:30'}
          onChange={(e) => setConfig({ ...config, time: e.target.value })}
        />
      </div>
    </TabsContent>
  );
}
