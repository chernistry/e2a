'use client';

import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { 
  BarChart, Bar, XAxis, YAxis, CartesianGrid, ResponsiveContainer, 
  ScatterChart, Scatter, Cell, FunnelChart, Funnel, LabelList,
  LineChart, Line, ComposedChart, Area, ReferenceLine
} from 'recharts';
import { 
  TrendingUp, TrendingDown, Minus, AlertTriangle, 
  DollarSign, Brain, Clock, Target, Info
} from 'lucide-react';

// Color-blind safe palette
const COLORS = {
  primary: '#2563eb',
  secondary: '#06b6d4', 
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  neutral: '#6b7280',
  // Categorical colors (color-blind safe)
  categorical: ['#2563eb', '#dc2626', '#059669', '#d97706', '#7c3aed', '#db2777']
};

interface KPICardProps {
  title: string;
  value: number | string;
  unit?: string;
  target?: number;
  status: 'good' | 'warning' | 'critical';
  trend?: Array<{time: string, value: number}>;
  description?: string;
  tooltip?: string;
  metadata?: Record<string, any>;
}

export function BIKPICard({ 
  title, 
  value, 
  unit = '', 
  target, 
  status, 
  trend = [], 
  description,
  tooltip,
  metadata 
}: KPICardProps) {
  const statusColors = {
    good: 'text-green-600 bg-green-50 border-green-200',
    warning: 'text-yellow-600 bg-yellow-50 border-yellow-200',
    critical: 'text-red-600 bg-red-50 border-red-200'
  };

  const statusIcons = {
    good: <TrendingUp className="h-4 w-4" />,
    warning: <Minus className="h-4 w-4" />,
    critical: <TrendingDown className="h-4 w-4" />
  };

  // Calculate trend direction
  const trendDirection = trend.length > 1 ? 
    (trend[trend.length - 1].value > trend[0].value ? 'up' : 
     trend[trend.length - 1].value < trend[0].value ? 'down' : 'flat') : 'flat';

  return (
    <Card className={`${statusColors[status]} border-2`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            {title}
            {tooltip && (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-3 w-3 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent>
                    <p className="max-w-xs text-xs">{tooltip}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            )}
          </CardTitle>
          {statusIcons[status]}
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline justify-between">
          <div>
            <div className="text-2xl font-bold">
              {typeof value === 'number' ? value.toLocaleString() : value}
              <span className="text-sm font-normal ml-1">{unit}</span>
            </div>
            {target && (
              <div className="text-xs text-muted-foreground mt-1">
                Target: {target.toLocaleString()}{unit}
              </div>
            )}
          </div>
          
          {trend.length > 0 && (
            <div className="w-20 h-12">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend}>
                  <Line 
                    type="monotone" 
                    dataKey="value" 
                    stroke={COLORS[status === 'good' ? 'success' : status === 'warning' ? 'warning' : 'danger']}
                    strokeWidth={2}
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        
        {description && (
          <p className="text-xs text-muted-foreground mt-2">{description}</p>
        )}
        
        {metadata && Object.keys(metadata).length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-200">
            <div className="flex flex-wrap gap-2">
              {Object.entries(metadata).slice(0, 2).map(([key, val]) => (
                <Badge key={key} variant="outline" className="text-xs">
                  {key}: {typeof val === 'number' ? val.toLocaleString() : String(val)}
                </Badge>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface SLARiskHeatmapProps {
  data: Array<{
    hour: number;
    reason_code: string;
    breach_count: number;
    revenue_risk: number;
  }>;
  title?: string;
}

export function SLARiskHeatmap({ data, title = "SLA Risk Heatmap" }: SLARiskHeatmapProps) {
  // Transform data for heatmap visualization
  const hours = Array.from(new Set(data.map(d => d.hour))).sort((a, b) => a - b);
  const reasons = Array.from(new Set(data.map(d => d.reason_code)));
  
  const maxRisk = Math.max(...data.map(d => d.revenue_risk));
  
  const getIntensity = (risk: number) => {
    const intensity = risk / maxRisk;
    return `rgba(239, 68, 68, ${intensity})`; // Red with variable opacity
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5" />
          {title}
        </CardTitle>
        <CardDescription>
          Revenue risk by hour and reason code - darker = higher risk
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {/* Hour labels */}
          <div className="flex">
            <div className="w-24"></div>
            {hours.map(hour => (
              <div key={hour} className="w-8 text-xs text-center">
                {hour}h
              </div>
            ))}
          </div>
          
          {/* Heatmap grid */}
          {reasons.map(reason => (
            <div key={reason} className="flex items-center">
              <div className="w-24 text-xs truncate pr-2" title={reason}>
                {reason}
              </div>
              {hours.map(hour => {
                const cell = data.find(d => d.hour === hour && d.reason_code === reason);
                const risk = cell?.revenue_risk || 0;
                const count = cell?.breach_count || 0;
                
                return (
                  <TooltipProvider key={`${hour}-${reason}`}>
                    <Tooltip>
                      <TooltipTrigger>
                        <div 
                          className="w-8 h-6 border border-gray-200 cursor-pointer"
                          style={{ backgroundColor: risk > 0 ? getIntensity(risk) : '#f9fafb' }}
                        />
                      </TooltipTrigger>
                      <TooltipContent>
                        <div className="text-xs">
                          <div>{reason} @ {hour}:00</div>
                          <div>Breaches: {count}</div>
                          <div>Risk: ${risk.toLocaleString()}</div>
                        </div>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                );
              })}
            </div>
          ))}
          
          {/* Legend */}
          <div className="flex items-center justify-center gap-4 mt-4 pt-4 border-t">
            <span className="text-xs text-muted-foreground">Low Risk</span>
            <div className="flex">
              {[0.2, 0.4, 0.6, 0.8, 1.0].map(intensity => (
                <div 
                  key={intensity}
                  className="w-4 h-4 border border-gray-200"
                  style={{ backgroundColor: `rgba(239, 68, 68, ${intensity})` }}
                />
              ))}
            </div>
            <span className="text-xs text-muted-foreground">High Risk</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface RevenueRiskParetoProps {
  data: Array<{
    reason_code: string;
    total_risk: number;
    exception_count: number;
    cumulative_percent: number;
  }>;
  insights?: {
    total_risk: number;
    pareto_80_reasons: string[];
    focus_message: string;
  };
}

export function RevenueRiskPareto({ data, insights }: RevenueRiskParetoProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <DollarSign className="h-5 w-5" />
          Revenue Risk Pareto Analysis
        </CardTitle>
        <CardDescription>
          80/20 analysis - focus on top reasons driving financial risk
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={data} margin={{ top: 20, right: 30, left: 20, bottom: 60 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="reason_code" 
                angle={-45}
                textAnchor="end"
                height={80}
                fontSize={10}
              />
              <YAxis yAxisId="left" />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} />
              
              <Bar 
                yAxisId="left"
                dataKey="total_risk" 
                fill={COLORS.primary}
                name="Revenue Risk ($)"
              />
              
              <Line 
                yAxisId="right"
                type="monotone" 
                dataKey="cumulative_percent" 
                stroke={COLORS.danger}
                strokeWidth={3}
                name="Cumulative %"
              />
              
              <ReferenceLine yAxisId="right" y={80} stroke={COLORS.warning} strokeDasharray="5 5" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        
        {insights && (
          <div className="mt-4 p-3 bg-blue-50 rounded-lg">
            <div className="text-sm font-medium text-blue-900 mb-2">
              Key Insight
            </div>
            <div className="text-sm text-blue-800">
              {insights.focus_message}
            </div>
            <div className="mt-2 flex flex-wrap gap-1">
              {insights.pareto_80_reasons.slice(0, 5).map(reason => (
                <Badge key={reason} variant="secondary" className="text-xs">
                  {reason}
                </Badge>
              ))}
              {insights.pareto_80_reasons.length > 5 && (
                <Badge variant="outline" className="text-xs">
                  +{insights.pareto_80_reasons.length - 5} more
                </Badge>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface AIConfidenceScatterProps {
  data: Array<{
    confidence_percent: number;
    resolution_hours: number;
    reason_code: string;
    severity: string;
    bubble_size: number;
  }>;
  insights?: {
    correlation_coefficient: number;
    correlation_strength: string;
    interpretation: string;
  };
}

export function AIConfidenceScatter({ data, insights }: AIConfidenceScatterProps) {
  const severityColors = {
    'CRITICAL': COLORS.danger,
    'HIGH': COLORS.warning,
    'MEDIUM': COLORS.primary,
    'LOW': COLORS.success
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Brain className="h-5 w-5" />
          AI Confidence vs Resolution Time
        </CardTitle>
        <CardDescription>
          Correlation analysis - validates AI effectiveness
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-80">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart data={data} margin={{ top: 20, right: 20, bottom: 20, left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                type="number" 
                dataKey="confidence_percent" 
                name="AI Confidence %" 
                domain={[0, 100]}
              />
              <YAxis 
                type="number" 
                dataKey="resolution_hours" 
                name="Resolution Time (hours)"
              />
              <Scatter name="Exceptions" dataKey="resolution_hours">
                {data.map((entry, index) => (
                  <Cell 
                    key={`cell-${index}`} 
                    fill={severityColors[entry.severity as keyof typeof severityColors] || COLORS.neutral}
                  />
                ))}
              </Scatter>
              
              {/* Quadrant lines */}
              <ReferenceLine x={80} stroke={COLORS.neutral} strokeDasharray="2 2" />
              <ReferenceLine y={24} stroke={COLORS.neutral} strokeDasharray="2 2" />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        
        {/* Quadrant labels */}
        <div className="grid grid-cols-2 gap-2 mt-4 text-xs">
          <div className="text-center p-2 bg-green-50 rounded">
            <div className="font-medium text-green-800">High Conf / Fast</div>
            <div className="text-green-600">Optimal AI Performance</div>
          </div>
          <div className="text-center p-2 bg-yellow-50 rounded">
            <div className="font-medium text-yellow-800">High Conf / Slow</div>
            <div className="text-yellow-600">Process Bottleneck</div>
          </div>
          <div className="text-center p-2 bg-blue-50 rounded">
            <div className="font-medium text-blue-800">Low Conf / Fast</div>
            <div className="text-blue-600">Manual Efficiency</div>
          </div>
          <div className="text-center p-2 bg-red-50 rounded">
            <div className="font-medium text-red-800">Low Conf / Slow</div>
            <div className="text-red-600">Needs Attention</div>
          </div>
        </div>
        
        {insights && (
          <div className="mt-4 p-3 bg-gray-50 rounded-lg">
            <div className="text-sm font-medium mb-2">
              Correlation Analysis (R² = {insights.correlation_coefficient.toFixed(3)})
            </div>
            <div className="text-sm text-muted-foreground">
              {insights.interpretation}
            </div>
            <Badge 
              variant={insights.correlation_strength === 'strong' ? 'default' : 
                      insights.correlation_strength === 'moderate' ? 'secondary' : 'outline'}
              className="mt-2"
            >
              {insights.correlation_strength} correlation
            </Badge>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface ProcessingFunnelProps {
  data: Array<{
    stage: string;
    count: number;
    color: string;
    conversion_rate?: number;
    drop_off?: number;
    drop_off_rate?: number;
  }>;
  insights?: {
    overall_conversion: number;
    biggest_drop_off: string;
    total_orders: number;
    completed_orders: number;
  };
}

export function ProcessingFunnel({ data, insights }: ProcessingFunnelProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5" />
          Order Processing Funnel
        </CardTitle>
        <CardDescription>
          Order fulfillment conversion rates and drop-off analysis
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {data.map((stage, index) => {
            const width = data[0].count > 0 ? (stage.count / data[0].count) * 100 : 0;
            
            return (
              <div key={stage.stage} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div 
                      className="w-3 h-3 rounded"
                      style={{ backgroundColor: stage.color }}
                    />
                    <span className="font-medium">{stage.stage}</span>
                  </div>
                  <div className="text-right">
                    <div className="font-bold">{stage.count.toLocaleString()}</div>
                    {stage.conversion_rate !== undefined && (
                      <div className="text-xs text-muted-foreground">
                        {stage.conversion_rate.toFixed(1)}% conversion
                      </div>
                    )}
                  </div>
                </div>
                
                <div className="relative">
                  <div className="w-full bg-gray-200 rounded-full h-6">
                    <div 
                      className="h-6 rounded-full flex items-center justify-center text-white text-xs font-medium"
                      style={{ 
                        width: `${width}%`,
                        backgroundColor: stage.color,
                        minWidth: width > 0 ? '60px' : '0px'
                      }}
                    >
                      {width > 15 && `${width.toFixed(0)}%`}
                    </div>
                  </div>
                  
                  {stage.drop_off && stage.drop_off > 0 && (
                    <div className="absolute right-0 top-7 text-xs text-red-600">
                      -{stage.drop_off.toLocaleString()} ({stage.drop_off_rate?.toFixed(1)}%)
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
        
        {insights && (
          <div className="mt-6 p-4 bg-blue-50 rounded-lg">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="font-medium text-blue-900">Overall Conversion</div>
                <div className="text-2xl font-bold text-blue-800">
                  {insights.overall_conversion.toFixed(1)}%
                </div>
              </div>
              <div>
                <div className="font-medium text-blue-900">Biggest Drop-off</div>
                <div className="text-lg font-bold text-blue-800">
                  {insights.biggest_drop_off}
                </div>
              </div>
            </div>
            <div className="mt-2 text-xs text-blue-700">
              {insights.completed_orders.toLocaleString()} of {insights.total_orders.toLocaleString()} orders completed
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

interface ExceptionAgingCohortsProps {
  data: Array<{
    cohort_date: string;
    age_bucket: string;
    exception_count: number;
    resolved_count: number;
    resolution_rate: number;
  }>;
  insights?: {
    current_open: number;
    total_exceptions: number;
    overall_resolution_rate: number;
    aging_trend: string;
  };
}

export function ExceptionAgingCohorts({ data, insights }: ExceptionAgingCohortsProps) {
  // Group data by cohort date
  const cohortDates = Array.from(new Set(data.map(d => d.cohort_date))).sort();
  const ageBuckets = ['0-4h', '4-24h', '1-3d', '3d+'];
  
  const bucketColors = {
    '0-4h': COLORS.success,
    '4-24h': COLORS.primary,
    '1-3d': COLORS.warning,
    '3d+': COLORS.danger
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5" />
          Exception Aging Cohorts
        </CardTitle>
        <CardDescription>
          Resolution patterns by creation date - track aging trends
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {/* Age bucket legend */}
          <div className="flex justify-center gap-4 mb-4">
            {ageBuckets.map(bucket => (
              <div key={bucket} className="flex items-center gap-1">
                <div 
                  className="w-3 h-3 rounded"
                  style={{ backgroundColor: bucketColors[bucket as keyof typeof bucketColors] }}
                />
                <span className="text-xs">{bucket}</span>
              </div>
            ))}
          </div>
          
          {/* Cohort grid */}
          <div className="space-y-1">
            {cohortDates.map(date => {
              const cohortData = data.filter(d => d.cohort_date === date);
              const totalForDate = cohortData.reduce((sum, d) => sum + d.exception_count, 0);
              
              return (
                <div key={date} className="flex items-center gap-2">
                  <div className="w-20 text-xs">
                    {new Date(date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                  </div>
                  
                  <div className="flex-1 flex">
                    {ageBuckets.map(bucket => {
                      const bucketData = cohortData.find(d => d.age_bucket === bucket);
                      const count = bucketData?.exception_count || 0;
                      const width = totalForDate > 0 ? (count / totalForDate) * 100 : 0;
                      
                      return (
                        <TooltipProvider key={bucket}>
                          <Tooltip>
                            <TooltipTrigger>
                              <div 
                                className="h-6 border-r border-white"
                                style={{ 
                                  width: `${width}%`,
                                  backgroundColor: bucketColors[bucket as keyof typeof bucketColors],
                                  minWidth: width > 0 ? '2px' : '0px'
                                }}
                              />
                            </TooltipTrigger>
                            <TooltipContent>
                              <div className="text-xs">
                                <div>{date} - {bucket}</div>
                                <div>Count: {count}</div>
                                <div>Resolved: {bucketData?.resolved_count || 0}</div>
                                <div>Rate: {bucketData?.resolution_rate.toFixed(1) || 0}%</div>
                              </div>
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      );
                    })}
                  </div>
                  
                  <div className="w-12 text-xs text-right">
                    {totalForDate}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        
        {insights && (
          <div className="mt-4 p-3 bg-gray-50 rounded-lg">
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <div className="font-medium">Currently Open</div>
                <div className="text-lg font-bold">{insights.current_open}</div>
              </div>
              <div>
                <div className="font-medium">Resolution Rate</div>
                <div className="text-lg font-bold">{insights.overall_resolution_rate.toFixed(1)}%</div>
              </div>
              <div>
                <div className="font-medium">Trend</div>
                <Badge 
                  variant={insights.aging_trend === 'improving' ? 'default' : 'destructive'}
                  className="text-xs"
                >
                  {insights.aging_trend}
                </Badge>
              </div>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
