FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
# Install CPU-only PyTorch first to save ~2GB of space
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

# Use gthread since eventlet was removed
CMD ["gunicorn", "--worker-class", "gthread", "--threads", "20", "-w", "1", "--bind", "0.0.0.0:5000", "app:app"]

