#!/usr/bin/env python3
"""
Тест системы парсинга цен

Использование:
    python tests/test_parsers.py [URL]
    
Пример:
    python tests/test_parsers.py https://ggsel.net/catalog/product/test-123
"""

import sys
import time
from pathlib import Path

# Добавляем корень проекта в path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.rsc_parser import rsc_parser
from src.watchlist_parser import watchlist_parser
from src.distill_parser import DistillParser
from src.config import config


def test_rsc_parser(url: str):
    """Тест RSC парсера"""
    print("\n" + "="*60)
    print("ТЕСТ RSC PARSER")
    print("="*60)
    
    start = time.time()
    result = rsc_parser.parse_url(url, timeout=15)
    elapsed = time.time() - start
    
    print(f"URL: {url}")
    print(f"Время: {elapsed:.2f}s")
    print(f"Успех: {result.success}")
    print(f"Цена: {result.price}₽" if result.price else "Цена: не найдена")
    print(f"Метод: {result.method}")
    print(f"Ошибка: {result.error}" if result.error else "")
    
    stats = rsc_parser.get_stats()
    print(f"\nСтатистика: {stats}")
    
    return result.success


def test_watchlist_parser(url: str):
    """Тест Watchlist парсера"""
    print("\n" + "="*60)
    print("ТЕСТ WATCHLIST PARSER")
    print("="*60)
    
    start = time.time()
    result = watchlist_parser.parse_url(url, timeout=10)
    elapsed = time.time() - start
    
    print(f"URL: {url}")
    print(f"Время: {elapsed:.2f}s")
    print(f"Успех: {result.success}")
    print(f"Цена: {result.price}₽" if result.price else "Цена: не найдена")
    print(f"Ошибка: {result.error}" if result.error else "")
    
    return result.success


def test_distill_parser(url: str):
    """Тест Distill.io парсера"""
    print("\n" + "="*60)
    print("ТЕСТ DISTILL.IO PARSER")
    print("="*60)
    
    # Инициализация из конфига
    parser = DistillParser(
        api_key=config.DISTILL_API_KEY or None,
        monitor_ids=config.DISTILL_MONITOR_IDS.split(',') if config.DISTILL_MONITOR_IDS else [],
        local_data_dir=config.DISTILL_LOCAL_DATA_DIR or None,
        email_enabled=config.DISTILL_EMAIL_ENABLED,
    )
    
    if not parser.api_key and not parser.local_data_dir:
        print("⚠️ Distill.io не настроен (нет API key или local_data_dir)")
        print("Настройте в .env:")
        print("  DISTILL_API_KEY=...")
        print("  или")
        print("  DISTILL_LOCAL_DATA_DIR=...")
        return False
    
    start = time.time()
    result = parser.get_price(url, timeout=10)
    elapsed = time.time() - start
    
    print(f"URL: {url}")
    print(f"Время: {elapsed:.2f}s")
    print(f"Успех: {result.success}")
    print(f"Цена: {result.price}₽" if result.price else "Цена: не найдена")
    print(f"Метод: {result.method}")
    print(f"Обновлено: {result.last_updated}" if result.last_updated else "")
    print(f"Ошибка: {result.error}" if result.error else "")
    
    return result.success


def test_cascade_parser(url: str):
    """Тест каскадного парсинга (как в scheduler)"""
    print("\n" + "="*60)
    print("ТЕСТ КАСКАДНОГО ПАРСИНГА (RSC → Distill)")
    print("="*60)
    print(f"URL: {url}")
    print()
    
    # 1. RSC Parser
    print("1️⃣ RSC Parser...")
    rsc_result = rsc_parser.parse_url(url, timeout=15)
    
    if rsc_result.success:
        print(f"   ✅ Успех: {rsc_result.price}₽ (метод: {rsc_result.method})")
        print(f"\n🎉 ИТОГ: {rsc_result.price}₽ (RSC Parser)")
        return True
    
    print(f"   ❌ Неудача: {rsc_result.error}")
    
    # 2. Distill.io Parser
    print("\n2️⃣ Distill.io Parser...")
    
    parser = DistillParser(
        api_key=config.DISTILL_API_KEY or None,
        monitor_ids=config.DISTILL_MONITOR_IDS.split(',') if config.DISTILL_MONITOR_IDS else [],
        local_data_dir=config.DISTILL_LOCAL_DATA_DIR or None,
    )
    
    if not parser.api_key and not parser.local_data_dir:
        print("   ⚠️ Не настроен (пропускаем)")
    else:
        distill_result = parser.get_price(url, timeout=10)
        
        if distill_result.success:
            print(f"   ✅ Успех: {distill_result.price}₽ (метод: {distill_result.method})")
            print(f"\n🎉 ИТОГ: {distill_result.price}₽ (Distill.io)")
            return True
        
        print(f"   ❌ Неудача: {distill_result.error}")
    
    print("\n❌ ВСЕ МЕТОДЫ ИСЧЕРПАНЫ")
    return False


def main():
    if len(sys.argv) < 2:
        print("Использование: python tests/test_parsers.py [URL]")
        print("\nПримеры:")
        print("  python tests/test_parsers.py https://ggsel.net/catalog/product/test-123")
        sys.exit(1)
    
    url = sys.argv[1]
    
    print("\n" + "="*60)
    print("ТЕСТИРОВАНИЕ СИСТЕМЫ ПАРСИНГА ЦЕН")
    print("="*60)
    print(f"Тестируемый URL: {url}")
    
    # Тест каскадного парсинга (основной сценарий)
    success = test_cascade_parser(url)
    
    # Опционально: тест отдельных парсеров
    if len(sys.argv) > 2 and sys.argv[2] == '--all':
        test_rsc_parser(url)
        test_distill_parser(url)
    
    print("\n" + "="*60)
    print(f"РЕЗУЛЬТАТ: {'✅ УСПЕХ' if success else '❌ НЕУДАЧА'}")
    print("="*60 + "\n")
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
