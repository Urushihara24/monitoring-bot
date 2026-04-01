#!/usr/bin/env python3
"""
Скрипт для обновления cookies конкурента через Selenium.

Использование:
    1. Первый запуск (с браузером для авторизации):
       python3 scripts/update_competitor_cookies.py --interactive

    2. Последующие запуски (автоматически):
       python3 scripts/update_competitor_cookies.py

Cookies сохраняются в data/cookies.json и могут быть использованы ботом.
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Пути
SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
COOKIES_FILE = PROJECT_DIR / 'data' / 'cookies_backup.json'

# URL конкурента для проверки
DEFAULT_COMPETITOR_URL = 'https://ggsel.net/catalog/product/fortnite-predmety-skiny-emocii-bez-vxoda-102124601'


def save_cookies(cookies: list, filepath: Path):
    """Сохраняет cookies в JSON файл с метаданными."""
    data = {
        'updated_at': datetime.now().isoformat(),
        'domain': 'ggsel.net',
        'cookies': cookies,
    }
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f'Cookies сохранены в {filepath}')


def load_cookies(filepath: Path) -> list:
    """Загружает cookies из JSON файла."""
    if not filepath.exists():
        return []
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    logger.info(f'Cookies загружены из {filepath}')
    return data.get('cookies', [])


def cookies_to_header_string(cookies: list) -> str:
    """Преобразует список cookies в строку для HTTP заголовка."""
    parts = []
    for cookie in cookies:
        name = cookie.get('name', '')
        value = cookie.get('value', '')
        if name and value:
            parts.append(f'{name}={value}')
    return '; '.join(parts)


def fetch_cookies_interactive(competitor_url: str) -> list:
    """
    Интерактивный режим: открывает браузер, пользователь входит в аккаунт.
    После входа cookies сохраняются.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    logger.info('=== Интерактивный режим ===')
    logger.info('1. Откроется браузер Chrome')
    logger.info('2. Пройдите капчу/авторизацию если нужно')
    logger.info('3. Закройте браузер когда страница загрузится')
    logger.info('')

    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    # НЕ используем headless для интерактивного режима

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(competitor_url)

        # Ждём пока пользователь закроет браузер или загрузится страница
        logger.info('Ожидание загрузки страницы (до 60 сек)...')
        try:
            WebDriverWait(driver, 60).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except Exception:
            pass

        # Даём время пользователю пройти капчу
        logger.info('Страница загружена. У вас есть 30 секунд для прохождения капчи...')
        time.sleep(30)

        # Получаем cookies
        cookies = driver.get_cookies()
        logger.info(f'Получено {len(cookies)} cookies')

        return cookies

    except Exception as e:
        logger.error(f'Ошибка: {e}')
        return []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def fetch_cookies_headless(competitor_url: str, existing_cookies: list = None) -> list:
    """
    Headless режим: использует существующие cookies для обновления.
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    options = Options()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)

    driver = None
    try:
        driver = webdriver.Chrome(options=options)

        # Устанавливаем существующие cookies
        if existing_cookies:
            driver.get('https://ggsel.net')
            time.sleep(2)
            for cookie in existing_cookies:
                try:
                    driver.add_cookie(cookie)
                except Exception:
                    pass

        # Переходим на целевую страницу
        driver.get(competitor_url)
        time.sleep(5)

        # Проверяем, удалось ли загрузить страницу
        if '401' in driver.title or '403' in driver.title:
            logger.warning('Страница заблокирована (401/403)')
            return existing_cookies or []

        # Получаем обновлённые cookies
        cookies = driver.get_cookies()
        logger.info(f'Обновлено {len(cookies)} cookies')

        return cookies

    except Exception as e:
        logger.error(f'Headless ошибка: {e}')
        return existing_cookies or []
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def verify_cookies(cookies: list, competitor_url: str) -> bool:
    """Проверяет, работают ли cookies."""
    import requests

    session = requests.Session()
    for cookie in cookies:
        session.cookies.set(
            name=cookie.get('name', ''),
            value=cookie.get('value', ''),
            domain=cookie.get('domain', 'ggsel.net'),
            path=cookie.get('path', '/'),
        )

    try:
        resp = session.get(competitor_url, timeout=15)
        if resp.status_code == 200:
            logger.info('✅ Cookies работают (200 OK)')
            return True
        else:
            logger.warning(f'❌ Cookies не работают ({resp.status_code})')
            return False
    except Exception as e:
        logger.error(f'Ошибка проверки: {e}')
        return False


def main():
    parser = argparse.ArgumentParser(description='Обновление cookies конкурента')
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Интерактивный режим (открыть браузер для авторизации)'
    )
    parser.add_argument(
        '--url', '-u',
        default=DEFAULT_COMPETITOR_URL,
        help='URL конкурента для проверки'
    )
    parser.add_argument(
        '--output', '-o',
        default=str(COOKIES_FILE),
        help='Путь для сохранения cookies'
    )
    args = parser.parse_args()

    competitor_url = args.url
    output_file = Path(args.output)

    logger.info(f'URL: {competitor_url}')
    logger.info(f'Output: {output_file}')

    # Загружаем существующие cookies
    existing_cookies = load_cookies(output_file)

    if args.interactive or not existing_cookies:
        # Интерактивный режим для первичной авторизации
        logger.info('Запуск интерактивного режима...')
        cookies = fetch_cookies_interactive(competitor_url)
    else:
        # Headless режим для обновления
        logger.info('Запуск headless режима...')
        cookies = fetch_cookies_headless(competitor_url, existing_cookies)

    if not cookies:
        logger.error('Не удалось получить cookies')
        return 1

    # Проверяем cookies
    if not verify_cookies(cookies, competitor_url):
        logger.warning('Cookies могут быть невалидны')

    # Сохраняем
    save_cookies(cookies, output_file)

    # Выводим строку для .env
    cookie_string = cookies_to_header_string(cookies)
    logger.info('')
    logger.info('=== Добавьте в .env ===')
    logger.info(f'COMPETITOR_COOKIES={cookie_string}')
    logger.info('')

    return 0


if __name__ == '__main__':
    sys.exit(main())
