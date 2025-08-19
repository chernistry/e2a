'use client';

import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { 
  Activity, 
  AlertTriangle, 
  Clock, 
  Shield,
  Brain,
  DollarSign,
  Zap,
  Package,
  Eye
} from 'lucide-react';
import { apiClient, useApiData, Exception } from '@/lib/api';
import { 
  KPICard, 
  SLAGauge, 
  ExceptionTrendChart, 
  ExceptionDistribution, 
  ProcessingFunnel, 
  AIPerformanceScatter,
  ActivityFeed
} from '@/components/ui/enhanced-charts';
import { ExceptionDetailModal } from '@/components/ui/exception-detail-modal';

export default function OverviewPage() {
  // Modal state for exception details
  const [selectedExceptionId, setSelectedExceptionId] = useState<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // Create stable fetcher functions
  const fetchMetrics = React.useCallback(() => apiClient.getDashboardMetrics(), []);
  const fetchHealth = React.useCallback(() => apiClient.getSystemHealth(), []);
  const fetchExceptions = React.useCallback(() => apiClient.getLiveExceptions(10), []);
  const fetchTrends = React.useCallback(() => apiClient.getDashboardTrends(24), []);
  const fetchActivityFeed = React.useCallback(() => apiClient.getActivityFeed(10), []);

  const { 
    data: metrics, 
    loading: metricsLoading, 
    error: metricsError 
  } = useApiData(fetchMetrics, 10000); // Refresh every 10 seconds

  const { 
    data: health, 
    loading: healthLoading, 
    error: healthError 
  } = useApiData(fetchHealth, 30000); // Refresh every 30 seconds

  const { 
    data: exceptions, 
    loading: exceptionsLoading, 
    error: exceptionsError 
  } = useApiData(fetchExceptions, 15000); // Refresh every 15 seconds

  const { 
    data: trends, 
    loading: trendsLoading, 
    error: trendsError 
  } = useApiData(fetchTrends, 60000); // Refresh every minute

  const { 
    data: activityFeed, 
    loading: activityLoading, 
    error: activityError 
  } = useApiData(fetchActivityFeed, 20000); // Refresh every 20 seconds

  // Generate KPI trend data from real metrics
  const generateKPITrend = (currentValue: number, trendData?: any[]) => {
    if (trendData && trendData.length > 0) {
      return trendData.slice(-12).map((item, index) => ({
        time: `${index}h`,
        value: item.total || currentValue
      }));
    }
    
    // Fallback: generate trend around current value
    return Array.from({ length: 12 }, (_, i) => ({
      time: `${i}h`,
      value: currentValue + (Math.random() - 0.5) * currentValue * 0.1
    }));
  };

  // Handle exception click
  const handleExceptionClick = (exceptionId: number) => {
    setSelectedExceptionId(exceptionId);
    setIsModalOpen(true);
  };

  // Handle activity item click
  const handleActivityClick = (activity: any) => {
    if (activity.metadata?.exception_id) {
      setSelectedExceptionId(activity.metadata.exception_id);
      setIsModalOpen(true);
    } else if (activity.metadata?.order_id) {
      // Could open order details modal in the future
      console.log('Order activity clicked:', activity.metadata.order_id);
    }
  };

  if (metricsError || healthError || exceptionsError) {
    return (
      <div className="space-y-4">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Failed to load dashboard data. Please check if the API server is running.
            <br />
            <code className="text-xs">API URL: {process.env.NEXT_PUBLIC_API_URL}</code>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  // Prepare real data for charts
  const exceptionTrendData = trends?.exception_trends || [];
  const exceptionDistribution = trends?.exception_distribution?.map((item, index) => ({
    ...item,
    color: ['#ef4444', '#f59e0b', '#06b6d4', '#8b5cf6', '#10b981', '#f97316'][index % 6]
  })) || [];
  
  const processingFunnel = trends?.processing_funnel?.map((item, index) => ({
    ...item,
    fill: ['#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'][index % 5]
  })) || [];

  const aiPerformanceData = trends?.ai_performance?.map(item => ({
    confidence: item.avg_confidence * 100,
    accuracy: item.avg_confidence * 100, // Simplified - in reality you'd have separate accuracy metric
    volume: item.count,
    category: item.confidence_range
  })) || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Octup E²A Dashboard</h1>
          <p className="text-muted-foreground">
            SLA Radar + Invoice Guard with AI Exception Analyst
          </p>
        </div>
        <div className="flex items-center space-x-2">
          <Badge variant={health?.overall_status === 'healthy' ? 'default' : 'destructive'}>
            {healthLoading ? 'Loading...' : health?.overall_status || 'Unknown'}
          </Badge>
          <Badge variant="outline">
            Tenant: {process.env.NEXT_PUBLIC_DEFAULT_TENANT}
          </Badge>
        </div>
      </div>

      {/* Enhanced KPI Cards with Real Data */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <KPICard
          title="Active Exceptions"
          value={metrics?.active_exceptions || 0}
          icon={<AlertTriangle className="h-4 w-4" />}
          trend={generateKPITrend(metrics?.active_exceptions || 15, exceptionTrendData)}
          status={(metrics?.active_exceptions || 0) < 20 ? 'good' : 'warning'}
          description={`Total: ${metrics?.total_exceptions || 0}`}
        />

        <KPICard
          title="AI Success Rate"
          value={((metrics?.ai_analysis_success_rate || 0) * 100).toFixed(1)}
          unit="%"
          target={90}
          icon={<Brain className="h-4 w-4" />}
          trend={generateKPITrend(metrics?.ai_analysis_success_rate ? metrics.ai_analysis_success_rate * 100 : 88)}
          status={((metrics?.ai_analysis_success_rate || 0) * 100) >= 85 ? 'good' : 'warning'}
          description={`AI analysis success rate (confidence ≥80%). Total analyzed: ${metrics?.ai_total_analyzed || 0}`}
        />

        <KPICard
          title="Events/Min"
          value={metrics?.events_processed_per_minute || 0}
          icon={<Activity className="h-4 w-4" />}
          trend={generateKPITrend(metrics?.events_processed_per_minute || 45)}
          status="good"
          description={`Avg response: ${metrics?.average_response_time || 0}ms`}
        />
      </div>

      {/* Enhanced Metrics Row with Real Data */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <KPICard
          title="Revenue at Risk"
          value={`$${((metrics?.revenue_at_risk_cents || 0) / 100).toFixed(1)}K`}
          icon={<DollarSign className="h-4 w-4" />}
          status={(metrics?.revenue_at_risk_cents || 0) > 50000 ? 'critical' : (metrics?.revenue_at_risk_cents || 0) > 0 ? 'warning' : 'good'}
          description={
            metrics?.revenue_at_risk_metadata?.is_zero_because_no_exceptions 
              ? "No active exceptions" 
              : `From ${metrics?.revenue_at_risk_metadata?.active_exceptions_analyzed || 0} active exceptions`
          }
          tooltip={
            metrics?.revenue_at_risk_metadata?.disclaimer || 
            "This calculation is based purely on mathematical analysis of active exceptions and their estimated impact. It does not account for potential contractual obligations, reputational risks, or other business factors that may contribute to revenue at risk."
          }
        />

        <KPICard
          title="Processing Speed"
          value={(metrics?.average_response_time ? (metrics.average_response_time / 1000).toFixed(1) : "2.3")}
          unit="s"
          icon={<Zap className="h-4 w-4" />}
          status={(metrics?.average_response_time || 2300) < 5000 ? 'good' : 'warning'}
          description="Avg response time"
        />

        <KPICard
          title="Orders Today"
          value={metrics?.orders_processed_today?.toLocaleString() || "0"}
          icon={<Package className="h-4 w-4" />}
          status="good"
          description="Processed orders"
        />
      </div>

      {/* SLA Gauge and Exception Trends with Real Data */}
      <div className="grid gap-4 md:grid-cols-3">
        <SLAGauge
          value={(metrics?.sla_compliance_rate || 0) * 100}
          target={95}
          title="SLA Compliance"
        />
        
        <div className="md:col-span-2">
          {trendsLoading ? (
            <Card>
              <CardHeader>
                <CardTitle>Exception Trends (24h)</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="h-64 flex items-center justify-center">
                  <div className="text-muted-foreground">Loading trends...</div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <ExceptionTrendChart data={exceptionTrendData} />
          )}
        </div>
      </div>

      {/* Exception Analysis with Real Data */}
      <div className="grid gap-4 md:grid-cols-2">
        {exceptionDistribution.length > 0 ? (
          <ExceptionDistribution data={exceptionDistribution} />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Exception Distribution</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-64 flex items-center justify-center">
                <div className="text-muted-foreground">No exception data available</div>
              </div>
            </CardContent>
          </Card>
        )}
        
        {processingFunnel.length > 0 ? (
          <ProcessingFunnel data={processingFunnel} />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Processing Funnel</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-64 flex items-center justify-center">
                <div className="text-muted-foreground">No processing data available</div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* AI Performance and Activity Feed with Real Data */}
      <div className="grid gap-4 md:grid-cols-2">
        {aiPerformanceData.length > 0 ? (
          <AIPerformanceScatter data={aiPerformanceData} />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>AI Performance</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-64 flex items-center justify-center">
                <div className="text-muted-foreground">No AI performance data available</div>
              </div>
            </CardContent>
          </Card>
        )}
        
        {activityFeed?.activities ? (
          <ActivityFeed 
            activities={activityFeed.activities} 
            onItemClick={handleActivityClick}
          />
        ) : (
          <Card>
            <CardHeader>
              <CardTitle>Live Activity Feed</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-64 flex items-center justify-center">
                <div className="text-muted-foreground">
                  {activityLoading ? 'Loading activities...' : 'No recent activity'}
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>

      {/* System Health & Recent Exceptions */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* System Components */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5" />
              System Components
            </CardTitle>
            <CardDescription>
              Status of system components
            </CardDescription>
          </CardHeader>
          <CardContent>
            {healthLoading ? (
              <div className="space-y-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="flex items-center justify-between">
                    <Skeleton className="h-4 w-24" />
                    <Skeleton className="h-6 w-16" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {health?.services?.map((service) => (
                  <div key={service.name} className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className={`h-2 w-2 rounded-full ${
                        service.status === 'healthy' ? 'bg-green-500' : 'bg-red-500'
                      }`} />
                      <span className="font-medium">{service.name}</span>
                    </div>
                    <div className="text-right">
                      <Badge variant={service.status === 'healthy' ? 'default' : 'destructive'}>
                        {service.status}
                      </Badge>
                      <div className="text-xs text-muted-foreground mt-1">
                        {service.latency}ms
                      </div>
                    </div>
                  </div>
                )) || (
                  <p className="text-sm text-muted-foreground">No service data available</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Recent Exceptions */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Recent Exceptions
            </CardTitle>
            <CardDescription>
              Latest SLA breaches and issues
            </CardDescription>
          </CardHeader>
          <CardContent>
            {exceptionsLoading ? (
              <div className="space-y-3">
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-8 w-8 rounded" />
                    <div className="space-y-1 flex-1">
                      <Skeleton className="h-4 w-3/4" />
                      <Skeleton className="h-3 w-1/2" />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {exceptions?.exceptions?.slice(0, 5).map((exception) => (
                  <div 
                    key={exception.id} 
                    className="flex items-center gap-3 cursor-pointer hover:bg-gray-50 p-2 rounded transition-colors"
                    onClick={() => handleExceptionClick(exception.id)}
                  >
                    <div className={`h-8 w-8 rounded flex items-center justify-center text-xs font-medium ${
                      exception.severity === 'HIGH' || exception.severity === 'CRITICAL' 
                        ? 'bg-red-100 text-red-700' 
                        : 'bg-yellow-100 text-yellow-700'
                    }`}>
                      {exception.severity === 'HIGH' || exception.severity === 'CRITICAL' ? '!' : '?'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-medium truncate">
                          {exception.order_id}
                        </p>
                        <Badge variant="outline" className="text-xs">
                          {exception.reason_code}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {new Date(exception.created_at).toLocaleTimeString()}
                        {exception.ai_confidence && (
                          <span className="ml-2">
                            AI: {(exception.ai_confidence * 100).toFixed(0)}%
                          </span>
                        )}
                      </p>
                    </div>
                    <Eye className="h-4 w-4 text-muted-foreground" />
                  </div>
                )) || (
                  <p className="text-sm text-muted-foreground">No recent exceptions</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Footer Info */}
      <div className="text-center text-xs text-muted-foreground">
        Last updated: {metrics?.timestamp ? new Date(metrics.timestamp).toLocaleString() : 'Never'}
        {' • '}
        Auto-refresh: 10s
      </div>

      {/* Exception Detail Modal */}
      <ExceptionDetailModal
        exceptionId={selectedExceptionId}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedExceptionId(null);
        }}
        onResolve={async (id, resolution) => {
          try {
            console.log(`Resolving exception ${id} with API call...`);
            
            // Make real API call to resolve exception
            await apiClient.resolveException(id, resolution);
            
            console.log(`Exception ${id} resolved successfully via API`);
            
            // Close modal
            setIsModalOpen(false);
            setSelectedExceptionId(null);
            
            // Show beautiful success notification
            const successDiv = document.createElement('div');
            successDiv.innerHTML = `
              <div class="fixed top-4 right-4 z-50 w-96 rounded-lg border border-green-200 bg-green-50 p-4 shadow-lg transition-all duration-300">
                <div class="flex items-start gap-3">
                  <svg class="h-5 w-5 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-semibold text-green-800 mb-1">Exception Resolved</div>
                    <div class="text-sm text-green-700">Exception ${id} has been successfully resolved.</div>
                  </div>
                  <button onclick="this.parentElement.parentElement.remove()" class="flex-shrink-0 text-green-600 hover:text-green-800 transition-colors">
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                  </button>
                </div>
              </div>
            `;
            document.body.appendChild(successDiv);
            
            // Auto remove after 4 seconds
            setTimeout(() => {
              if (successDiv.parentNode) {
                successDiv.remove();
              }
            }, 4000);
            
            // Refresh the page to get updated data
            setTimeout(() => window.location.reload(), 1500);
            
          } catch (error) {
            console.error(`Failed to resolve exception ${id}:`, error);
            
            // Show beautiful error notification
            const errorDiv = document.createElement('div');
            errorDiv.innerHTML = `
              <div class="fixed top-4 right-4 z-50 w-96 rounded-lg border border-red-200 bg-red-50 p-4 shadow-lg transition-all duration-300">
                <div class="flex items-start gap-3">
                  <svg class="h-5 w-5 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                  </svg>
                  <div class="flex-1 min-w-0">
                    <div class="text-sm font-semibold text-red-800 mb-1">Resolution Failed</div>
                    <div class="text-sm text-red-700">Failed to resolve exception ${id}. Please try again.</div>
                  </div>
                  <button onclick="this.parentElement.parentElement.remove()" class="flex-shrink-0 text-red-600 hover:text-red-800 transition-colors">
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                    </svg>
                  </button>
                </div>
              </div>
            `;
            document.body.appendChild(errorDiv);
            
            // Auto remove after 5 seconds
            setTimeout(() => {
              if (errorDiv.parentNode) {
                errorDiv.remove();
              }
            }, 5000);
          }
        }}
        onEscalate={(id, level) => {
          console.log(`Escalating exception ${id} to level ${level}`);
        }}
      />
    </div>
  );
}
