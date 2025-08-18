'use client';

import React, { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import {
  AlertTriangle,
  Clock,
  User,
  Package,
  MapPin,
  DollarSign,
  Truck,
  Calendar,
  FileText,
  Brain,
  Target,
  TrendingUp,
  ExternalLink,
  Copy,
  CheckCircle,
  XCircle,
  AlertCircle,
  Info
} from 'lucide-react';
import { Exception, apiClient } from '@/lib/api';

// Extended exception data with additional context
interface ExtendedExceptionData extends Exception {
  // Order details
  order_details?: {
    customer_name: string;
    customer_email: string;
    order_value: number;
    currency: string;
    shipping_address: string;
    order_date: string;
    expected_delivery: string;
    priority: 'standard' | 'express' | 'overnight';
    items: Array<{
      sku: string;
      name: string;
      quantity: number;
      price: number;
    }>;
  };
  
  // SLA details
  sla_details?: {
    sla_type: string;
    target_time: number;
    elapsed_time: number;
    remaining_time: number;
    breach_severity: 'minor' | 'major' | 'critical';
    escalation_level: number;
  };
  
  // Processing timeline
  timeline?: Array<{
    timestamp: string;
    event: string;
    actor: string;
    details: string;
    status: 'completed' | 'failed' | 'pending';
  }>;
  
  // AI analysis details
  ai_analysis?: {
    model_version: string;
    processing_time_ms: number;
    confidence_breakdown: Record<string, number>;
    similar_cases: Array<{
      case_id: string;
      similarity: number;
      resolution: string;
    }>;
    recommended_actions: Array<{
      action: string;
      priority: number;
      estimated_impact: string;
    }>;
  };
  
  // Financial impact
  financial_impact?: {
    potential_penalty: number;
    recovery_cost: number;
    customer_compensation: number;
    total_impact: number;
    currency: string;
  };
}

interface ExceptionDetailModalProps {
  exceptionId: number | null;
  isOpen: boolean;
  onClose: () => void;
  onResolve?: (exceptionId: number, resolution: string) => void;
  onEscalate?: (exceptionId: number, level: number) => void;
}

export const ExceptionDetailModal: React.FC<ExceptionDetailModalProps> = ({
  exceptionId,
  isOpen,
  onClose,
  onResolve,
  onEscalate
}) => {
  const [exception, setException] = useState<ExtendedExceptionData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch exception details when modal opens and exceptionId changes
  useEffect(() => {
    if (isOpen && exceptionId) {
      setLoading(true);
      setError(null);
      
      apiClient.getExceptionDetails(exceptionId)
        .then((data) => {
          setException(data as ExtendedExceptionData);
        })
        .catch((err) => {
          console.error('Failed to fetch exception details:', err);
          setError('Failed to load exception details');
        })
        .finally(() => {
          setLoading(false);
        });
    } else {
      setException(null);
    }
  }, [isOpen, exceptionId]);

  if (!isOpen) return null;

  if (loading) {
    return (
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className='max-w-7xl max-h-[90vh] overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>Loading Exception Details</DialogTitle>
          </DialogHeader>
          <div className="flex items-center justify-center py-8">
            <div className="text-muted-foreground">Loading exception details...</div>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  if (error || !exception) {
    return (
      <Dialog open={isOpen} onOpenChange={onClose}>
        <DialogContent className='max-w-7xl max-h-[90vh] overflow-y-auto'>
          <DialogHeader>
            <DialogTitle>Exception Not Found</DialogTitle>
          </DialogHeader>
          <div className="flex items-center justify-center py-8">
            <div className="text-red-600">{error || 'Exception not found'}</div>
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return <XCircle className="h-5 w-5 text-red-500" />;
      case 'high': return <AlertTriangle className="h-5 w-5 text-orange-500" />;
      case 'medium': return <AlertCircle className="h-5 w-5 text-yellow-500" />;
      case 'low': return <Info className="h-5 w-5 text-blue-500" />;
      default: return <AlertTriangle className="h-5 w-5 text-gray-500" />;
    }
  };

  const getSeverityColor = (severity: string) => {
    switch (severity.toLowerCase()) {
      case 'critical': return 'bg-red-50 text-red-700 border-red-200';
      case 'high': return 'bg-orange-50 text-orange-700 border-orange-200';
      case 'medium': return 'bg-yellow-50 text-yellow-700 border-yellow-200';
      case 'low': return 'bg-blue-50 text-blue-700 border-blue-200';
      default: return 'bg-gray-50 text-gray-700 border-gray-200';
    }
  };

  const formatCurrency = (amount: number, currency: string = 'USD') => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency
    }).format(amount);
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className='max-w-7xl max-h-[90vh] overflow-y-auto'>
        <DialogHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {getSeverityIcon(exception.severity)}
              <div>
                <DialogTitle className="text-xl">
                  Exception #{exception.id} - Order {exception.order_id}
                </DialogTitle>
                <DialogDescription className="flex items-center gap-2 mt-1">
                  <Badge variant="outline">{exception.reason_code}</Badge>
                  <Badge className={getSeverityColor(exception.severity)}>
                    {exception.severity}
                  </Badge>
                  <Badge variant={exception.status === 'RESOLVED' ? 'default' : 'destructive'}>
                    {exception.status}
                  </Badge>
                </DialogDescription>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => copyToClipboard(exception.order_id)}
            >
              <Copy className="h-4 w-4 mr-2" />
              Copy Order ID
            </Button>
          </div>
        </DialogHeader>

        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="order">Order Details</TabsTrigger>
            <TabsTrigger value="timeline">Timeline</TabsTrigger>
            <TabsTrigger value="ai-analysis">AI Analysis</TabsTrigger>
            <TabsTrigger value="actions">Actions</TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="space-y-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Left Column */}
              <div className="space-y-4">
                {/* SLA Status */}
                {exception.sla_details && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Target className="h-5 w-5" />
                        SLA Status
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-3">
                        <div className="flex justify-between items-center">
                          <span className="text-sm">Progress</span>
                          <span className="text-sm font-medium">
                            {exception.sla_details.elapsed_time}h / {exception.sla_details.target_time}h
                          </span>
                        </div>
                        <Progress 
                          value={(exception.sla_details.elapsed_time / exception.sla_details.target_time) * 100} 
                          className="h-2"
                        />
                        <div className="grid grid-cols-2 gap-4 text-sm">
                          <div>
                            <span className="text-muted-foreground">Remaining:</span>
                            <div className="font-medium">{exception.sla_details.remaining_time}h</div>
                          </div>
                          <div>
                            <span className="text-muted-foreground">Escalation:</span>
                            <div className="font-medium">Level {exception.sla_details.escalation_level}</div>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Exception Details */}
                <Card>
                  <CardHeader>
                    <CardTitle>Exception Details</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm text-muted-foreground">Created:</span>
                        <span className="text-sm font-medium">
                          {new Date(exception.created_at).toLocaleString()}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <User className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm text-muted-foreground">Tenant:</span>
                        <span className="text-sm font-medium">{exception.tenant}</span>
                      </div>
                      {exception.correlation_id && (
                        <div className="flex items-center gap-2">
                          <FileText className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm text-muted-foreground">Correlation ID:</span>
                          <span className="text-sm font-mono">{exception.correlation_id}</span>
                        </div>
                      )}
                      {exception.ops_note && (
                        <div>
                          <span className="text-sm font-medium text-muted-foreground">Operations Note:</span>
                          <p className="text-sm mt-1 p-2 bg-gray-50 rounded">{exception.ops_note}</p>
                        </div>
                      )}
                      {exception.client_note && (
                        <div>
                          <span className="text-sm font-medium text-muted-foreground">Client Note:</span>
                          <p className="text-sm mt-1 p-2 bg-blue-50 rounded">{exception.client_note}</p>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Right Column */}
              <div className="space-y-4">
                {/* Financial Impact */}
                {exception.financial_impact && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <DollarSign className="h-5 w-5" />
                        Financial Impact
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="space-y-2">
                        <div className="flex justify-between">
                          <span className="text-sm text-muted-foreground">Potential Penalty:</span>
                          <span className="font-medium text-red-600">
                            {formatCurrency(exception.financial_impact.potential_penalty, exception.financial_impact.currency)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-muted-foreground">Recovery Cost:</span>
                          <span className="font-medium">
                            {formatCurrency(exception.financial_impact.recovery_cost, exception.financial_impact.currency)}
                          </span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-sm text-muted-foreground">Customer Compensation:</span>
                          <span className="font-medium">
                            {formatCurrency(exception.financial_impact.customer_compensation, exception.financial_impact.currency)}
                          </span>
                        </div>
                        <Separator />
                        <div className="flex justify-between font-semibold">
                          <span>Total Impact:</span>
                          <span className="text-red-600">
                            {formatCurrency(exception.financial_impact.total_impact, exception.financial_impact.currency)}
                          </span>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Quick Actions */}
                <Card>
                  <CardHeader>
                    <CardTitle>Quick Actions</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <Button 
                      className="w-full justify-start" 
                      variant="outline"
                      onClick={() => onResolve?.(exception.id, 'Manual resolution')}
                    >
                      <CheckCircle className="h-4 w-4 mr-2" />
                      Mark as Resolved
                    </Button>
                    <Button 
                      className="w-full justify-start" 
                      variant="outline"
                      onClick={() => onEscalate?.(exception.id, (exception.sla_details?.escalation_level || 0) + 1)}
                    >
                      <TrendingUp className="h-4 w-4 mr-2" />
                      Escalate
                    </Button>
                    <Button className="w-full justify-start" variant="outline">
                      <ExternalLink className="h-4 w-4 mr-2" />
                      View in CRM
                    </Button>
                  </CardContent>
                </Card>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="order" className="space-y-4">
            {exception.order_details ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Customer Information */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <User className="h-5 w-5" />
                      Customer Information
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div>
                      <span className="text-sm text-muted-foreground">Name:</span>
                      <div className="font-medium">{exception.order_details.customer_name}</div>
                    </div>
                    <div>
                      <span className="text-sm text-muted-foreground">Email:</span>
                      <div className="font-medium">{exception.order_details.customer_email}</div>
                    </div>
                    <div>
                      <span className="text-sm text-muted-foreground">Shipping Address:</span>
                      <div className="font-medium">{exception.order_details.shipping_address}</div>
                    </div>
                  </CardContent>
                </Card>

                {/* Order Information */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Package className="h-5 w-5" />
                      Order Information
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Order Value:</span>
                      <span className="font-medium">
                        {formatCurrency(exception.order_details.order_value, exception.order_details.currency)}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Priority:</span>
                      <Badge variant="outline">{exception.order_details.priority}</Badge>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Order Date:</span>
                      <span className="font-medium">
                        {new Date(exception.order_details.order_date).toLocaleDateString()}
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-sm text-muted-foreground">Expected Delivery:</span>
                      <span className="font-medium">
                        {new Date(exception.order_details.expected_delivery).toLocaleDateString()}
                      </span>
                    </div>
                  </CardContent>
                </Card>

                {/* Order Items */}
                <Card className="md:col-span-2">
                  <CardHeader>
                    <CardTitle>Order Items</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {exception.order_details.items.map((item, index) => (
                        <div key={index} className="flex justify-between items-center p-2 bg-gray-50 rounded">
                          <div>
                            <div className="font-medium">{item.name}</div>
                            <div className="text-sm text-muted-foreground">SKU: {item.sku}</div>
                          </div>
                          <div className="text-right">
                            <div className="font-medium">Qty: {item.quantity}</div>
                            <div className="text-sm text-muted-foreground">
                              {formatCurrency(item.price, exception.order_details.currency)}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card>
                <CardContent className="flex items-center justify-center py-8">
                  <p className="text-muted-foreground">Order details not available</p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="timeline" className="space-y-4">
            {exception.timeline ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Calendar className="h-5 w-5" />
                    Processing Timeline
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4">
                    {exception.timeline.map((event, index) => (
                      <div key={index} className="flex gap-4">
                        <div className="flex flex-col items-center">
                          <div className={`w-3 h-3 rounded-full ${
                            event.status === 'completed' ? 'bg-green-500' :
                            event.status === 'failed' ? 'bg-red-500' : 'bg-yellow-500'
                          }`} />
                          {index < exception.timeline!.length - 1 && (
                            <div className="w-px h-8 bg-gray-200 mt-2" />
                          )}
                        </div>
                        <div className="flex-1 pb-4">
                          <div className="flex justify-between items-start">
                            <div>
                              <div className="font-medium">{event.event}</div>
                              <div className="text-sm text-muted-foreground">{event.details}</div>
                              <div className="text-xs text-muted-foreground mt-1">
                                by {event.actor}
                              </div>
                            </div>
                            <div className="text-xs text-muted-foreground">
                              {new Date(event.timestamp).toLocaleString()}
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="flex items-center justify-center py-8">
                  <p className="text-muted-foreground">Timeline not available</p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="ai-analysis" className="space-y-4">
            {exception.ai_analysis ? (
              <div className="space-y-4">
                {/* AI Confidence Breakdown */}
                <Card>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      <Brain className="h-5 w-5" />
                      AI Analysis Results
                    </CardTitle>
                    <CardDescription>
                      Model: {exception.ai_analysis.model_version} • 
                      Processing time: {exception.ai_analysis.processing_time_ms}ms
                    </CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-3">
                      {Object.entries(exception.ai_analysis.confidence_breakdown).map(([category, confidence]) => (
                        <div key={category}>
                          <div className="flex justify-between text-sm mb-1">
                            <span>{category}</span>
                            <span>{(confidence * 100).toFixed(1)}%</span>
                          </div>
                          <Progress value={confidence * 100} className="h-2" />
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* Similar Cases */}
                <Card>
                  <CardHeader>
                    <CardTitle>Similar Cases</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {exception.ai_analysis.similar_cases.map((case_item, index) => (
                        <div key={index} className="flex justify-between items-center p-2 bg-gray-50 rounded">
                          <div>
                            <div className="font-medium">Case #{case_item.case_id}</div>
                            <div className="text-sm text-muted-foreground">{case_item.resolution}</div>
                          </div>
                          <Badge variant="outline">
                            {(case_item.similarity * 100).toFixed(0)}% match
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>

                {/* Recommended Actions */}
                <Card>
                  <CardHeader>
                    <CardTitle>Recommended Actions</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {exception.ai_analysis.recommended_actions
                        .sort((a, b) => b.priority - a.priority)
                        .map((action, index) => (
                        <div key={index} className="flex justify-between items-center p-3 border rounded">
                          <div>
                            <div className="font-medium">{action.action}</div>
                            <div className="text-sm text-muted-foreground">{action.estimated_impact}</div>
                          </div>
                          <Badge variant={action.priority > 7 ? 'destructive' : action.priority > 4 ? 'default' : 'secondary'}>
                            Priority {action.priority}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            ) : (
              <Card>
                <CardContent className="flex items-center justify-center py-8">
                  <p className="text-muted-foreground">AI analysis not available</p>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="actions" className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Card>
                <CardHeader>
                  <CardTitle>Quick Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Button 
                    className="w-full justify-start" 
                    variant="outline"
                    onClick={() => onResolve?.(exception.id, 'Manual resolution')}
                  >
                    <CheckCircle className="h-4 w-4 mr-2" />
                    Mark as Resolved
                  </Button>
                  <Button 
                    className="w-full justify-start" 
                    variant="outline"
                    onClick={() => onEscalate?.(exception.id, (exception.sla_details?.escalation_level || 0) + 1)}
                  >
                    <TrendingUp className="h-4 w-4 mr-2" />
                    Escalate
                  </Button>
                  <Button className="w-full justify-start" variant="outline">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    View in CRM
                  </Button>
                  <Button className="w-full justify-start" variant="outline">
                    <FileText className="h-4 w-4 mr-2" />
                    Generate Report
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Communication</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  <Button className="w-full justify-start" variant="outline">
                    <User className="h-4 w-4 mr-2" />
                    Contact Customer
                  </Button>
                  <Button className="w-full justify-start" variant="outline">
                    <Truck className="h-4 w-4 mr-2" />
                    Update Carrier
                  </Button>
                  <Button className="w-full justify-start" variant="outline">
                    <AlertTriangle className="h-4 w-4 mr-2" />
                    Send Alert
                  </Button>
                </CardContent>
              </Card>
            </div>
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
};
