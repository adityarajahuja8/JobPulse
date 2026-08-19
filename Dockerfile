FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .

COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "acdyon.server:app", "--host", "0.0.0.0", "--port", "8000"]
