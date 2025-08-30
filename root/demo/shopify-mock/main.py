#!/usr/bin/env python3
"""
Shopify Mock API Server

Minimal Shopify API simulation for Octup E²A demo.
Provides realistic orders, customers, and webhook simulation.
"""

import asyncio
import os
import random
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn

from data.generator import ShopifyDataGenerator


# Configuration from environment
OCTUP_API_URL = os.getenv("OCTUP_API_URL", "http://localhost:8000")
WEBHOOK_DELAY_SECONDS = int(os.getenv("WEBHOOK_DELAY_SECONDS", "2"))

# Orders generation configuration
SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS = int(os.getenv("SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS", "1001"))
SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS = int(os.getenv("SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS", "1999"))

print(f"🎲 Shopify Mock API configured to generate {SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS}-{SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS} orders per batch")

app = FastAPI(
    title="Shopify Mock API",
    description="Mock Shopify API for Octup E²A demo",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global data store (in-memory for demo)
generator = ShopifyDataGenerator(seed=42)
orders_db: Dict[str, Dict] = {}
customers_db: Dict[str, Dict] = {}
products_db: Dict[str, Dict] = {}

# Initialize some demo data
def init_demo_data():
    """Initialize demo data on startup."""
    print("🚀 Initializing Shopify Mock API demo data...")
    
    # Generate customers (enough for realistic distribution)
    print("👥 Generating customers...")
    for _ in range(500):  # More customers for realistic distribution
        customer = generator.generate_customer()
        customers_db[customer['id']] = customer
    
    # Generate products
    print("📦 Generating products...")
    for category in ['electronics', 'clothing', 'home_garden', 'books']:  # Only existing categories
        for _ in range(20):  # More products for variety
            product = generator.generate_product_variant(category)
            products_db[product['id']] = product
    
    print(f"✅ Demo data initialized: {len(customers_db)} customers, {len(products_db)} products")


def generate_batch_orders():
    """Generate a batch of orders for API consumption."""
    # Determine how many orders to generate this batch
    batch_size = random.randint(SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS, SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS)
    
    print(f"🎲 Generating batch of {batch_size} orders...")
    
    new_orders = []
    for _ in range(batch_size):
        order, problem = generator.generate_order_with_problems()
        
        # Store in memory
        orders_db[order['id']] = {
            **order,
            'has_problems': problem is not None,
            'problem_type': problem['type'] if problem else None
        }
        
        new_orders.append(order)
    
    problems_count = sum(1 for o in orders_db.values() if o.get('has_problems'))
    print(f"✅ Generated {len(new_orders)} new orders (total: {len(orders_db)}, {problems_count} with problems)")
    return new_orders

@app.on_event("startup")
async def startup_event():
    init_demo_data()


# Shopify Admin API Routes
@app.get("/admin/api/2023-10/orders.json")
async def get_orders(
    limit: int = 50,
    status: Optional[str] = None,
    financial_status: Optional[str] = None,
    generate_new: bool = True  # Flag to generate new batch
):
    """Get orders list (Shopify format)."""
    
    # Generate new batch if requested and we have few orders
    if generate_new and len(orders_db) < limit:
        print(f"📊 Current orders: {len(orders_db)}, requested: {limit}")
        print("🎲 Generating new batch of orders...")
        generate_batch_orders()
    
    orders = list(orders_db.values())
    
    # Apply filters
    if status:
        orders = [o for o in orders if o.get('fulfillment_status') == status]
    if financial_status:
        orders = [o for o in orders if o.get('financial_status') == financial_status]
    
    # Sort by creation date (newest first)
    orders.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Limit results
    orders = orders[:limit]
    
    print(f"📤 Returning {len(orders)} orders to client")
    
    return {"orders": orders}


@app.get("/admin/api/2023-10/orders/{order_id}.json")
async def get_order(order_id: str):
    """Get single order (Shopify format)."""
    if order_id not in orders_db:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {"order": orders_db[order_id]}


@app.post("/admin/api/2023-10/orders.json")
async def create_order(order_data: Dict[str, Any], background_tasks: BackgroundTasks):
    """Create new order and trigger webhook."""
    # Generate new order
    order, problem = generator.generate_order_with_problems()
    orders_db[order['id']] = {
        **order,
        'has_problems': problem is not None,
        'problem_type': problem['type'] if problem else None
    }
    
    # Schedule webhook (only send order data, let the system detect problems)
    background_tasks.add_task(send_webhook, "orders/create", order)
    
    return {"order": order}


@app.get("/admin/api/2023-10/customers.json")
async def get_customers(limit: int = 50):
    """Get customers list."""
    customers = list(customers_db.values())[:limit]
    return {"customers": customers}


@app.get("/admin/api/2023-10/products.json")
async def get_products(limit: int = 50):
    """Get products list."""
    products = list(products_db.values())[:limit]
    return {"products": products}


# Webhook simulation
async def send_webhook(topic: str, order: Dict):
    """Send webhook to Octup E²A API."""
    await asyncio.sleep(WEBHOOK_DELAY_SECONDS)
    
    webhook_payload = {
        "event_id": f"shopify_{topic}_{order['id']}",
        "event_type": "order_created" if topic == "orders/create" else topic.replace("/", "_"),
        "source": "shopify",
        "tenant": "demo-3pl",
        "occurred_at": datetime.now().isoformat(),
        "order_id": order['name'],
        "data": {
            "order": order,
            "webhook_topic": topic
        }
    }
    
    try:
        async with httpx.AsyncClient() as client:
            # Send order event - let the system analyze and detect problems
            response = await client.post(
                f"{OCTUP_API_URL}/ingest/events",
                json=webhook_payload,
                headers={"X-Tenant-Id": "demo-3pl"}
            )
            print(f"Webhook sent: {topic} for order {order['name']} - Status: {response.status_code}")
            
            # Send additional fulfillment events based on order status
            if topic == "orders/create" and order.get('fulfillment_status') in ['fulfilled', 'shipped', 'delivered']:
                await send_fulfillment_events(order)
                
    except Exception as e:
        print(f"Webhook failed: {e}")


async def send_fulfillment_events(order: Dict):
    """Send fulfillment events based on order status."""
    fulfillment_status = order.get('fulfillment_status', 'pending')
    
    # Base fulfillment events for completed orders
    events_to_send = []
    
    if fulfillment_status in ['fulfilled', 'shipped', 'delivered']:
        events_to_send.extend([
            ("order_paid", {"payment_method": "card"}),
            ("pick_completed", {"picker": "worker"}),
            ("pack_completed", {"packer": "worker"}),
            ("ship_label_printed", {"tracking": f"TRACK{order['id']}"})
        ])
    
    if fulfillment_status in ['fulfilled', 'shipped', 'delivered']:
        events_to_send.append(("order_fulfilled", {"status": "completed"}))
    
    if fulfillment_status in ['shipped', 'delivered']:
        events_to_send.append(("package_shipped", {"carrier": "UPS"}))
    
    if fulfillment_status == 'delivered':
        events_to_send.append(("delivered", {"delivery_date": datetime.now().isoformat()}))
    
    # Send each fulfillment event
    for event_type, payload in events_to_send:
        await asyncio.sleep(1)  # Small delay between events
        
        event_payload = {
            "event_id": f"shopify_{event_type}_{order['id']}",
            "event_type": event_type,
            "source": "shopify",
            "tenant": "demo-3pl",
            "occurred_at": datetime.now().isoformat(),
            "order_id": order['name'],
            "data": payload
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{OCTUP_API_URL}/ingest/events",
                    json=event_payload,
                    headers={"X-Tenant-Id": "demo-3pl"}
                )
                print(f"Fulfillment event sent: {event_type} for order {order['name']} - Status: {response.status_code}")
        except Exception as e:
            print(f"Fulfillment event failed: {e}")


async def send_batch_webhook(events: List[Dict]):
    """Send batch webhook to Octup E²A optimized API."""
    await asyncio.sleep(WEBHOOK_DELAY_SECONDS)
    
    batch_payload = {
        "events": events,
        "batch_id": f"batch_{int(time.time())}",
        "priority": "normal"
    }
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Try optimized batch endpoint first
            try:
                response = await client.post(
                    f"{OCTUP_API_URL}/ingest/v2/events/batch",
                    json=batch_payload,
                    headers={"X-Tenant-Id": "demo-3pl"}
                )
                
                if response.status_code == 200:
                    result = response.json()
                    print(f"Batch webhook sent: {result.get('processed_count', 0)} events processed - Status: {response.status_code}")
                    return
                else:
                    print(f"Batch webhook failed with status {response.status_code}, falling back to individual webhooks")
                    
            except Exception as batch_error:
                print(f"Batch webhook failed: {batch_error}, falling back to individual webhooks")
            
            # Fallback to individual webhooks
            success_count = 0
            for event_data in events:
                try:
                    response = await client.post(
                        f"{OCTUP_API_URL}/ingest/events",
                        json=event_data,
                        headers={"X-Tenant-Id": "demo-3pl"}
                    )
                    if response.status_code == 200:
                        success_count += 1
                except Exception:
                    continue
            
            print(f"Fallback webhooks sent: {success_count}/{len(events)} events processed")
            
    except Exception as e:
        print(f"All webhook attempts failed: {e}")


# Demo endpoints
@app.post("/demo/generate-batch")
async def generate_demo_batch(background_tasks: BackgroundTasks):
    """Generate a new batch of orders (1001-1999 orders) and send webhooks via batch API."""
    batch_size = random.randint(SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS, SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS)
    
    print(f"🎯 Manual batch generation requested: {batch_size} orders")
    
    new_orders = generate_batch_orders()
    
    # Send batch webhook to optimized API
    print(f"📡 Sending batch of {len(new_orders)} events to optimized API...")
    
    # Prepare batch payload
    batch_events = []
    for order in new_orders:
        event_data = {
            "event_id": f"shopify_orders_create_{order['id']}",
            "event_type": "order_created",
            "order_id": order['name'],
            "occurred_at": datetime.now().isoformat(),
            "source": "shopify",
            "data": {
                "order": order,
                "webhook_topic": "orders/create"
            }
        }
        batch_events.append(event_data)
    
    # Send batch request
    background_tasks.add_task(send_batch_webhook, batch_events)
    
    # Count problems
    orders_with_problems = sum(1 for o in orders_db.values() if o.get('has_problems'))
    
    return {
        "message": f"Generated batch of {len(new_orders)} orders",
        "batch_size": len(new_orders),
        "total_orders": len(orders_db),
        "orders_with_problems": orders_with_problems,
        "problem_rate": f"{(orders_with_problems/len(orders_db)*100):.1f}%" if orders_db else "0%",
        "batch_events_queued": len(batch_events),
        "config": {
            "min_orders": SHOPIFY_DEMO_API_PRODUCE_MIN_ORDERS,
            "max_orders": SHOPIFY_DEMO_API_PRODUCE_MAX_ORDERS
        }
    }


@app.post("/demo/clear-orders")
async def clear_demo_orders():
    """Clear all orders (keep customers and products)."""
    orders_count = len(orders_db)
    orders_db.clear()
    
    print(f"🗑️  Cleared {orders_count} orders")
    
    return {
        "message": f"Cleared {orders_count} orders",
        "remaining_orders": len(orders_db),
        "customers": len(customers_db),
        "products": len(products_db)
    }


@app.post("/demo/generate-order")
async def generate_demo_order(background_tasks: BackgroundTasks):
    """Generate a single demo order with potential problems."""
    order, problem = generator.generate_order_with_problems()
    
    orders_db[order['id']] = {
        **order,
        'has_problems': problem is not None,
        'problem_type': problem['type'] if problem else None
    }
    
    # Send webhook (let system detect problems)
    background_tasks.add_task(send_webhook, "orders/create", order)
    
    return {
        "message": "Demo order generated",
        "order_id": order['name'],
        "has_problems": problem is not None,
        "problem_type": problem['type'] if problem else None
    }


@app.get("/demo/stats")
async def get_demo_stats():
    """Get demo statistics."""
    total_orders = len(orders_db)
    orders_with_problems = sum(1 for o in orders_db.values() if o.get('has_problems'))
    
    return {
        "total_orders": total_orders,
        "total_customers": len(customers_db),
        "total_products": len(products_db),
        "orders_with_problems": orders_with_problems,
        "problem_rate": f"{(orders_with_problems/total_orders*100):.1f}%" if total_orders > 0 else "0%"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "shopify-mock",
        "timestamp": datetime.now().isoformat(),
        "orders_count": len(orders_db)
    }


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8090,
        reload=True,
        log_level="info"
    )
