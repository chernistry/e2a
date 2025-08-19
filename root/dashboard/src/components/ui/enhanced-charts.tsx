'use client';

import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { 
  Tooltip as UITooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { 
  LineChart, 
  Line, 
  AreaChart, 
  Area, 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  Legend
} from 'recharts';
import { 
  TrendingUp, 
  TrendingDown, 
  AlertTriangle, 
  Clock, 
  Target,
  Zap,
  Activity,
  Eye,
  BarChart3,
  PieChart as PieChartIcon
} from 'lucide-react';

// Color palette for consistent theming
const COLORS = {
  primary: '#3b82f6',
  success: '#10b981',
  warning: '#f59e0b',
  danger: '#ef4444',
  info: '#06b6d4',
  muted: '#6b7280',
  accent: '#8b5cf6'
};

// Enhanced KPI Card with trend and sparkline
interface KPICardProps {
  title: string;
  value: string | number;
  change?: number;
  target?: number;
  unit?: string;
  icon?: React.ReactNode;
  trend?: Array<{ time: string; value: number }>;
  status?: 'good' | 'warning' | 'critical';
  description?: string;
  tooltip?: string;
}

export const KPICard: React.FC<KPICardProps> = ({
  title,
  value,
  change,
  target,
  unit = '',
  icon,
  trend,
  status = 'good',
  description,
  tooltip
}) => {
  const statusColors = {
    good: 'text-green-600',
    warning: 'text-yellow-600',
    critical: 'text-red-600'
  };

  const formatValue = (val: string | number) => {
    if (typeof val === 'number') {
      return val.toLocaleString();
    }
    return val;
  };

  return (
    <Card className="relative overflow-hidden">
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        {tooltip ? (
          <TooltipProvider>
            <UITooltip>
              <TooltipTrigger asChild>
                <CardTitle className="text-sm font-medium cursor-help">{title}</CardTitle>
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                <p className="text-sm">{tooltip}</p>
              </TooltipContent>
            </UITooltip>
          </TooltipProvider>
        ) : (
          <CardTitle className="text-sm font-medium">{title}</CardTitle>
        )}
        {icon && <div className="h-4 w-4 text-muted-foreground">{icon}</div>}
      </CardHeader>
      <CardContent>
        <div className="flex items-baseline space-x-2">
          <div className={`text-2xl font-bold ${statusColors[status]}`}>
            {formatValue(value)}{unit}
          </div>
          {change !== undefined && (
            <div className={`flex items-center text-xs ${change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
              {change >= 0 ? <TrendingUp className="h-3 w-3" /> : <TrendingDown className="h-3 w-3" />}
              {Math.abs(change).toFixed(1)}%
            </div>
          )}
        </div>
        
        {target && (
          <div className="mt-2">
            <div className="flex justify-between text-xs text-muted-foreground mb-1">
              <span>Target: {target}{unit}</span>
              <span>{((Number(value) / target) * 100).toFixed(0)}%</span>
            </div>
            <Progress value={(Number(value) / target) * 100} className="h-1" />
          </div>
        )}

        {trend && trend.length > 0 && (
          <div className='mt-3 h-8'>
            <ResponsiveContainer width='100%' height='100%'>
              <LineChart data={trend}>
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      return (
                        <div className='rounded-lg border bg-background p-2 shadow-sm'>
                          <div className='grid grid-cols-1 gap-1.5'>
                            <span className='text-muted-foreground'>
                              {payload[0].payload.time}
                            </span>
                            <span className='font-bold'>
                              {payload[0].value}
                              {unit}
                            </span>
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Line
                  type='monotone'
                  dataKey='value'
                  stroke={COLORS.primary}
                  strokeWidth={1.5}
                  dot={false}
                  activeDot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {description && (
          <p className="text-xs text-muted-foreground mt-2">{description}</p>
        )}
      </CardContent>
    </Card>
  );
};

// SLA Compliance Gauge
interface SLAGaugeProps {
  value: number;
  target: number;
  title: string;
}

export const SLAGauge: React.FC<SLAGaugeProps> = ({ value, target, title }) => {
  const percentage = (value / target) * 100;
  const isHealthy = percentage >= 95;
  
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Target className="h-5 w-5" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex items-center justify-center">
        <div className="relative w-32 h-32">
          <svg className="w-32 h-32 transform -rotate-90" viewBox="0 0 36 36">
            <path
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none"
              stroke="#e5e7eb"
              strokeWidth="2"
            />
            <path
              d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
              fill="none"
              stroke={isHealthy ? COLORS.success : percentage > 90 ? COLORS.warning : COLORS.danger}
              strokeWidth="2"
              strokeDasharray={`${percentage}, 100`}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center">
              <div className={`text-2xl font-bold ${isHealthy ? 'text-green-600' : percentage > 90 ? 'text-yellow-600' : 'text-red-600'}`}>
                {percentage.toFixed(1)}%
              </div>
              <div className="text-xs text-muted-foreground">Target: {target}%</div>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// Exception Trend Chart
interface ExceptionTrendProps {
  data: Array<{
    time: string;
    total: number;
    resolved: number;
    critical: number;
    high: number;
    medium: number;
  }>;
}

export const ExceptionTrendChart: React.FC<ExceptionTrendProps> = ({ data }) => {
  // Format time for better display
  const formatTime = (timeStr: string) => {
    try {
      const date = new Date(timeStr);
      return date.toLocaleTimeString('en-US', { 
        hour: '2-digit', 
        minute: '2-digit',
        hour12: false 
      });
    } catch {
      return timeStr;
    }
  };

  // Generate sample data if no data provided or normalize existing data
  const chartData = data && data.length > 0 ? data : [
    { time: '00:00', total: 5, resolved: 3, critical: 1, high: 2, medium: 2 },
    { time: '04:00', total: 3, resolved: 2, critical: 0, high: 1, medium: 2 },
    { time: '08:00', total: 12, resolved: 8, critical: 2, high: 4, medium: 6 },
    { time: '12:00', total: 18, resolved: 12, critical: 3, high: 6, medium: 9 },
    { time: '16:00', total: 25, resolved: 15, critical: 5, high: 8, medium: 12 },
    { time: '20:00', total: 8, resolved: 6, critical: 1, high: 3, medium: 4 }
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Exception Trends (24h)
        </CardTitle>
        <CardDescription>
          Exception volume by severity over time
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                dataKey="time" 
                tick={{ fontSize: 12 }}
                tickFormatter={formatTime}
                axisLine={true}
                tickLine={true}
                label={{
                  value: 'Time',
                  position: 'insideBottom',
                  offset: -10
                }}
              />
              <YAxis 
                tick={{ fontSize: 12 }}
                axisLine={true}
                tickLine={true}
                label={{
                  value: 'Exceptions',
                  angle: -90,
                  position: 'insideLeft'
                }}
              />
              <Tooltip 
                labelFormatter={(value) => `Time: ${formatTime(value as string)}`}
                formatter={(value: any, name: string) => {
                  const nameMap: Record<string, string> = {
                    critical: 'Critical',
                    high: 'High', 
                    medium: 'Medium',
                    total: 'Total',
                    resolved: 'Resolved'
                  };
                  return [value, nameMap[name] || name];
                }}
                contentStyle={{
                  backgroundColor: 'white',
                  border: '1px solid #ccc',
                  borderRadius: '4px'
                }}
              />
              <Legend 
                wrapperStyle={{ paddingTop: '20px' }}
                iconType="rect"
                verticalAlign='top'
                align='right'
              />
              <Area 
                type="monotone" 
                dataKey="critical" 
                stackId="1" 
                stroke={COLORS.danger} 
                fill={COLORS.danger}
                fillOpacity={0.8}
                name="Critical"
              />
              <Area 
                type="monotone" 
                dataKey="high" 
                stackId="1" 
                stroke={COLORS.warning} 
                fill={COLORS.warning}
                fillOpacity={0.8}
                name="High"
              />
              <Area 
                type="monotone" 
                dataKey="medium" 
                stackId="1" 
                stroke={COLORS.info} 
                fill={COLORS.info}
                fillOpacity={0.8}
                name="Medium"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
};

// Exception Distribution Pie Chart
interface ExceptionDistributionProps {
  data: Array<{
    name: string;
    value: number;
    color: string;
  }>;
}

export const ExceptionDistribution: React.FC<ExceptionDistributionProps> = ({ data }) => {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PieChartIcon className="h-5 w-5" />
          Exception Types
        </CardTitle>
        <CardDescription>
          Distribution by reason code
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={80}
                paddingAngle={5}
                dataKey="value"
              >
                {data.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          {data.map((item, index) => (
            <div key={index} className="flex items-center gap-2">
              <div 
                className="w-3 h-3 rounded-full" 
                style={{ backgroundColor: item.color }}
              />
              <span className="text-sm">{item.name}</span>
              <span className="text-sm font-medium ml-auto">{item.value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

// Processing Funnel
interface ProcessingFunnelProps {
  data: Array<{
    name: string;
    value: number;
    fill: string;
  }>;
}

export const ProcessingFunnel: React.FC<ProcessingFunnelProps> = ({ data }) => {
  // Generate sample data if none provided
  const funnelData = data && data.length > 0 ? data : [
    { name: 'Orders Received', value: 1000, fill: COLORS.primary },
    { name: 'Validated', value: 950, fill: COLORS.success },
    { name: 'Processing', value: 900, fill: COLORS.info },
    { name: 'Shipped', value: 850, fill: COLORS.warning },
    { name: 'Delivered', value: 800, fill: COLORS.accent }
  ];

  const maxValue = Math.max(...funnelData.map(d => d.value));
  const funnelHeight = 240;
  const funnelWidth = 300;
  const stepHeight = funnelHeight / funnelData.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Processing Funnel
        </CardTitle>
        <CardDescription>
          Order processing stages with conversion rates
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-center">
          <svg width={funnelWidth + 100} height={funnelHeight + 40} className="overflow-visible">
            {funnelData.map((item, index) => {
              const widthRatio = item.value / maxValue;
              const width = funnelWidth * widthRatio;
              const x = (funnelWidth - width) / 2;
              const y = index * stepHeight + 10;
              const prevValue = index > 0 ? funnelData[index - 1].value : item.value;
              const conversionRate = index > 0 ? ((item.value / prevValue) * 100).toFixed(1) : '100.0';
              
              return (
                <g key={index}>
                  {/* Funnel segment */}
                  <rect
                    x={x}
                    y={y}
                    width={width}
                    height={stepHeight - 4}
                    fill={item.fill}
                    rx={4}
                    className="transition-all duration-300 hover:opacity-80"
                  />
                  
                  {/* Value text inside segment */}
                  <text
                    x={funnelWidth / 2}
                    y={y + stepHeight / 2}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="white"
                    fontSize="14"
                    fontWeight="600"
                  >
                    {item.value.toLocaleString()}
                  </text>
                  
                  {/* Stage name on the right */}
                  <text
                    x={funnelWidth + 20}
                    y={y + stepHeight / 2 - 8}
                    dominantBaseline="middle"
                    fontSize="12"
                    fontWeight="500"
                    fill="currentColor"
                  >
                    {item.name}
                  </text>
                  
                  {/* Conversion rate on the right */}
                  <text
                    x={funnelWidth + 20}
                    y={y + stepHeight / 2 + 8}
                    dominantBaseline="middle"
                    fontSize="11"
                    fill="#6b7280"
                  >
                    {conversionRate}% conversion
                  </text>
                  
                  {/* Connection line to next stage */}
                  {index < funnelData.length - 1 && (
                    <line
                      x1={x + width / 2}
                      y1={y + stepHeight - 4}
                      x2={(funnelWidth - (funnelWidth * (funnelData[index + 1].value / maxValue))) / 2 + (funnelWidth * (funnelData[index + 1].value / maxValue)) / 2}
                      y2={y + stepHeight + 6}
                      stroke="#e5e7eb"
                      strokeWidth="2"
                      strokeDasharray="4,4"
                    />
                  )}
                </g>
              );
            })}
          </svg>
        </div>
        
        {/* Summary stats */}
        <div className="mt-4 grid grid-cols-3 gap-4 text-center">
          <div className="p-2 bg-gray-50 rounded">
            <div className="text-lg font-semibold text-gray-900">
              {((funnelData[funnelData.length - 1].value / funnelData[0].value) * 100).toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600">Overall Conversion</div>
          </div>
          <div className="p-2 bg-gray-50 rounded">
            <div className="text-lg font-semibold text-gray-900">
              {(funnelData[0].value - funnelData[funnelData.length - 1].value).toLocaleString()}
            </div>
            <div className="text-xs text-gray-600">Total Drop-offs</div>
          </div>
          <div className="p-2 bg-gray-50 rounded">
            <div className="text-lg font-semibold text-gray-900">
              {funnelData.reduce((acc, curr, idx) => {
                if (idx === 0) return acc;
                const prev = funnelData[idx - 1];
                const dropRate = ((prev.value - curr.value) / prev.value) * 100;
                return Math.max(acc, dropRate);
              }, 0).toFixed(1)}%
            </div>
            <div className="text-xs text-gray-600">Biggest Drop</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// AI Performance Scatter
interface AIPerformanceProps {
  data: Array<{
    confidence: number;
    accuracy: number;
    volume: number;
    category: string;
  }>;
}

export const AIPerformanceScatter: React.FC<AIPerformanceProps> = ({ data }) => {
  // Generate sample data if none provided
  const scatterData = data && data.length > 0 ? data : [
    { confidence: 95, accuracy: 92, volume: 45, category: 'Payment Issues' },
    { confidence: 88, accuracy: 85, volume: 32, category: 'Shipping Delays' },
    { confidence: 92, accuracy: 89, volume: 28, category: 'Inventory Problems' },
    { confidence: 85, accuracy: 82, volume: 18, category: 'Address Validation' },
    { confidence: 78, accuracy: 75, volume: 12, category: 'Other' }
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5" />
          AI Analysis Performance
        </CardTitle>
        <CardDescription>
          AI confidence vs accuracy by exception category (bubble size = volume)
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart data={scatterData} margin={{ top: 20, right: 20, bottom: 40, left: 40 }}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                type="number" 
                dataKey="confidence" 
                name="Confidence" 
                unit="%" 
                domain={[70, 100]}
                tick={{ fontSize: 12 }}
                label={{ value: 'AI Confidence %', position: 'insideBottom', offset: -10 }}
              />
              <YAxis 
                type="number" 
                dataKey="accuracy" 
                name="Accuracy" 
                unit="%" 
                domain={[70, 100]}
                tick={{ fontSize: 12 }}
                label={{
                  value: 'Accuracy %',
                  angle: -90,
                  position: 'insideLeft'
                }}
              />
              <Tooltip
                cursor={{ strokeDasharray: '3 3' }}
                content={({ active, payload }) => {
                  if (active && payload && payload.length) {
                    const data = payload[0].payload;
                    return (
                      <div className='rounded-lg border bg-background p-2 shadow-sm'>
                        <div className='grid grid-cols-1 gap-1.5'>
                          <span className='font-bold'>{data.category}</span>
                          <span className='text-sm text-muted-foreground'>
                            Confidence: {data.confidence}%
                          </span>
                          <span className='text-sm text-muted-foreground'>
                            Accuracy: {data.accuracy}%
                          </span>
                          <span className='text-sm text-muted-foreground'>
                            Volume: {data.volume}
                          </span>
                        </div>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Legend />
              <Scatter 
                name="AI Performance" 
                dataKey="volume" 
                fill={COLORS.primary}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        {/* Legend showing categories */}
        <div className="mt-4">
          <div className="text-sm font-medium text-muted-foreground mb-2">Categories:</div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {scatterData.map((item, index) => (
              <div key={index} className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-blue-500" />
                <span>{item.category}</span>
                <span className="text-muted-foreground">({item.volume})</span>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
};

// Real-time Activity Feed
interface ActivityItem {
  id: string;
  type: 'exception' | 'resolution' | 'alert' | 'system';
  title: string;
  description: string;
  timestamp: string;
  severity?: 'low' | 'medium' | 'high' | 'critical';
  metadata?: Record<string, any>;
}

interface ActivityFeedProps {
  activities: ActivityItem[];
  onItemClick?: (item: ActivityItem) => void;
}

export const ActivityFeed: React.FC<ActivityFeedProps> = ({ activities, onItemClick }) => {
  const getIcon = (type: string) => {
    switch (type) {
      case 'exception': return <AlertTriangle className="h-4 w-4" />;
      case 'resolution': return <Target className="h-4 w-4" />;
      case 'alert': return <Zap className="h-4 w-4" />;
      case 'system': return <Activity className="h-4 w-4" />;
      default: return <Clock className="h-4 w-4" />;
    }
  };

  const getSeverityColor = (severity?: string) => {
    switch (severity) {
      case 'critical': return 'text-red-600 bg-red-50';
      case 'high': return 'text-orange-600 bg-orange-50';
      case 'medium': return 'text-yellow-600 bg-yellow-50';
      case 'low': return 'text-blue-600 bg-blue-50';
      default: return 'text-gray-600 bg-gray-50';
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Eye className="h-5 w-5" />
          Live Activity Feed
        </CardTitle>
        <CardDescription>
          Real-time system events and exceptions
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-3 max-h-96 overflow-y-auto">
          {activities.map((activity) => (
            <div 
              key={activity.id}
              className={`flex items-start gap-3 p-3 rounded-lg border transition-colors ${
                onItemClick ? 'cursor-pointer hover:bg-gray-50 hover:shadow-sm' : ''
              }`}
              onClick={() => onItemClick?.(activity)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  onItemClick?.(activity);
                }
              }}
              role={onItemClick ? 'button' : 'listitem'}
              tabIndex={onItemClick ? 0 : -1}
            >
              <div className={`p-2 rounded-full ${getSeverityColor(activity.severity)}`}>
                {getIcon(activity.type)}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-medium truncate">{activity.title}</p>
                  <span className="text-xs text-muted-foreground">
                    {new Date(activity.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">{activity.description}</p>
                {activity.severity && (
                  <Badge variant="outline" className="mt-2 text-xs">
                    {activity.severity.toUpperCase()}
                  </Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};
