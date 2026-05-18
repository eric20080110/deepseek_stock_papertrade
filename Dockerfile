FROM python:3.11-slim

WORKDIR /app

COPY backend/paper_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

EXPOSE 10000

CMD ["uvicorn", "paper_service.main:app", "--host", "0.0.0.0", "--port", "10000"]
