FROM python:3.11-slim

# Install ffprobe for video duration detection
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy posting service
COPY posting_service/ ./posting_service/
COPY .env ./

# Install dependencies
RUN pip install --no-cache-dir -r posting_service/requirements.txt

# Create dirs
RUN mkdir -p posting_service/logs input processed

# Run the scheduler
CMD ["python", "-m", "posting_service"]
