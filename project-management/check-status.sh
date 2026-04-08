#!/bin/bash
# Doornegar Daily Status Check
# Run: bash project-management/check-status.sh

echo "═══════════════════════════════════════"
echo "  دورنگر — گزارش وضعیت"
echo "  $(date '+%Y-%m-%d %H:%M')"
echo "═══════════════════════════════════════"
echo ""

cd "$(dirname "$0")/../backend" || exit 1

# Check Docker
echo "🔧 زیرساخت:"
docker compose ps --format "table {{.Name}}\t{{.Status}}" 2>/dev/null || echo "  Docker not running"
echo ""

# Check backend
echo "🌐 بک‌اند:"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "  ✓ API running on port 8000"
else
    echo "  ✗ API not running — start with: uvicorn app.main:app --reload --port 8000"
fi
echo ""

# Data metrics
echo "📊 داده‌ها:"
python3 -c "
import asyncio
from app.database import async_session
from sqlalchemy import select, func
from app.models.article import Article
from app.models.story import Story
from app.models.source import Source
from app.models.social import TelegramPost
async def s():
    async with async_session() as db:
        articles = (await db.execute(select(func.count(Article.id)))).scalar()
        stories = (await db.execute(select(func.count(Story.id)))).scalar()
        visible = (await db.execute(select(func.count(Story.id)).where(Story.article_count >= 5))).scalar()
        summaries = (await db.execute(select(func.count(Story.id)).where(Story.summary_fa.isnot(None)))).scalar()
        tg_posts = (await db.execute(select(func.count(TelegramPost.id)))).scalar()
        print(f'  مقالات: {articles}')
        print(f'  موضوعات: {stories} (نمایشی: {visible})')
        print(f'  خلاصه‌ها: {summaries}')
        print(f'  پست تلگرام: {tg_posts}')
asyncio.run(s())
" 2>&1 | grep -v "INFO\|WARNING\|hazm"
echo ""

# Reminders
echo "📋 یادآوری‌ها:"
echo "  • python manage.py pipeline    ← اجرای خط‌لوله کامل"
echo "  • python manage.py summarize   ← تولید خلاصه‌ها"
echo "  • python manage.py status      ← وضعیت کامل سیستم"
echo ""
echo "═══════════════════════════════════════"
