@echo off
cd /d D:\N8N\BV_HansViet\Handviets
call .venv\Scripts\python.exe manage.py sync_rss_news --max-items 3 --publish --balanced >> logs\rss_sync.log 2>&1
