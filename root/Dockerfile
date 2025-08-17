FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install poetry==1.8.0

# Configure Poetry to not create virtual environment (use system Python)
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=0 \
    POETRY_CACHE_DIR=/tmp/poetry_cache \
    POETRY_VIRTUALENVS_CREATE=false

# Copy Poetry files
COPY pyproject.toml poetry.lock ./

# Install dependencies directly to system Python
RUN poetry install --only=main && rm -rf $POETRY_CACHE_DIR

# Copy application code
COPY app/ ./app/
COPY flows/ ./flows/
COPY migrations/ ./migrations/
COPY alembic.ini .

# Create non-root user
RUN useradd --create-home --shell /bin/bash app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
