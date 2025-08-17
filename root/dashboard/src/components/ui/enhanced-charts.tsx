'use client';

import React from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
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
  FunnelChart,
  Funnel,
  LabelList
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

const CHART_COLORS = [COLORS.primary, COLORS.success, COLORS.warning, COLORS.danger, COLORS.info, COLORS.accent];

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
  description
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
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
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
          <div className="mt-3 h-8">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trend}>
                <Line 
                  type="monotone" 
                  dataKey="value" 
                  stroke={COLORS.primary} 
                  strokeWidth={1.5}
                  dot={false}
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
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Exception Trends (24h)
        </CardTitle>
        <CardDescription>
          Exception volume and resolution patterns
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Area 
                type="monotone" 
                dataKey="critical" 
                stackId="1" 
                stroke={COLORS.danger} 
                fill={COLORS.danger}
                fillOpacity={0.8}
              />
              <Area 
                type="monotone" 
                dataKey="high" 
                stackId="1" 
                stroke={COLORS.warning} 
                fill={COLORS.warning}
                fillOpacity={0.8}
              />
              <Area 
                type="monotone" 
                dataKey="medium" 
                stackId="1" 
                stroke={COLORS.info} 
                fill={COLORS.info}
                fillOpacity={0.8}
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
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5" />
          Processing Funnel
        </CardTitle>
        <CardDescription>
          Order processing stages and drop-offs
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <FunnelChart>
              <Funnel
                dataKey="value"
                data={data}
                isAnimationActive
              >
                <LabelList position="center" fill="#fff" stroke="none" />
              </Funnel>
              <Tooltip />
            </FunnelChart>
          </ResponsiveContainer>
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
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Zap className="h-5 w-5" />
          AI Analysis Performance
        </CardTitle>
        <CardDescription>
          Confidence vs Accuracy by exception category
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart data={data}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis 
                type="number" 
                dataKey="confidence" 
                name="Confidence" 
                unit="%" 
                domain={[0, 100]}
              />
              <YAxis 
                type="number" 
                dataKey="accuracy" 
                name="Accuracy" 
                unit="%" 
                domain={[0, 100]}
              />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} />
              <Scatter 
                name="AI Performance" 
                dataKey="volume" 
                fill={COLORS.primary}
              />
            </ScatterChart>
          </ResponsiveContainer>
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
              className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer hover:bg-gray-50 transition-colors ${
                onItemClick ? 'hover:shadow-sm' : ''
              }`}
              onClick={() => onItemClick?.(activity)}
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
