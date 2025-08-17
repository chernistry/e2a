'use client';

import React, { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  AlertTriangle, 
  Clock, 
  CheckCircle, 
  Search, 
  Filter,
  Eye,
  TrendingUp,
  BarChart3,
  Users,
  DollarSign
} from 'lucide-react';
import { apiClient, useApiData, Exception } from '@/lib/api';
import { ExceptionDetailModal } from '@/components/ui/exception-detail-modal';
import { KPICard, ExceptionDistribution } from '@/components/ui/enhanced-charts';

export default function ExceptionsPage() {
  const [selectedExceptionId, setSelectedExceptionId] = useState<number | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [reasonFilter, setReasonFilter] = useState<string>('all');

  const fetchExceptions = React.useCallback(() => apiClient.getLiveExceptions(100), []);
  
  const { 
    data: exceptions, 
    loading, 
    error 
  } = useApiData(fetchExceptions, 15000);

  // Filter and search exceptions
  const filteredExceptions = useMemo(() => {
    if (!exceptions?.exceptions) return [];

    return exceptions.exceptions.filter(exception => {
      const matchesSearch = exception.order_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
                           exception.reason_code.toLowerCase().includes(searchTerm.toLowerCase());
      
      const matchesSeverity = severityFilter === 'all' || exception.severity === severityFilter;
      const matchesStatus = statusFilter === 'all' || exception.status === statusFilter;
      const matchesReason = reasonFilter === 'all' || exception.reason_code === reasonFilter;

      return matchesSearch && matchesSeverity && matchesStatus && matchesReason;
    });
  }, [exceptions?.exceptions, searchTerm, severityFilter, statusFilter, reasonFilter]);

  // Get unique values for filters
  const uniqueReasons = useMemo(() => {
    if (!exceptions?.exceptions) return [];
    const reasonSet = new Set(exceptions.exceptions.map(e => e.reason_code));
    return Array.from(reasonSet);
  }, [exceptions?.exceptions]);

  // Calculate statistics
  const stats = useMemo(() => {
    if (!exceptions?.exceptions) return { total: 0, open: 0, resolved: 0, critical: 0, avgResolutionTime: 0 };

    const total = exceptions.exceptions.length;
    const open = exceptions.exceptions.filter(e => e.status === 'OPEN').length;
    const resolved = exceptions.exceptions.filter(e => e.status === 'RESOLVED').length;
    const critical = exceptions.exceptions.filter(e => e.severity === 'CRITICAL').length;

    // Mock average resolution time calculation
    const avgResolutionTime = 4.2; // hours

    return { total, open, resolved, critical, avgResolutionTime };
  }, [exceptions?.exceptions]);

  // Generate distribution data
  const distributionData = useMemo(() => {
    if (!exceptions?.exceptions) return [];

    const reasonCounts = exceptions.exceptions.reduce((acc, exception) => {
      acc[exception.reason_code] = (acc[exception.reason_code] || 0) + 1;
      return acc;
    }, {} as Record<string, number>);

    const colors = ['#ef4444', '#f59e0b', '#06b6d4', '#8b5cf6', '#10b981', '#f97316'];
    
    return Object.entries(reasonCounts)
      .map(([name, value], index) => ({
        name,
        value,
        color: colors[index % colors.length]
      }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 6);
  }, [exceptions?.exceptions]);

  const handleExceptionClick = (exception: Exception) => {
    setSelectedExceptionId(exception.id);
    setIsModalOpen(true);
  };

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight">Exceptions</h1>
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Failed to load exceptions data: {error}
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">SLA Exceptions</h1>
        <Badge variant="outline">
          {loading ? 'Loading...' : `${filteredExceptions.length} of ${exceptions?.count || 0} exceptions`}
        </Badge>
      </div>

      {/* Statistics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KPICard
          title="Total Exceptions"
          value={stats.total}
          icon={<BarChart3 className="h-4 w-4" />}
          status="good"
          description="All time"
        />

        <KPICard
          title="Open Cases"
          value={stats.open}
          icon={<AlertTriangle className="h-4 w-4" />}
          status={stats.open > 20 ? 'critical' : stats.open > 10 ? 'warning' : 'good'}
          description="Requiring attention"
        />

        <KPICard
          title="Resolved Today"
          value={stats.resolved}
          change={12.5}
          icon={<CheckCircle className="h-4 w-4" />}
          status="good"
          description="vs yesterday"
        />

        <KPICard
          title="Avg Resolution Time"
          value={stats.avgResolutionTime.toFixed(1)}
          unit="h"
          change={-8.3}
          icon={<Clock className="h-4 w-4" />}
          status="good"
          description="Target: <6h"
        />
      </div>

      {/* Exception Distribution */}
      <div className="grid gap-4 md:grid-cols-2">
        <ExceptionDistribution data={distributionData} />
        
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5" />
              Key Insights
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-blue-500 rounded-full" />
                <span className="font-medium text-blue-900">Peak Hours</span>
              </div>
              <p className="text-sm text-blue-800">
                Most exceptions occur between 2-4 PM during order processing peak
              </p>
            </div>
            
            <div className="p-3 bg-green-50 rounded-lg border border-green-200">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-green-500 rounded-full" />
                <span className="font-medium text-green-900">AI Success</span>
              </div>
              <p className="text-sm text-green-800">
                85% of exceptions are automatically categorized with high confidence
              </p>
            </div>

            <div className="p-3 bg-orange-50 rounded-lg border border-orange-200">
              <div className="flex items-center gap-2 mb-2">
                <div className="w-2 h-2 bg-orange-500 rounded-full" />
                <span className="font-medium text-orange-900">Action Needed</span>
              </div>
              <p className="text-sm text-orange-800">
                {stats.critical} critical exceptions require immediate attention
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters and Search */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Filter className="h-5 w-5" />
            Filters & Search
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-5">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search orders, reason codes..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>

            <Select value={severityFilter} onValueChange={setSeverityFilter}>
              <SelectTrigger>
                <SelectValue placeholder="Severity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Severities</SelectItem>
                <SelectItem value="CRITICAL">Critical</SelectItem>
                <SelectItem value="HIGH">High</SelectItem>
                <SelectItem value="MEDIUM">Medium</SelectItem>
                <SelectItem value="LOW">Low</SelectItem>
              </SelectContent>
            </Select>

            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="OPEN">Open</SelectItem>
                <SelectItem value="IN_PROGRESS">In Progress</SelectItem>
                <SelectItem value="RESOLVED">Resolved</SelectItem>
              </SelectContent>
            </Select>

            <Select value={reasonFilter} onValueChange={setReasonFilter}>
              <SelectTrigger>
                <SelectValue placeholder="Reason" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Reasons</SelectItem>
                {uniqueReasons.map(reason => (
                  <SelectItem key={reason} value={reason}>{reason}</SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Button 
              variant="outline" 
              onClick={() => {
                setSearchTerm('');
                setSeverityFilter('all');
                setStatusFilter('all');
                setReasonFilter('all');
              }}
            >
              Clear Filters
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Exceptions List */}
      <Tabs defaultValue="list" className="w-full">
        <TabsList>
          <TabsTrigger value="list">List View</TabsTrigger>
          <TabsTrigger value="cards">Card View</TabsTrigger>
        </TabsList>

        <TabsContent value="list" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Exception List</CardTitle>
              <CardDescription>
                Click on any exception to view detailed information
              </CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <div className="space-y-3">
                  {[...Array(10)].map((_, i) => (
                    <div key={i} className="flex items-center justify-between p-3 border rounded">
                      <div className="flex items-center gap-3">
                        <Skeleton className="h-8 w-8 rounded" />
                        <div className="space-y-1">
                          <Skeleton className="h-4 w-32" />
                          <Skeleton className="h-3 w-24" />
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Skeleton className="h-6 w-16" />
                        <Skeleton className="h-6 w-20" />
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="space-y-2">
                  {filteredExceptions.map((exception) => (
                    <div 
                      key={exception.id}
                      className="flex items-center justify-between p-3 border rounded hover:bg-gray-50 cursor-pointer transition-colors"
                      onClick={() => handleExceptionClick(exception)}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`h-8 w-8 rounded flex items-center justify-center text-xs font-medium ${
                          exception.severity === 'CRITICAL' ? 'bg-red-100 text-red-700' :
                          exception.severity === 'HIGH' ? 'bg-orange-100 text-orange-700' :
                          exception.severity === 'MEDIUM' ? 'bg-yellow-100 text-yellow-700' :
                          'bg-blue-100 text-blue-700'
                        }`}>
                          {exception.severity === 'CRITICAL' || exception.severity === 'HIGH' ? '!' : '?'}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{exception.order_id}</span>
                            <Badge variant="outline" className="text-xs">
                              {exception.reason_code}
                            </Badge>
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {new Date(exception.created_at).toLocaleString()}
                            {exception.ai_confidence && (
                              <span className="ml-2 text-blue-600">
                                AI: {(exception.ai_confidence * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge variant={
                          exception.status === 'RESOLVED' ? 'default' : 
                          exception.status === 'OPEN' ? 'destructive' : 'secondary'
                        }>
                          {exception.status}
                        </Badge>
                        <Badge variant={
                          exception.severity === 'CRITICAL' ? 'destructive' :
                          exception.severity === 'HIGH' ? 'destructive' :
                          exception.severity === 'MEDIUM' ? 'default' : 'secondary'
                        }>
                          {exception.severity}
                        </Badge>
                        <Eye className="h-4 w-4 text-muted-foreground" />
                      </div>
                    </div>
                  ))}
                  
                  {filteredExceptions.length === 0 && (
                    <div className="text-center py-8">
                      <CheckCircle className="h-12 w-12 text-green-500 mx-auto mb-2" />
                      <p className="text-lg font-medium">No exceptions found</p>
                      <p className="text-sm text-muted-foreground">
                        {searchTerm || severityFilter !== 'all' || statusFilter !== 'all' || reasonFilter !== 'all'
                          ? 'Try adjusting your filters'
                          : 'All SLAs are being met'
                        }
                      </p>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="cards" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {loading ? (
              [...Array(6)].map((_, i) => (
                <Card key={i}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <Skeleton className="h-6 w-32" />
                      <Skeleton className="h-5 w-20" />
                    </div>
                    <Skeleton className="h-4 w-full" />
                  </CardHeader>
                  <CardContent>
                    <Skeleton className="h-4 w-3/4" />
                  </CardContent>
                </Card>
              ))
            ) : (
              filteredExceptions.map((exception) => (
                <Card 
                  key={exception.id} 
                  className="cursor-pointer hover:shadow-md transition-shadow"
                  onClick={() => handleExceptionClick(exception)}
                >
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        <AlertTriangle className={`h-5 w-5 ${
                          exception.severity === 'CRITICAL' ? 'text-red-500' :
                          exception.severity === 'HIGH' ? 'text-orange-500' :
                          exception.severity === 'MEDIUM' ? 'text-yellow-500' :
                          'text-blue-500'
                        }`} />
                        {exception.order_id}
                      </CardTitle>
                      <Badge variant={
                        exception.status === 'RESOLVED' ? 'default' : 
                        exception.status === 'OPEN' ? 'destructive' : 'secondary'
                      }>
                        {exception.status}
                      </Badge>
                    </div>
                    <CardDescription className="flex items-center gap-2">
                      <Clock className="h-4 w-4" />
                      {new Date(exception.created_at).toLocaleString()}
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <Badge variant="outline">{exception.reason_code}</Badge>
                        <Badge variant={
                          exception.severity === 'CRITICAL' ? 'destructive' :
                          exception.severity === 'HIGH' ? 'destructive' :
                          exception.severity === 'MEDIUM' ? 'default' : 'secondary'
                        }>
                          {exception.severity}
                        </Badge>
                      </div>
                      {exception.ai_confidence && (
                        <div className="text-sm text-blue-600">
                          AI Confidence: {(exception.ai_confidence * 100).toFixed(0)}%
                        </div>
                      )}
                      {exception.ops_note && (
                        <p className="text-sm text-muted-foreground truncate">
                          {exception.ops_note}
                        </p>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))
            )}
          </div>
        </TabsContent>
      </Tabs>

      <div className="text-center text-xs text-muted-foreground">
        Auto-refresh: 15s • Last updated: {exceptions?.timestamp ? new Date(exceptions.timestamp).toLocaleString() : 'Never'}
      </div>

      {/* Exception Detail Modal */}
      <ExceptionDetailModal
        exceptionId={selectedExceptionId}
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setSelectedExceptionId(null);
        }}
        onResolve={(id, resolution) => {
          console.log(`Resolving exception ${id} with: ${resolution}`);
          setIsModalOpen(false);
          setSelectedExceptionId(null);
        }}
        onEscalate={(id, level) => {
          console.log(`Escalating exception ${id} to level ${level}`);
        }}
      />
    </div>
  );
}
