#!/usr/bin/env python3
"""
Health check скрипт для Docker контейнера

Проверяет:
1. Последний цикл планировщика (не старше 5 минут)
2. Доступность GGSEL API
3. Наличие cookies

Использование:
    python healthcheck.py

Возвращает:
    0 - HEALTHY
    1 - UNHEALTHY
"""

import sys
import os
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем корень проекта
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from storage import storage
from config import config


def check_last_cycle() -> bool:
    """Проверка последнего цикла планировщика"""
    state = storage.get_state()
    last_cycle = state.get('last_cycle')
    
    if not last_cycle:
        print("⚠️ Last cycle: не найден (бот ещё не запускался)")
        return True  # Не считаем ошибкой на старте
    
    # Конвертируем строку в datetime
    try:
        if isinstance(last_cycle, str):
            last_cycle = datetime.fromisoformat(last_cycle)
    except (ValueError, TypeError):
        print(f"❌ Last cycle: некорректный формат ({last_cycle})")
        return False
    
    # Проверяем возраст
    age = (datetime.now() - last_cycle).total_seconds()
    
    if age > 300:  # 5 минут
        print(f"⚠️ Last cycle: {age:.0f}s назад (старше 5 минут)")
        return True  # Предупреждение, но не критично
    
    print(f"✅ Last cycle: {age:.0f}s назад")
    return True


def check_api() -> bool:
    """Проверка доступности GGSEL API"""
    if not config.GGSEL_API_KEY and not config.GGSEL_ACCESS_TOKEN:
        print("⚠️ API: GGSEL_API_KEY и GGSEL_ACCESS_TOKEN не указаны")
        return True  # Не считаем ошибкой
    
    try:
        from api_client import GGSELClient
        
        api_client = GGSELClient(
            api_key=config.GGSEL_API_KEY or '',
            seller_id=config.GGSEL_SELLER_ID,
            base_url=config.GGSEL_BASE_URL,
            lang=config.GGSEL_LANG,
            access_token=config.GGSEL_ACCESS_TOKEN or '',
        )
        
        # Быстрая проверка (без таймаута)
        product_id = config.GGSEL_PRODUCT_ID
        if product_id and product_id > 0:
            product = api_client.get_product(product_id)
            if product:
                print(f"✅ API: товар {product_id} доступен (цена: {product.price})")
                return True
            else:
                print(f"⚠️ API: товар {product_id} не найден")
                return True  # Не считаем критичной ошибкой
        
        # Если product_id не указан, просто проверяем соединение
        if api_client.check_api_access():
            print("✅ API: соединение установлено")
            return True
        else:
            print("❌ API: соединение не установлено")
            return False
            
    except Exception as e:
        print(f"❌ API: ошибка ({e})")
        return False


def check_cookies() -> bool:
    """Проверка наличия cookies"""
    cookies_backup_path = Path('data/cookies_backup.json')
    
    if not cookies_backup_path.exists():
        print("⚠️ Cookies: файл не найден (не критично)")
        return True
    
    if config.COMPETITOR_COOKIES:
        print("✅ Cookies: указаны в COMPETITOR_COOKIES")
        return True
    
    # Проверяем возраст cookies
    try:
        file_mtime = datetime.fromtimestamp(cookies_backup_path.stat().st_mtime)
        age_seconds = (datetime.now() - file_mtime).total_seconds()
        
        if age_seconds > config.COOKIES_EXPIRE_SECONDS:
            print(f"⚠️ Cookies: протухли ({age_seconds/3600:.1f}ч назад)")
            return True  # Не считаем критичной ошибкой
        
        print(f"✅ Cookies: актуальны ({age_seconds/3600:.1f}ч назад)")
        return True
        
    except Exception as e:
        print(f"⚠️ Cookies: ошибка проверки ({e})")
        return True


def check_disk_space() -> bool:
    """Проверка свободного места на диске"""
    try:
        import shutil
        total, used, free = shutil.disk_usage('/')
        
        free_gb = free / (1024 ** 3)
        free_percent = (free / total) * 100
        
        if free_percent < 5:
            print(f"❌ Disk: критически мало места ({free_gb:.2f}GB, {free_percent:.1f}%)")
            return False
        
        if free_percent < 10:
            print(f"⚠️ Disk: мало места ({free_gb:.2f}GB, {free_percent:.1f}%)")
            return True
        
        print(f"✅ Disk: {free_gb:.2f}GB свободно ({free_percent:.1f}%)")
        return True
        
    except Exception as e:
        print(f"⚠️ Disk: ошибка проверки ({e})")
        return True


def main():
    """Основная функция"""
    print(f"\n🏥 Health Check ({datetime.now().isoformat()})")
    print("=" * 50)
    
    checks = [
        ("Last Cycle", check_last_cycle),
        ("API", check_api),
        ("Cookies", check_cookies),
        ("Disk Space", check_disk_space),
    ]
    
    results = []
    
    for name, check_func in checks:
        print(f"\n📋 Проверка: {name}")
        print("-" * 30)
        result = check_func()
        results.append(result)
    
    print("\n" + "=" * 50)
    
    # Итог
    healthy_count = sum(results)
    total_count = len(results)
    
    if all(results):
        print(f"✅ HEALTHY ({healthy_count}/{total_count} проверок)")
        sys.exit(0)
    else:
        print(f"❌ UNHEALTHY ({healthy_count}/{total_count} проверок)")
        sys.exit(1)


if __name__ == '__main__':
    main()
