FROM python:3.11-slim

WORKDIR /app

# Build context is repo root. Requirements in paper_service/.
COPY backend/paper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy entire backend (includes database.py, paper_trading/, paper_service/)
COPY backend/ .

EXPOSE 10000

CMD ["uvicorn", "paper_service.main:app", "--host", "0.0.0.0", "--port", "10000"]
