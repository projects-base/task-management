FROM python:3.9-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY card_task_manager.py .

# Create data directory
RUN mkdir -p data

EXPOSE 8000

# Start the server
CMD ["python", "-u", "card_task_manager.py"]
