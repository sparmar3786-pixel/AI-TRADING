import React, { useState } from 'react';
import { format, subDays, startOfMonth, startOfYear, isSameDay } from 'date-fns';
import { Calendar as CalendarIcon, Check, ChevronDown, RotateCcw, X } from 'lucide-react';
import { DateRange } from 'react-day-picker';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';

export interface DateRangePickerProps {
  dateRange: DateRange | undefined;
  onDateRangeChange: (range: DateRange | undefined) => void;
  className?: string;
  align?: 'start' | 'center' | 'end';
}

interface PresetOption {
  label: string;
  getValue: () => DateRange;
}

export default function DateRangePicker({
  dateRange,
  onDateRangeChange,
  className,
  align = 'end',
}: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  const [selectedRange, setSelectedRange] = useState<DateRange | undefined>(dateRange);

  // Sync internal state when external prop changes
  React.useEffect(() => {
    setSelectedRange(dateRange);
  }, [dateRange]);

  const today = new Date();

  const presets: PresetOption[] = [
    {
      label: 'Today',
      getValue: () => ({ from: today, to: today }),
    },
    {
      label: 'Yesterday',
      getValue: () => {
        const yest = subDays(today, 1);
        return { from: yest, to: yest };
      },
    },
    {
      label: 'Last 7 Days',
      getValue: () => ({ from: subDays(today, 6), to: today }),
    },
    {
      label: 'Last 30 Days',
      getValue: () => ({ from: subDays(today, 29), to: today }),
    },
    {
      label: 'This Month',
      getValue: () => ({ from: startOfMonth(today), to: today }),
    },
    {
      label: 'Last 90 Days',
      getValue: () => ({ from: subDays(today, 89), to: today }),
    },
    {
      label: 'Year to Date',
      getValue: () => ({ from: startOfYear(today), to: today }),
    },
    {
      label: 'All Time',
      getValue: () => ({ from: subDays(today, 365), to: today }),
    },
  ];

  const handleApply = () => {
    onDateRangeChange(selectedRange);
    setOpen(false);
  };

  const handleReset = () => {
    const defaultRange: DateRange = { from: subDays(today, 29), to: today };
    setSelectedRange(defaultRange);
    onDateRangeChange(defaultRange);
    setOpen(false);
  };

  const handlePresetSelect = (preset: PresetOption) => {
    const range = preset.getValue();
    setSelectedRange(range);
    onDateRangeChange(range);
    setOpen(false);
  };

  // Determine active preset label if any matches
  const activePreset = presets.find((p) => {
    if (!selectedRange?.from || !selectedRange?.to) return false;
    const val = p.getValue();
    return (
      val.from &&
      val.to &&
      isSameDay(selectedRange.from, val.from) &&
      isSameDay(selectedRange.to, val.to)
    );
  });

  const getDisplayText = () => {
    if (!selectedRange?.from) {
      return <span>Select time interval</span>;
    }
    if (selectedRange.to) {
      if (isSameDay(selectedRange.from, selectedRange.to)) {
        return (
          <span>
            {format(selectedRange.from, 'LLL dd, y')} (Single Day)
          </span>
        );
      }
      return (
        <span>
          {format(selectedRange.from, 'LLL dd, y')} &ndash; {format(selectedRange.to, 'LLL dd, y')}
        </span>
      );
    }
    return <span>From {format(selectedRange.from, 'LLL dd, y')}</span>;
  };

  return (
    <div className={cn('grid gap-2', className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            id="date"
            variant="outline"
            size="sm"
            className={cn(
              'h-9 justify-start text-left font-normal border-border/60 hover:border-primary/50 bg-background/80 px-3',
              !selectedRange && 'text-muted-foreground'
            )}
          >
            <CalendarIcon className="mr-2 h-4 w-4 text-[#fc0]" />
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-foreground">{getDisplayText()}</span>
              {activePreset && (
                <Badge
                  variant="secondary"
                  className="text-[10px] py-0 px-1.5 h-4 bg-primary/10 text-primary border-primary/20 font-semibold"
                >
                  {activePreset.label}
                </Badge>
              )}
            </div>
            <ChevronDown className="ml-2 h-3.5 w-3.5 opacity-50" />
          </Button>
        </PopoverTrigger>

        <PopoverContent
          className="w-auto p-0 border-border/80 bg-popover shadow-2xl rounded-xl overflow-hidden"
          align={align}
        >
          <div className="flex flex-col sm:flex-row">
            {/* Quick Preset Interval Sidebar */}
            <div className="border-b sm:border-b-0 sm:border-r border-border/40 p-3 sm:w-44 bg-muted/20 flex flex-col gap-1">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase px-2 mb-1 tracking-wider">
                Interval Presets
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-1 gap-1">
                {presets.map((preset) => {
                  const isActive = activePreset?.label === preset.label;
                  return (
                    <button
                      key={preset.label}
                      onClick={() => handlePresetSelect(preset)}
                      className={cn(
                        'flex items-center justify-between px-2.5 py-1.5 text-xs rounded-md text-left transition-all',
                        isActive
                          ? 'bg-primary text-primary-foreground font-semibold shadow-sm'
                          : 'text-foreground/80 hover:bg-muted hover:text-foreground'
                      )}
                    >
                      <span>{preset.label}</span>
                      {isActive && <Check className="h-3 w-3 ml-1" />}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Calendar View */}
            <div className="p-3">
              <div className="px-2 pb-2 text-xs text-muted-foreground flex items-center justify-between border-b border-border/30 mb-2">
                <span>Select range on calendar</span>
                <span className="text-[11px] text-foreground font-mono">
                  {selectedRange?.from ? format(selectedRange.from, 'yyyy-MM-dd') : 'Start'} &rarr;{' '}
                  {selectedRange?.to ? format(selectedRange.to, 'yyyy-MM-dd') : 'End'}
                </span>
              </div>
              <Calendar
                initialFocus
                mode="range"
                defaultMonth={selectedRange?.from || today}
                selected={selectedRange}
                onSelect={setSelectedRange}
                numberOfMonths={1}
                disabled={(date) => {
                  const maxDate = new Date();
                  maxDate.setHours(23, 59, 59, 999);
                  return date > maxDate;
                }}
              />

              {/* Action buttons footer */}
              <div className="flex items-center justify-between pt-3 border-t border-border/40 mt-2 px-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleReset}
                  className="h-8 text-xs text-muted-foreground hover:text-foreground gap-1"
                >
                  <RotateCcw className="h-3 w-3" />
                  Reset (30D)
                </Button>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setOpen(false)}
                    className="h-8 text-xs"
                  >
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleApply}
                    disabled={!selectedRange?.from}
                    className="h-8 text-xs bg-[#fc0] text-black hover:bg-[#fc0]/90 font-semibold"
                  >
                    Apply Range
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
