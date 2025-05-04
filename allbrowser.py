from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import (TimeoutException, 
                                      NoSuchElementException, 
                                      WebDriverException,
                                      InvalidSessionIdException,
                                      StaleElementReferenceException)
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.microsoft import EdgeChromiumDriverManager
import random
import datetime
import time
import json
import os
import re
import requests
import getpass
import socket
import uuid
import sys
import msvcrt
import threading

class UserIdentity:
    """Класс для идентификации пользователя и устройства"""
    def __init__(self):
        self.user_id = self._get_user_id()
        self.device_id = self._get_device_id()
        self.username = getpass.getuser()
        self.hostname = socket.gethostname()
        
    def _get_user_id(self):
        """Генерирует уникальный ID пользователя"""
        try:
            if os.path.exists('user_config.json'):
                with open('user_config.json', 'r') as f:
                    config = json.load(f)
                    return config.get('user_id', str(uuid.uuid4()))
        except Exception:
            pass
        return str(uuid.uuid4())
    
    def _get_device_id(self):
        """Генерирует уникальный ID устройства"""
        try:
            mac = uuid.getnode()
            return str(mac)
        except Exception:
            return str(uuid.uuid4())
    
    def save_user_id(self):
        """Сохраняет user_id в файл конфигурации"""
        try:
            with open('user_config.json', 'w') as f:
                json.dump({'user_id': self.user_id}, f)
        except Exception:
            pass

class TelegramNotifier:
    def __init__(self, token, chat_id, user_identity):
        self.token = token
        self.chat_id = chat_id
        self.user_identity = user_identity
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.session = requests.Session()
        
    def _make_request(self, method, params=None, files=None, timeout=30, max_retries=3):
        for attempt in range(max_retries):
            try:
                url = f"{self.base_url}/{method}"
                if files:
                    response = self.session.post(url, files=files, data=params, timeout=timeout)
                else:
                    response = self.session.post(url, json=params, timeout=timeout)
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    print(f"Telegram API final error after {max_retries} attempts: {str(e)}")
                    return None
                sleep(2 ** (attempt + 1))
                
    def send_message(self, text, disable_notification=False):
        user_info = (
            f"\n👤 User: {self.user_identity.username}@{self.user_identity.hostname}\n"
            f"🆔 ID: {self.user_identity.user_id[:8]}"
        )
        full_text = f"{text}{user_info}"
        
        params = {
            'chat_id': self.chat_id,
            'text': full_text,
            'parse_mode': 'HTML',
            'disable_notification': disable_notification,
            'disable_web_page_preview': True
        }
        return self._make_request('sendMessage', params)

class MangaReader:
    def __init__(self):
        # Идентификация пользователя
        self.user_identity = UserIdentity()
        self.user_identity.save_user_id()
        
        # Инициализация TelegramNotifier перед driver
        self.telegram = None
        try:
            if os.path.exists('config.json'):
                with open('config.json') as f:
                    config = json.load(f)
                self.telegram = TelegramNotifier(
                    config['telegram']['token'], 
                    config['telegram']['chat_id'], 
                    user_identity=self.user_identity
                )
                self.telegram.send_message("🤖 MangaBot запущен и готов к работе!")
        except Exception as e:
            print(f"Ошибка инициализации Telegram: {str(e)}")
        
        # Настройка браузера
        self.driver = None
        self.initialize_driver()
        
        # Состояние
        self.state_file = f"manga_state_{self.user_identity.user_id[:8]}.json"
        self.current_page = 1
        self.current_manga = None
        self.current_volume = 1
        self.current_chapter = 1
        self.processed_chapters = set()
        self.login_attempts = 0
        self.max_login_attempts = 3
        self.last_error = None
        self.is_logged_in = False
        self.email = None
        self.password = None
        self.MAX_CATALOG_PAGES = 100
        self.reading_speed = 60
        self.user_interrupt = False
        self.switch_manga_flag = False

    def initialize_driver(self, browser_name="firefox"):
        """Инициализирует драйвер браузера с обработкой ошибок"""
        try:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
            
            browser_name = browser_name.lower().strip()
            
            if browser_name == "firefox":
                firefox_options = FirefoxOptions()
                firefox_options.add_argument("--headless")
                firefox_options.add_argument("--disable-gpu")
                firefox_options.add_argument("--no-sandbox")
                firefox_options.add_argument("--disable-dev-shm-usage")
                service = webdriver.FirefoxService(GeckoDriverManager().install())
                self.driver = webdriver.Firefox(service=service, options=firefox_options)
                
            elif browser_name == "chrome":
                chrome_options = ChromeOptions()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--disable-gpu")
                chrome_options.add_argument("--no-sandbox")
                chrome_options.add_argument("--disable-dev-shm-usage")
                service = webdriver.ChromeService(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                
            elif browser_name == "opera":
                opera_options = OperaOptions()
                opera_options.add_argument("--headless")
                opera_options.add_argument("--disable-gpu")
                opera_options.add_argument("--no-sandbox")
                opera_options.add_argument("--disable-dev-shm-usage")
                service = webdriver.ChromeService(OperaDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=opera_options)
                
            elif browser_name == "yandex":
                yandex_options = ChromeOptions()
                yandex_options.add_argument("--headless")
                yandex_options.add_argument("--disable-gpu")
                yandex_options.add_argument("--no-sandbox")
                yandex_options.add_argument("--disable-dev-shm-usage")
                if os.name == 'nt':
                    yandex_path = os.getenv('LOCALAPPDATA') + r'\Yandex\YandexBrowser\Application\browser.exe'
                else:
                    yandex_path = '/usr/bin/yandex-browser'
                yandex_options.binary_location = yandex_path
                service = webdriver.ChromeService(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=yandex_options)
                
            elif browser_name == "edge":
                edge_options = ChromeOptions()
                edge_options.add_argument("--headless")
                edge_options.add_argument("--disable-gpu")
                edge_options.add_argument("--no-sandbox")
                edge_options.add_argument("--disable-dev-shm-usage")
                service = webdriver.EdgeService(EdgeChromiumDriverManager().install())
                self.driver = webdriver.Edge(service=service, options=edge_options)
                
            else:
                raise ValueError(f"Unsupported browser: {browser_name}")
            
            self.driver.set_page_load_timeout(90)
            self.wait = WebDriverWait(self.driver, 45)
            return True
            
        except Exception as e:
            error_msg = f"Критическая ошибка при инициализации драйвера: {str(e)}"
            print(error_msg)
            if hasattr(self, 'telegram') and self.telegram:
                self.telegram.send_message(error_msg)
            return False

    def get_credentials(self):
        """Запрашивает учетные данные у пользователя"""
        print("=== ВВОД ДАННЫХ ===")
        email = input("Email: ").strip()
        
        # Улучшенный ввод пароля для разных платформ
        print("Password: ", end='', flush=True)
        password = ''
        
        if sys.platform == 'win32':
            # Для Windows
            while True:
                ch = msvcrt.getch()
                if ch in (b'\r', b'\n'):
                    print()
                    break
                elif ch == b'\x08':
                    if len(password) > 0:
                        password = password[:-1]
                        print('\b \b', end='', flush=True)
                else:
                    password += ch.decode('utf-8')
                    print('*', end='', flush=True)
        else:
            # Для Linux/MacOS
            import termios
            import tty
            fd = sys.stdin.fileno()
            old_settings = termios.tcgetattr(fd)
            try:
                tty.setraw(sys.stdin.fileno())
                while True:
                    ch = sys.stdin.read(1)
                    if ch in ('\r', '\n'):
                        print()
                        break
                    elif ch == '\x7f':  # Backspace
                        if len(password) > 0:
                            password = password[:-1]
                            print('\b \b', end='', flush=True)
                    else:
                        password += ch
                        print('*', end='', flush=True)
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        
        return email, password

    def load_state(self):
        """Загружает сохраненное состояние из файла"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding='utf-8') as f:
                    state = json.load(f)
                    self.current_page = state.get("current_page", 1)
                    self.current_manga = state.get("current_manga")
                    self.current_volume = state.get("current_volume", 1)
                    self.current_chapter = state.get("current_chapter", 1)
                    self.processed_chapters = set(state.get("processed_chapters", []))
                    return True
            except Exception as e:
                self.log_message(f"Ошибка загрузки состояния: {e}", is_error=True)
        return False

    def save_state(self):
        """Сохраняет текущее состояние в файл"""
        state = {
            "current_page": self.current_page,
            "current_manga": self.current_manga,
            "current_volume": self.current_volume,
            "current_chapter": self.current_chapter,
            "processed_chapters": list(self.processed_chapters)
        }
        try:
            with open(self.state_file, "w", encoding='utf-8') as f:
                json.dump(state, f, indent=2)
            return True
        except Exception as e:
            self.log_message(f"Ошибка сохранения состояния: {e}", is_error=True)
            return False

    def log_message(self, message, is_error=False):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_prefix = f"[USER:{self.user_identity.user_id[:8]}]"
        log_entry = f"{user_prefix}[{timestamp}] {message}\n"
        
        with open("manga_bot_log.txt", "a", encoding='utf-8') as log_file:
            log_file.write(log_entry)
        
        print(f"{user_prefix} {message}")
        
        if is_error:
            self.last_error = message[:500]
            if hasattr(self, 'telegram') and self.telegram:
                try:
                    error_message = (
                        f"🚨 <b>MangaBot Error</b>\n"
                        f"<pre>{message[:4000]}</pre>\n"
                        f"📚 Манга: {self.current_manga or 'Нет'}\n"
                        f"📖 Том/Глава: {self.current_volume}/{self.current_chapter}"
                    )
                    self.telegram.send_message(
                        error_message,
                        disable_notification=not is_error
                    )
                except Exception as e:
                    print(f"Не удалось отправить ошибку в Telegram: {str(e)}")

    def safe_get(self, url, retries=3):
        """Безопасная загрузка страницы с повторами"""
        for attempt in range(retries):
            try:
                try:
                    _ = self.driver.current_url
                except (WebDriverException, InvalidSessionIdException):
                    self.log_message("Соединение с браузером потеряно, перезапускаем...", is_error=True)
                    if not self.initialize_driver():
                        raise
                
                self.driver.set_page_load_timeout(90)
                self.driver.get(url)
                self.wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                return True
            except (TimeoutException, WebDriverException, InvalidSessionIdException) as e:
                error_msg = f"Ошибка загрузки ({attempt+1}/{retries}): {str(e)[:100]}"
                self.log_message(error_msg, is_error=True)
                
                if attempt == retries - 1:
                    self.save_debug_info("page_load_failed")
                    raise
                
                if "Tried to run command without establishing a connection" in str(e):
                    if not self.initialize_driver():
                        raise
                
                sleep(5 * (attempt + 1))
        return False

    def check_login_state(self):
        """Проверяет состояние входа"""
        checks = [
            ("Аватар пользователя", ".user-avatar"),
            ("Меню пользователя", ".user-menu"),
            ("Кнопка выхода", "//*[contains(text(), 'Выйти')]"),
            ("URL профиля", lambda: "login" not in self.driver.current_url)
        ]
        
        for check_name, locator in checks:
            try:
                if callable(locator):
                    result = locator()
                else:
                    result = self.driver.find_elements(By.CSS_SELECTOR, locator) if '.' in locator else \
                            self.driver.find_elements(By.XPATH, locator)
                    result = bool(result)
                
                if result:
                    return True
            except Exception as e:
                self.log_message(f"Ошибка проверки '{check_name}': {str(e)[:100]}")
        
        return False

    def manual_login_assist(self):
        """Помощник ручного входа"""
        self.log_message("=== РЕЖИМ РУЧНОГО ВХОДА ===")
        if hasattr(self, 'telegram') and self.telegram:
            self.telegram.send_message(
                "🔐 Требуется ручной вход в MangaBuff!\n"
                "1. Откройте браузер на вашем компьютере\n"
                "2. Войдите в аккаунт\n"
                "3. Вернитесь сюда и нажмите Enter"
            )
        
        try:
            self.driver.quit()
        except Exception:
            pass
        
        firefox_options = FirefoxOptions()
        service = webdriver.FirefoxService(GeckoDriverManager().install())
        self.driver = webdriver.Firefox(service=service, options=firefox_options)
        
        try:
            self.driver.get("https://mangabuff.ru/login")
            input("После успешного входа нажмите Enter здесь...")
            
            if self.check_login_state():
                self.log_message("Ручной вход подтвержден!")
                if hasattr(self, 'telegram') and self.telegram:
                    self.telegram.send_message("✅ Ручной вход успешно выполнен!")
                self.driver.quit()
                self.initialize_driver()
                return True
                
            self.log_message("Не удалось подтвердить вход", is_error=True)
            return False
            
        except Exception as e:
            self.log_message(f"Ошибка в режиме ручного входа: {str(e)}", is_error=True)
            return False

    def get_reading_speed(self):
        """Запрашивает скорость чтения"""
        while True:
            try:
                speed = int(input("Введите скорость чтения (1-666 глав в час): ").strip())
                if 1 <= speed <= 666:
                    if hasattr(self, 'telegram') and self.telegram:
                        self.telegram.send_message(f"⚡ Установлена скорость чтения: {speed} глав/час")
                    return speed
                print(f"Ошибка: скорость должна быть от 1 до 666 (вы ввели {speed})")
            except ValueError:
                print("Ошибка: введите целое число")

    def calculate_delay(self, speed):
        """Вычисляет задержку между главами"""
        return 3600 / speed

    def login(self, email, password):
        """Выполняет вход на сайт"""
        self.login_attempts += 1
        self.email = email
        self.password = password
        
        try:
            self.log_message(f"Попытка входа #{self.login_attempts}")
            if hasattr(self, 'telegram') and self.telegram:
                self.telegram.send_message(f"🔑 Попытка входа #{self.login_attempts}...")
            
            self.driver.delete_all_cookies()
            
            if not self.safe_get("https://mangabuff.ru/login"):
                self.log_message("Не удалось загрузить страницу входа", is_error=True)
                return False
            
            try:
                email_field = self.wait.until(
                    EC.presence_of_element_located((By.NAME, "email"))
                )
                pass_field = self.wait.until(
                    EC.presence_of_element_located((By.NAME, "password"))
                )
            except TimeoutException:
                self.log_message("Не удалось найти поля ввода на странице", is_error=True)
                self.save_debug_info("login_fields_missing")
                return False
            
            email_field.clear()
            email_field.send_keys(email)
            
            pass_field.clear()
            pass_field.send_keys(password)
            
            try:
                login_btn = self.wait.until(
                    EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Войти')]"))
                )
                login_btn.click()
            except Exception as e:
                self.log_message(f"Ошибка при нажатии кнопки входа: {str(e)}", is_error=True)
                self.save_debug_info("login_button_error")
                return False
            
            try:
                error_msg = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Неверный email или пароль')]"))
                )
                if error_msg:
                    self.log_message("Ошибка: Неверный email или пароль", is_error=True)
                    if hasattr(self, 'telegram') and self.telegram:
                        self.telegram.send_message("❌ Неверный email или пароль!")
                    return False
            except TimeoutException:
                if self.check_login_state():
                    self.log_message("Вход выполнен успешно!")
                    self.is_logged_in = True
                    if hasattr(self, 'telegram') and self.telegram:
                        self.telegram.send_message("✅ Вход выполнен успешно!")
                    return True
                
                self.log_message("Не удалось определить результат входа", is_error=True)
                self.save_debug_info("login_ambiguous")
                return False
                
        except Exception as e:
            self.log_message(f"Критическая ошибка при входе: {str(e)}", is_error=True)
            self.save_debug_info("login_crash")
            return False

    def get_manga_from_catalog(self, page=1):
        """Получает список манги с указанной страницы каталога"""
        try:
            url = f"https://mangabuff.ru/manga?page={page}"
            if not self.safe_get(url):
                self.log_message("Не удалось загрузить каталог", is_error=True)
                return None
            
            try:
                manga_cards = self.wait.until(
                    EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.cards__item"))
                )
            except TimeoutException:
                self.log_message("Карточки манги не найдены на странице", is_error=True)
                return None
            
            manga_list = []
            for card in manga_cards:
                try:
                    href = card.get_attribute("href")
                    if href and '/manga/' in href:
                        manga_slug = href.split('/')[-1]
                        if manga_slug and manga_slug != 'manga':
                            manga_list.append(manga_slug)
                except Exception as e:
                    self.log_message(f"Ошибка извлечения ссылки: {str(e)[:100]}", is_error=True)
                    continue
            
            return manga_list if manga_list else None
            
        except Exception as e:
            self.log_message(f"Ошибка получения каталога: {str(e)[:100]}", is_error=True)
            return None

    def get_chapters(self, manga_slug):
        """Получает список глав для указанной манги"""
        try:
            url = f"https://mangabuff.ru/manga/{manga_slug}"
            if not self.safe_get(url):
                self.log_message(f"Не удалось загрузить страницу манги {manga_slug}", is_error=True)
                return None
            
            sleep(3)
            
            try:
                chapters = []
                chapter_elements = self.wait.until(
                    EC.presence_of_all_elements_located(
                        (By.CSS_SELECTOR, "a.chapter-item, a.chapter-link, [href*='/manga/']")
                    )
                )
                
                for elem in chapter_elements:
                    try:
                        href = elem.get_attribute("href")
                        if href and '/manga/' in href:
                            parts = href.split('/')
                            if len(parts) >= 5:
                                volume = int(parts[-2])
                                chapter = int(parts[-1])
                                chapters.append((volume, chapter))
                    except Exception:
                        continue
                
                chapters = sorted(list(set(chapters)), key=lambda x: (x[0], x[1]))
                
                if not chapters:
                    self.log_message("Главы не найдены, используем том 1 главу 1")
                    return [(1, 1)]
                
                return chapters
                
            except Exception as e:
                self.log_message(f"Ошибка поиска глав: {str(e)[:100]}", is_error=True)
                return [(1, 1)]
        except Exception:
            return [(1, 1)]

    def read_chapter(self, manga_slug, volume, chapter):
        """Читает указанную главу манги с полной загрузкой страницы"""
        chapter_key = f"{manga_slug}_{volume}_{chapter}"
        
        if chapter_key in self.processed_chapters:
            self.log_message(f"Глава том {volume} глава {chapter} уже в списке обработанных")
            return None
        
        try:
            url = f"https://mangabuff.ru/manga/{manga_slug}/{volume}/{chapter}"
            if not self.safe_get(url):
                self.log_message(f"Не удалось загрузить главу: том {volume} глава {chapter}", is_error=True)
                return None
            
            # Улучшенная проверка загрузки контента
            try:
                self.wait.until(EC.presence_of_element_located(
                    (By.CSS_SELECTOR, ".reader-container, .reader, .manga-reader, .chapter-content, img")))
            except TimeoutException:
                try:
                    error_msg = self.driver.find_element(By.XPATH, 
                        "//*[contains(text(), 'недоступна') or contains(text(), 'удалена')]")
                    if error_msg:
                        self.log_message(f"Глава недоступна или удалена: том {volume} глава {chapter}", is_error=True)
                        self.processed_chapters.add(chapter_key)
                        return None
                except NoSuchElementException:
                    self.log_message("Контент главы загружен не полностью, но продолжаем обработку")
            
            # Добавляем в избранное (если еще не добавлено)
            try:
                favorite_btn = self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                        ".favourite-btn, .favorite-btn, [class*='favourite-btn'], [class*='favorite-btn']")))
                
                btn_classes = favorite_btn.get_attribute("class")
                is_active = "active" in btn_classes or "favourite-btn--active" in btn_classes
                
                if not is_active:
                    try:
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", favorite_btn)
                        sleep(1)
                        
                        favorite_btn.click()
                        sleep(2)
                        
                        btn_classes = favorite_btn.get_attribute("class")
                        is_active_now = "active" in btn_classes or "favourite-btn--active" in btn_classes
                        
                        if not is_active_now:
                            self.log_message("Кнопка избранного не изменила состояние после нажатия!")
                            favorite_btn.click()
                            sleep(2)
                    except Exception as e:
                        self.log_message(f"Не удалось нажать кнопку избранного: {str(e)[:100]}", is_error=True)
                        return None
            except Exception as e:
                self.log_message(f"Ошибка при работе с избранным: {str(e)[:100]}", is_error=True)
                return None

            # Прокрутка всей страницы для имитации чтения
            try:
                total_height = int(self.driver.execute_script("return document.body.scrollHeight"))
                viewport_height = int(self.driver.execute_script("return window.innerHeight"))
                
                scroll_steps = random.randint(10, 20)
                step_size = total_height // scroll_steps
                
                for i in range(1, scroll_steps + 1):
                    if self.user_interrupt or self.switch_manga_flag:
                        return None
                        
                    scroll_pos = min(i * step_size, total_height - viewport_height)
                    self.driver.execute_script(f"window.scrollTo(0, {scroll_pos});")
                    sleep(random.uniform(0.5, 2.0))
                    
                    if random.random() < 0.3:
                        try:
                            body = self.driver.find_element(By.TAG_NAME, 'body')
                            ActionChains(self.driver).move_to_element(body).click().perform()
                        except Exception:
                            pass
                
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
                sleep(3)
                
            except Exception as e:
                self.log_message(f"Ошибка при прокрутке страницы: {str(e)[:100]}", is_error=True)
                return None
            
            self.processed_chapters.add(chapter_key)
            self.log_message(f'Глава том {volume} глава {chapter} успешно обработана')
            
            chapters = self.get_chapters(manga_slug)
            if chapters:
                try:
                    current_idx = chapters.index((volume, chapter))
                    if current_idx + 1 < len(chapters):
                        return chapters[current_idx + 1]
                except ValueError:
                    pass
            
            return None
            
        except Exception as e:
            self.log_message(f'Критическая ошибка при обработке главы: {str(e)[:100]}', is_error=True)
            
            if "Tried to run command without establishing a connection" in str(e):
                self.initialize_driver()
            
            return None

    def process_manga(self, manga_slug):
        """Обрабатывает всю мангу до конца"""
        self.log_message(f"Начинаем чтение манги: {manga_slug}")
        
        chapters = self.get_chapters(manga_slug)
        total_chapters = len(chapters) if chapters else 0
        
        if hasattr(self, 'telegram') and self.telegram:
            try:
                self.telegram.send_message(
                    f"📚 Начинаем чтение манги: <b>{manga_slug}</b>\n"
                    f"⚡ Скорость: {self.reading_speed} глав/час"
                )
            except Exception as e:
                self.log_message(f"Ошибка отправки сообщения в Telegram: {str(e)}", is_error=True)
    
        read_count = 0
        
        while True:
            if self.user_interrupt or self.switch_manga_flag:
                self.log_message("Прерывание обработки манги по запросу пользователя")
                self.switch_manga_flag = False
                return False
                
            try:
                if not chapters:
                    chapters = self.get_chapters(manga_slug)
                    if not chapters:
                        self.log_message("Не удалось получить список глав", is_error=True)
                        return False
                
                current_pos = (self.current_volume, self.current_chapter)
                if current_pos not in chapters:
                    self.current_volume, self.current_chapter = chapters[0]
                    self.save_state()
                
                for i in range(len(chapters)):
                    if self.user_interrupt or self.switch_manga_flag:
                        self.log_message("Прерывание обработки глав по запросу пользователя")
                        self.switch_manga_flag = False
                        return False
                        
                    next_vol, next_ch = chapters[i]
                    
                    chapter_key = f"{manga_slug}_{next_vol}_{next_ch}"
                    if chapter_key in self.processed_chapters:
                        continue
                    
                    self.current_volume, self.current_chapter = next_vol, next_ch
                    self.save_state()
                    
                    result = self.read_chapter(manga_slug, next_vol, next_ch)
                    if result is not None:
                        read_count += 1
                    
                    if i < len(chapters) - 1:
                        delay = self.calculate_delay(self.reading_speed)
                        start_time = time.time()
                        while time.time() - start_time < delay:
                            if self.user_interrupt or self.switch_manga_flag:
                                self.log_message("Прерывание ожидания по запросу пользователя")
                                self.switch_manga_flag = False
                                return False
                            sleep(1)
            
                try:
                    updated_chapters = self.get_chapters(manga_slug)
                    if updated_chapters and len(updated_chapters) > len(chapters):
                        self.log_message(f"Обнаружены новые главы ({len(chapters)} -> {len(updated_chapters)})")
                        if hasattr(self, 'telegram') and self.telegram:
                            try:
                                self.telegram.send_message(
                                    f"🆕 Обнаружены новые главы для <b>{manga_slug}</b>!"
                                )
                            except Exception as e:
                                self.log_message(f"Ошибка отправки сообщения в Telegram: {str(e)}", is_error=True)
                        chapters = updated_chapters
                        continue
                except Exception as e:
                    self.log_message(f"Ошибка при проверке новых глав: {str(e)}", is_error=True)
                
                break
            
            except Exception as e:
                self.log_message(f"Ошибка в процессе чтения манги: {str(e)}", is_error=True)
                return False
        
        self.log_message(f"Закончили чтение манги: {manga_slug} (прочитано глав: {read_count})")
        if hasattr(self, 'telegram') and self.telegram:
            try:
                self.telegram.send_message(
                    f"🏁 Закончили чтение манги: <b>{manga_slug}</b>\n"
                    f"📊 Прочитано глав: {read_count}"
                )
            except Exception as e:
                self.log_message(f"Ошибка отправки сообщения в Telegram: {str(e)}", is_error=True)
        return True

    def keyboard_listener(self):
        """Слушает нажатия клавиш для управления ботом"""
        print("\nУправление ботом:")
        print("U - Переключиться на другую мангу")
        print("Q - Завершить работу\n")
        
        while not self.user_interrupt:
            if msvcrt.kbhit():
                key = msvcrt.getch().decode('utf-8').lower()
                if key == 'q':
                    self.user_interrupt = True
                    self.log_message("Получена команда на завершение работы")
                    if hasattr(self, 'telegram') and self.telegram:
                        self.telegram.send_message("🛑 Получена команда на завершение работы")
                elif key == 'u':
                    self.switch_manga_flag = True
                    self.log_message("Получена команда на переключение манги")
                    if hasattr(self, 'telegram') and self.telegram:
                        self.telegram.send_message("🔄 Получена команда на переключение манги")

    def main_loop(self):
        """Основной цикл работы бота"""
        max_page_attempts = 3
        page_attempts = 0
        
        keyboard_thread = threading.Thread(target=self.keyboard_listener, daemon=True)
        keyboard_thread.start()
        
        while not self.user_interrupt:
            try:
                if self.current_manga:
                    self.process_manga(self.current_manga)
                    self.current_manga = None
                    self.save_state()
                    continue
                
                manga_list = self.get_manga_from_catalog(self.current_page)
                
                if not manga_list:
                    page_attempts += 1
                    self.log_message(f"На странице {self.current_page} нет манги. Попытка {page_attempts}/{max_page_attempts}")
                    
                    if page_attempts >= max_page_attempts:
                        self.current_page = 1
                        page_attempts = 0
                        self.log_message("Сброс на первую страницу каталога")
                    else:
                        if self.current_page < self.MAX_CATALOG_PAGES:
                            self.current_page += 1
                        else:
                            self.current_page = 1
                    
                    self.save_state()
                    continue
                
                page_attempts = 0
                
                self.current_manga = random.choice(manga_list)
                self.current_volume = 1
                self.current_chapter = 1
                self.save_state()
                
                if len(self.processed_chapters) % 10 == 0:
                    self.send_status_report()
                
            except Exception as e:
                self.log_message(f'Ошибка в основном цикле: {str(e)[:100]}', is_error=True)
                self.save_debug_info("main_loop_error")
                sleep(10)
                self.initialize_driver()

    def send_status_report(self):
        """Отправляет отчет о статусе"""
        if not hasattr(self, 'telegram') or not self.telegram:
            return
            
        status = (
            f"📊 <b>MangaBot Status Report</b>\n"
            f"• Текущая манга: {self.current_manga or 'Нет'}\n"
            f"• Том/Глава: {self.current_volume}/{self.current_chapter}\n"
            f"• Прочитано глав: {len(self.processed_chapters)}\n"
            f"• Последняя ошибка: {self.last_error or 'Нет'}"
        )
        
        try:
            self.telegram.send_message(status)
            
            screenshot_path = "debug/current_status.png"
            self.driver.save_screenshot(screenshot_path)
            self.telegram.send_photo(
                screenshot_path,
                caption="Текущее состояние браузера"
            )
            
            if os.path.exists("manga_bot_log.txt"):
                self.telegram.send_document(
                    "manga_bot_log.txt",
                    caption="Полный лог работы бота"
                )
        except Exception as e:
            print(f"Ошибка отправки отчета: {str(e)}")

    def save_debug_info(self, prefix=""):
        """Сохраняет отладочную информацию"""
        try:
            os.makedirs("debug", exist_ok=True)
            timestamp = int(time.time())
            
            screenshot_path = f"debug/{prefix}debug_{timestamp}.png"
            self.driver.save_screenshot(screenshot_path)
            
            page_source_path = f"debug/{prefix}page_source_{timestamp}.html"
            with open(page_source_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
                
            cookies_path = f"debug/{prefix}cookies_{timestamp}.json"
            with open(cookies_path, "w") as f:
                json.dump(self.driver.get_cookies(), f)
                
            self.log_message(f"Сохранена отладочная информация: {screenshot_path}")
            
            if hasattr(self, 'telegram') and self.telegram:
                caption = f"🐛 Debug: {prefix}{timestamp}"
                self.telegram.send_photo(
                    screenshot_path,
                    caption=caption
                )
                self.telegram.send_document(
                    page_source_path,
                    caption=caption
                )
                
            return True
        except Exception as e:
            self.log_message(f"Ошибка сохранения отладочной информации: {str(e)}", is_error=True)
            return False

    def run(self):
        """Запуск программы"""
        try:
            self.log_message(f"Запуск бота для пользователя: {self.user_identity.username}@{self.user_identity.hostname}")
            self.log_message(f"Уникальный ID пользователя: {self.user_identity.user_id}")
            
            if self.load_state():
                self.log_message("Загружено сохраненное состояние")
                if hasattr(self, 'telegram') and self.telegram:
                    self.telegram.send_message("⚙ Загружено сохраненное состояние бота")
            
            email, password = self.get_credentials()
            
            while self.login_attempts < self.max_login_attempts and not self.user_interrupt:
                if self.login(email, password):
                    break
                
                if self.login_attempts >= self.max_login_attempts:
                    self.log_message("Достигнуто максимальное количество попыток входа", is_error=True)
                    return
            
            if not self.check_login_state():
                self.log_message("Не удалось авторизоваться. Завершение работы.", is_error=True)
                return
            
            self.reading_speed = self.get_reading_speed()
            self.log_message(f"Установлена скорость: {self.reading_speed} глав/час")
            
            self.main_loop()

        except KeyboardInterrupt:
            self.log_message("\nОстановлено пользователем")
            if hasattr(self, 'telegram') and self.telegram:
                self.telegram.send_message("⏸ Работа бота приостановлена пользователем")
            self.save_state()
        except Exception as e:
            self.log_message(f'Критическая ошибка: {e}', is_error=True)
            self.save_state()
            
            if hasattr(self, 'telegram') and self.telegram:
                error_msg = (
                    f"💥 <b>Критическая ошибка!</b>\n"
                    f"<code>{str(e)[:4000]}</code>\n\n"
                    f"📚 Манга: {self.current_manga or 'Нет'}\n"
                    f"📖 Том/Глава: {self.current_volume}/{self.current_chapter}\n"
                    f"🔄 Попытка восстановления..."
                )
                self.telegram.send_message(error_msg)
        finally:
            try:
                self.user_interrupt = True
                if self.driver:
                    self.driver.quit()
                self.log_message("Браузер закрыт")
                if hasattr(self, 'telegram') and self.telegram:
                    self.telegram.send_message("🛑 Браузер закрыт, работа завершена")
            except Exception as e:
                self.log_message(f"Ошибка при закрытии: {e}", is_error=True)

if __name__ == "__main__":
    if not os.path.exists("config.json"):
        config = {
            "telegram": {
                "token": "ВАШ_TELEGRAM_BOT_TOKEN",
                "chat_id": "ВАШ_CHAT_ID"
            }
        }
        with open("config.json", "w") as f:
            json.dump(config, f, indent=4)
        print("Создан файл config.json. Заполните его данными вашего Telegram бота.")
    else:
        bot = MangaReader()
        bot.run()
