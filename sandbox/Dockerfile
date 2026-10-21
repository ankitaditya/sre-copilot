FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn[standard]>=0.30,<1"
COPY demo_api.py .
EXPOSE 8080
CMD ["uvicorn", "demo_api:app", "--host", "0.0.0.0", "--port", "8080"]

