.PHONY: up down fmt test migrate seed deploy-flow clean logs help
.PHONY: up-local up-cloud setup-local setup-cloud
.PHONY: simulate simulate-fast simulate-replay simulate-logs simulate-stop simulate-metrics

# Environment Configuration
ENV ?= local
COMPOSE_FILE = docker/docker-compose.yml

# Default target
help:		## Show this help
	@echo "Octup E²A - SLA Radar + Invoice Guard"
	@echo ""
	@echo "Environment Setup:"
	@echo "  setup-local     - Setup for local development (Supabase local + Prefect local)"
	@echo "  setup-cloud     - Setup for cloud deployment"
	@echo ""
	@echo "Development:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

## Environment Setup
setup-local:	## Setup local development environment
	@echo "Setting up local development environment..."
	@cp .env.local .env
	@echo "✅ Copied .env.local to .env"
	@echo "📋 Next steps:"
	@echo "   1. Start Supabase: supabase start"
	@echo "   2. Run migrations: make migrate"
	@echo "   3. Start services: make up-local"

setup-cloud:	## Setup cloud deployment environment
	@echo "Setting up cloud deployment environment..."
	@cp .env.cloud .env
	@echo "✅ Copied .env.cloud to .env"
	@echo "⚠️  Please update .env with your actual cloud credentials"
	@echo "📋 Required: DATABASE_URL, REDIS_URL, AI_API_KEY, NEW_RELIC_LICENSE_KEY"

## Development Commands
up:		## Start the stack (API only)
	docker compose -f $(COMPOSE_FILE) up --build -d api

up-local:	## Start with local Redis (for local development)
	docker compose -f $(COMPOSE_FILE) --profile local-redis up --build -d

up-cloud:	## Start for cloud deployment (API only, uses cloud services)
	docker compose -f $(COMPOSE_FILE) up --build -d api

up-full:	## Start with all optional services
	docker compose -f $(COMPOSE_FILE) --profile local-redis --profile observability --profile prefect up --build -d

up-demo:	## Start demo services (API + Shopify Mock)
	docker compose -f $(COMPOSE_FILE) --profile demo up --build -d

web-dev:	## Start the web dashboard in development mode
	@echo "Starting Octup E²A Dashboard..."
	cd dashboard && npm run dev

web-install:	## Install dashboard dependencies
	@echo "Installing dashboard dependencies..."
	cd dashboard && npm install

web-build:	## Build dashboard for production
	@echo "Building dashboard..."
	cd dashboard && npm run build

web-start:	## Start dashboard in production mode
	@echo "Starting dashboard in production..."
	cd dashboard && npm start

dev-full:	## Start both API and web dashboard
	make up-local &
	make web-dev

down:		## Stop the stack
	docker compose -f $(COMPOSE_FILE) down

clean:		## Stop and remove all containers and volumes
	docker compose -f $(COMPOSE_FILE) --profile "*" down -v
	docker system prune -f

logs:		## Show logs (usage: make logs SERVICE=api)
	docker compose -f $(COMPOSE_FILE) logs -f $(SERVICE)

status:		## Show container status
	docker compose -f $(COMPOSE_FILE) ps

## Database & Migrations
migrate:	## Run Alembic migrations
	alembic upgrade head

seed:		## Seed demo data
	python -m app.storage.seed

## Testing & Quality
fmt:		## Format code
	ruff check . --fix
	ruff format .

test:		## Run tests
	pytest -v

test-coverage:	## Run tests with coverage
	pytest --cov=app --cov-report=html --cov-report=term

## Shopify Mock (Demo)
demo-start:	## Start Shopify mock API for demo
	docker compose -f $(COMPOSE_FILE) --profile demo up -d shopify-mock

demo-stop:	## Stop Shopify mock API
	docker compose -f $(COMPOSE_FILE) stop shopify-mock

demo-logs:	## Show Shopify mock logs
	docker compose -f $(COMPOSE_FILE) logs -f shopify-mock

demo-generate:	## Generate batch of demo orders (1001-1999 orders)
	@echo "🎲 Generating demo orders batch..."
	@curl -X POST http://localhost:8090/demo/generate-batch | jq .

demo-clear:	## Clear all demo orders
	@echo "🗑️  Clearing demo orders..."
	@curl -X POST http://localhost:8090/demo/clear-orders | jq .

demo-stats:	## Show demo statistics
	@echo "📊 Demo statistics:"
	@curl -s http://localhost:8090/demo/stats | jq .

demo-health:	## Check Shopify mock health
	@echo "🔍 Shopify mock health:"
	@curl -s http://localhost:8090/health | jq .

## Development Workflows
dev-demo:	## Start demo environment (API + Shopify Mock + Dashboard)
	@echo "🚀 Starting demo environment..."
	make up-demo
	@echo "✅ Demo services started!"
	@echo "📋 Available endpoints:"
	@echo "   API: http://localhost:8000"
	@echo "   Shopify Mock: http://localhost:8090"
	@echo "   Dashboard: http://localhost:3000 (run 'make web-dev' in another terminal)"
	@echo ""
	@echo "🎯 Next step: make web-dev"
prefect-server:	## Start local Prefect server
	docker compose -f $(COMPOSE_FILE) --profile prefect up -d prefect-server

prefect-worker:	## Start Prefect worker (requires server to be running)
	docker compose -f $(COMPOSE_FILE) --profile prefect up -d prefect-worker

prefect-up:	## Start both Prefect server and worker
	docker compose -f $(COMPOSE_FILE) --profile prefect up -d

prefect-down:	## Stop Prefect services
	docker compose -f $(COMPOSE_FILE) stop prefect-server prefect-worker

prefect-logs:	## Show Prefect logs (usage: make prefect-logs SERVICE=prefect-server)
	docker compose -f $(COMPOSE_FILE) logs -f $(or $(SERVICE),prefect-server)

prefect-ui:	## Open Prefect UI in browser
	@echo "🎯 Prefect UI: http://localhost:4200"
	@open http://localhost:4200 2>/dev/null || echo "Open http://localhost:4200 in your browser"

prefect-deploy:	## Deploy flows to local Prefect server
	python deploy_flows.py

prefect-deploy-check:	## Check Prefect server connection
	python deploy_flows.py --check

## Prefect Flows (Updated for local server)
flow-demo:	## Run periodic demo flow once (for testing)
	PYTHONPATH=/Users/sasha/IdeaProjects/octup/root python flows/periodic_demo.py --run

flow-demo-serve:	## Start periodic demo flow with 5-minute schedule
	PYTHONPATH=/Users/sasha/IdeaProjects/octup/root python flows/periodic_demo.py --serve

flow-invoice:	## Run invoice validation flow locally (with event streaming)
	PYTHONPATH=/Users/sasha/IdeaProjects/octup/root python flows/invoice_validate_nightly.py --run

flow-invoice-fast:	## Run invoice validation with fast streaming (1 min, 10 EPS)
	PYTHONPATH=/Users/sasha/IdeaProjects/octup/root python flows/invoice_validate_nightly.py --run --duration 1 --eps 10

flow-invoice-no-stream:	## Run invoice validation without event streaming
	PYTHONPATH=/Users/sasha/IdeaProjects/octup/root python flows/invoice_validate_nightly.py --run --no-streaming

flow-streaming:	## Run event streaming flow only (3 min, 5 EPS)
	PYTHONPATH=/Users/sasha/IdeaProjects/octup/root python flows/event_streaming.py --run

flow-test:	## Test complete flow integration
	python test_flow_integration.py

## Supabase Management (Local)
supabase-start:	## Start local Supabase
	supabase start

supabase-stop:	## Stop local Supabase
	supabase stop

supabase-status:	## Show Supabase status
	supabase status

supabase-reset:	## Reset local Supabase database
	supabase db reset

## Health Checks
health:		## Check system health
	@echo "🔍 Checking system health..."
	@curl -s http://localhost:8000/healthz | jq . || echo "❌ API not responding"
	@echo ""
	@echo "📊 Available endpoints:"
	@echo "   API: http://localhost:8000/metrics"
	@echo "   Shopify Mock: http://localhost:8090/health"
	@echo "   Dashboard: http://localhost:3000"

## Development Workflows
dev-local:	## Complete local development setup
	@echo "🚀 Setting up complete local development environment..."
	make setup-local
	make supabase-start
	sleep 5
	make migrate
	make seed
	make up-local
	make prefect-server
	@echo "✅ Local development environment ready!"
	@echo "📋 Available endpoints:"
	@echo "   API: http://localhost:8000"
	@echo "   Dashboard: http://localhost:3000 (run 'make web-dev' in another terminal)"
	@echo "   Supabase Studio: http://localhost:54323"
	@echo "   Prefect UI: http://localhost:4200"
	@echo "   API Docs: http://localhost:8000/docs"
	@echo ""
	@echo "🎯 Next steps:"
	@echo "   1. Deploy flows: make prefect-deploy"
	@echo "   2. Start worker: make prefect-worker"
	@echo "   3. Start dashboard: make web-dev"

dev-cloud:	## Setup for cloud development
	@echo "☁️  Setting up cloud development environment..."
	make setup-cloud
	@echo "⚠️  Please update .env with your cloud credentials, then run:"
	@echo "   make migrate && make seed && make up-cloud"

## Production Deployment
deploy-staging:	## Deploy to staging environment
	@echo "🚀 Deploying to staging..."
	make setup-cloud
	make migrate
	make up-cloud

deploy-prod:	## Deploy to production environment
	@echo "🚀 Deploying to production..."
	@echo "⚠️  This should be run in your CI/CD pipeline"
	make setup-cloud
	make migrate
	make up-cloud
