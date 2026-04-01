#!/bin/bash
echo "🚀 ПОЛНЫЙ ДЕПЛОЙ НА СЕРВЕР"
echo "=========================="
echo ""
echo "📤 Отправка файлов..."

# Копируем всё кроме .git, .venv, __pycache__, logs, data
rsync -avz --exclude='.git' \
      --exclude='.venv' \
      --exclude='__pycache__' \
      --exclude='*.pyc' \
      --exclude='logs' \
      --exclude='data/*.json' \
      --exclude='.DS_Store' \
      src/ scripts/ tests/ \
      *.py *.txt *.ini *.yml *.md Dockerfile Makefile .env.example \
      root@5.230.125.77:/root/monitoring-bot/

echo ""
echo "✅ Файлы отправлены!"
echo ""
echo "📋 НА СЕРВЕРЕ ВЫПОЛНИТЕ:"
echo "  ssh root@5.230.125.77"
echo "  cd /root/monitoring-bot"
echo "  docker-compose down"
echo "  docker-compose up -d --build"
echo "  docker-compose logs -f"
