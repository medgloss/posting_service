# Posting Service — Social Media Auto-Poster

A standalone service that automatically posts reels to **Instagram** (Reels + Stories) and **Facebook** (Reels + Feed) twice daily.

## Features

- **2 posts/day** at 6 PM IST and 8 PM IST
- **Instagram**: Reels (title + description + hashtags) and Stories (title only)
- **Facebook**: Reels and Feed posts (title + description + hashtags)
- **Auto-sync** input folder for new content
- **Rotating logs** in `posting_service/logs/`
- **SQLite** for state tracking

## Quick Start

### 1. Install dependencies

```bash
pip install -r posting_service/requirements.txt
```

### 2. Configure

Copy `.env.example` to `.env` in the project root and fill in your credentials:

```bash
cp posting_service/.env.example .env
```

### 3. Test

```bash
# Sync input folder without posting
python -m posting_service --test

# Post immediately (one post)
python -m posting_service --run-now
```

### 4. Run as service

```bash
# Runs continuously, posts at 6 PM and 8 PM IST
python -m posting_service
```

## AWS Deployment

### Docker

```bash
docker build -f posting_service/Dockerfile -t posting-service .
docker run -d \
  --name posting-service \
  -v $(pwd)/input:/app/input \
  -v $(pwd)/processed:/app/processed \
  --restart unless-stopped \
  posting-service
```

### systemd (EC2)

Create `/etc/systemd/system/posting-service.service`:

```ini
[Unit]
Description=Social Media Posting Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/posting-pipeline
ExecStart=/home/ubuntu/posting-pipeline/venv/bin/python -m posting_service
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable posting-service
sudo systemctl start posting-service
```

## Input Folder Structure

Each content folder in `input/` should contain:

```
input/
└── 2025-10-15_05-42-13_UTC_DP0YsYcgZlz_VERTICAL.../
    ├── final_video.mp4              # Video file
    ├── social_media_content.json    # Preferred: structured content
    └── social_media_content.txt     # Fallback: text content
```

## Logs

Logs are stored in `posting_service/logs/`:
- `posting_service.log` — current log
- `posting_service.log.1` through `.10` — rotated backups (5 MB each)
