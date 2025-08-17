# Octup E²A Demo System

A minimal demo system with a pseudo-Shopify API to demonstrate Octup E²A.

## 🚀 Quick Start

```bash
# 1. Start the demo system
cd docker
docker-compose --profile demo up -d

# 2. Verify that everything is working
cd ../demo
python test_demo.py

# 3. Open interfaces
open http://localhost:8090/docs    # Shopify Mock API
open http://localhost:3000         # Octup Dashboard
```

## 🏗️ Architecture

```
┌─────────────────┐    webhooks    ┌─────────────────┐    dashboard    ┌─────────────────┐
│  Shopify Mock   │ ──────────────▶│   Octup E²A     │ ──────────────▶│   Dashboard     │
│     API         │                │      API        │                │   (Next.js)     │
│   Port 8090     │                │   Port 8000     │                │   Port 3000     │
└─────────────────┘                └─────────────────┘                └─────────────────┘
```

## 📡 Shopify Mock API

### Main Endpoints:
- `GET /admin/api/2023-10/orders.json` - list of orders
- `GET /admin/api/2023-10/orders/{id}.json` - order details  
- `POST /demo/generate-order` - create a demo order
- `GET /demo/stats` - demo statistics

### Automatic Webhooks:
When an order is created, the following are automatically sent:
1. **Order webhook** → `POST /api/ingest/events` (Octup E²A)
2. **Exception webhook** → `POST /api/exceptions` (if an exception occurs)

## 🎯 Demo Scenarios

### 1. Create Order with Exception
```bash
curl -X POST http://localhost:8090/demo/generate-order
```

### 2. View Orders
```bash
curl http://localhost:8090/admin/api/2023-10/orders.json?limit=5
```

### 3. Statistics
```bash
curl http://localhost:8090/demo/stats
```

## 🔧 Configuration

### Environment Variables:
- `OCTUP_API_URL` - URL of Octup E²A API (default: http://localhost:8000)
- `WEBHOOK_DELAY_SECONDS` - webhook delay (default: 2)

### Docker Compose:
```yaml
shopify-mock:
  build: ../demo/shopify-mock
  ports:
    - "8090:8090"
  environment:
    - OCTUP_API_URL=http://api:8000
  profiles:
    - demo
```

## 📊 Data

### Generated Orders:
- Realistic customer names (not "John Doe")
- Diverse emails (not @example.com)
- Varying order amounts (not $299.99)
- Real addresses (not "123 Main St")
- Real products (not "Premium Widget")

### Exception Types (13% of orders):
- `DELIVERY_DELAY` (5%) - delivery delays
- `ADDRESS_INVALID` (2%) - invalid address
- `PAYMENT_FAILED` (1.5%) - payment issues
- `INVENTORY_SHORTAGE` (2.5%) - out of stock
- `DAMAGED_PACKAGE` (0.8%) - shipping damage
- `CUSTOMER_UNAVAILABLE` (3%) - customer unavailable

## 🧪 Testing

```bash
# Run tests
python demo/test_demo.py

# Expected result:
# ✅ Shopify Mock API is healthy
# ✅ Generated order #12345
# 🚨 Exception created: DELIVERY_DELAY
# ✅ Octup E²A API is healthy
```

## 🎭 Advantages over the old system

| Old System | New System |
|----------------|---------------|
| ❌ CSV file dependency | ✅ Faker generation |
| ❌ Obvious mock data | ✅ Realistic data |
| ❌ Static scenarios | ✅ Dynamic webhooks |
| ❌ Complex setup | ✅ Simple docker-compose |

## 🔍 Monitoring

### Health checks:
- Shopify Mock: `http://localhost:8090/health`
- Octup E²A: `http://localhost:8000/healthz`

### Logs:
```bash
docker-compose logs -f shopify-mock
docker-compose logs -f api
```

A minimal yet fully functional demo system.