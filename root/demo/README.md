# Octup E²A Demo System

Минимальная демо-система с псевдо-Shopify API для демонстрации Octup E²A.

## 🚀 Быстрый старт

```bash
# 1. Запустить демо-систему
cd docker
docker-compose --profile demo up -d

# 2. Проверить что все работает
cd ../demo
python test_demo.py

# 3. Открыть интерфейсы
open http://localhost:8090/docs    # Shopify Mock API
open http://localhost:3000         # Octup Dashboard
```

## 🏗️ Архитектура

```
┌─────────────────┐    webhooks    ┌─────────────────┐    dashboard    ┌─────────────────┐
│  Shopify Mock   │ ──────────────▶│   Octup E²A     │ ──────────────▶│   Dashboard     │
│     API         │                │      API        │                │   (Next.js)     │
│   Port 8090     │                │   Port 8000     │                │   Port 3000     │
└─────────────────┘                └─────────────────┘                └─────────────────┘
```

## 📡 Shopify Mock API

### Основные эндпойнты:
- `GET /admin/api/2023-10/orders.json` - список заказов
- `GET /admin/api/2023-10/orders/{id}.json` - детали заказа  
- `POST /demo/generate-order` - создать демо-заказ
- `GET /demo/stats` - статистика демо

### Автоматические webhook'и:
При создании заказа автоматически отправляются:
1. **Order webhook** → `POST /api/ingest/events` (Octup E²A)
2. **Exception webhook** → `POST /api/exceptions` (если есть исключение)

## 🎯 Демо-сценарии

### 1. Создание заказа с исключением
```bash
curl -X POST http://localhost:8090/demo/generate-order
```

### 2. Просмотр заказов
```bash
curl http://localhost:8090/admin/api/2023-10/orders.json?limit=5
```

### 3. Статистика
```bash
curl http://localhost:8090/demo/stats
```

## 🔧 Конфигурация

### Environment переменные:
- `OCTUP_API_URL` - URL Octup E²A API (default: http://localhost:8000)
- `WEBHOOK_DELAY_SECONDS` - задержка webhook'ов (default: 2)

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

## 📊 Данные

### Генерируемые заказы:
- Реалистичные имена клиентов (не "John Doe")
- Разнообразные email'ы (не @example.com)
- Варьирующиеся суммы заказов (не $299.99)
- Настоящие адреса (не "123 Main St")
- Реальные товары (не "Premium Widget")

### Типы исключений (13% заказов):
- `DELIVERY_DELAY` (5%) - задержки доставки
- `ADDRESS_INVALID` (2%) - неверный адрес
- `PAYMENT_FAILED` (1.5%) - проблемы с оплатой
- `INVENTORY_SHORTAGE` (2.5%) - нехватка товара
- `DAMAGED_PACKAGE` (0.8%) - повреждение при доставке
- `CUSTOMER_UNAVAILABLE` (3%) - клиент недоступен

## 🧪 Тестирование

```bash
# Запустить тесты
python demo/test_demo.py

# Ожидаемый результат:
# ✅ Shopify Mock API is healthy
# ✅ Generated order #12345
# 🚨 Exception created: DELIVERY_DELAY
# ✅ Octup E²A API is healthy
```

## 🎭 Преимущества над старой системой

| Старая система | Новая система |
|----------------|---------------|
| ❌ Зависимость от CSV файлов | ✅ Faker генерация |
| ❌ Очевидные mock данные | ✅ Реалистичные данные |
| ❌ Статичные сценарии | ✅ Динамические webhook'и |
| ❌ Сложная настройка | ✅ Простой docker-compose |

## 🔍 Мониторинг

### Health checks:
- Shopify Mock: `http://localhost:8090/health`
- Octup E²A: `http://localhost:8000/healthz`

### Логи:
```bash
docker-compose logs -f shopify-mock
docker-compose logs -f api
```

Готово! Минимальная, но полнофункциональная демо-система.
