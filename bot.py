import os
from dotenv import load_dotenv
load_dotenv()  # يستخدم محليًا فقط — Render سيتجاهله

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')
if ADMIN_USER_ID:
    ADMIN_USER_ID = int(ADMIN_USER_ID)

import os
import logging
import requests
import hashlib
import hmac
import time
import sqlite3
import re
import threading
import queue
import csv
from datetime import datetime, timedelta
import tempfile
import pytz
from urllib.parse import urlencode
from dotenv import load_dotenv

# تحميل المتغيرات من ملف .env
load_dotenv()

# إعداد التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_errors.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# تهيئة البوت





# تهيئة telebot
bot = None
try:
    if BOT_TOKEN and BOT_TOKEN != 'توكن_البوت_الخاص_بك':
        import telebot
        from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
        bot = telebot.TeleBot(BOT_TOKEN)
        logger.info("✅ تم تهيئة بوت Telegram بنجاح")
    else:
        logger.warning("⚠️ لم يتم تعيين BOT_TOKEN، البوت يعمل في وضع الاختبار")
        class MockBot:
            def __init__(self):
                self.message_handlers = []
            def message_handler(self, **kwargs):
                def decorator(func):
                    self.message_handlers.append((func, kwargs))
                    return func
                return decorator
            def callback_query_handler(self, **kwargs):
                def decorator(func):
                    return func
                return decorator
            def send_message(self, chat_id, text, **kwargs):
                print(f"📨 [TEST] إرسال رسالة إلى {chat_id}: {text}")
            def edit_message_text(self, text, chat_id, message_id, **kwargs):
                print(f"✏️ [TEST] تعديل الرسالة {message_id}: {text}")
            def delete_message(self, chat_id, message_id):
                print(f"🗑️ [TEST] حذف الرسالة {message_id}")
            def answer_callback_query(self, callback_query_id, **kwargs):
                print(f"🔔 [TEST] الرد على الاستعلام {callback_query_id}")
            def register_next_step_handler(self, message, func, *args, **kwargs):
                print(f"⏭️ [TEST] تسجيل معالج الخطوة التالية")
            def send_document(self, chat_id, document, **kwargs):
                print(f"📎 [TEST] إرسال مستند إلى {chat_id}")
            def polling(self, none_stop=True, timeout=120):
                print("🤖 [TEST] بدء وضع الاستطلاع (وهمي)")
                while True:
                    time.sleep(10)
                    
        class MockReplyKeyboardMarkup:
            def __init__(self, resize_keyboard=True):
                self.resize_keyboard = resize_keyboard
            def row(self, *buttons):
                return self
        class MockKeyboardButton:
            def __init__(self, text):
                self.text = text
        class MockInlineKeyboardMarkup:
            def __init__(self):
                pass
            def row(self, *buttons):
                return self
        class MockInlineKeyboardButton:
            def __init__(self, text, callback_data=None):
                self.text = text
                self.callback_data = callback_data
        
        ReplyKeyboardMarkup = MockReplyKeyboardMarkup
        KeyboardButton = MockKeyboardButton
        InlineKeyboardMarkup = MockInlineKeyboardMarkup
        InlineKeyboardButton = MockInlineKeyboardButton
        bot = MockBot()
        
except ImportError:
    logger.error("❌ لم يتم تثبيت telebot. قم بتثبيته: pip install pyTelegramBotAPI")
    class MockBot:
        def __init__(self):
            self.message_handlers = []
        def __getattr__(self, name):
            def mock_method(*args, **kwargs):
                print(f"🤖 [MOCK] {name}{args} {kwargs}")
            return mock_method
    class MockReplyKeyboardMarkup:
        def __init__(self, resize_keyboard=True):
            self.resize_keyboard = resize_keyboard
        def row(self, *buttons):
            return self
    class MockKeyboardButton:
        def __init__(self, text):
            self.text = text
    ReplyKeyboardMarkup = MockReplyKeyboardMarkup
    KeyboardButton = MockKeyboardButton
    InlineKeyboardMarkup = MockReplyKeyboardMarkup
    InlineKeyboardButton = MockKeyboardButton
    bot = MockBot()
except Exception as e:
    logger.error(f"❌ خطأ في تهيئة البوت: {e}")
    class MockBot:
        def __init__(self):
            self.message_handlers = []
        def __getattr__(self, name):
            def mock_method(*args, **kwargs):
                print(f"🤖 [MOCK] {name}{args} {kwargs}")
            return mock_method
    class MockReplyKeyboardMarkup:
        def __init__(self, resize_keyboard=True):
            self.resize_keyboard = resize_keyboard
        def row(self, *buttons):
            return self
    class MockKeyboardButton:
        def __init__(self, text):
            self.text = text
    ReplyKeyboardMarkup = MockReplyKeyboardMarkup
    KeyboardButton = MockKeyboardButton
    InlineKeyboardMarkup = MockReplyKeyboardMarkup
    InlineKeyboardButton = MockKeyboardButton
    bot = MockBot()

# نظام ذكي لإدارة حدود Binance
class BinanceRateLimiter:
    def __init__(self):
        self.last_request_time = 0
        self.request_count = 0
        self.lock = threading.Lock()
        
    def wait_if_needed(self):
        with self.lock:
            current_time = time.time()
            elapsed = current_time - self.last_request_time
            
            if elapsed > 1.0:
                self.request_count = 0
                self.last_request_time = current_time
                return
            
            if self.request_count >= 2:
                sleep_time = 1.1 - elapsed
                if sleep_time > 0:
                    logger.info(f"⏰ Rate limiting: Waiting {sleep_time:.2f}s")
                    time.sleep(sleep_time)
                self.request_count = 0
                self.last_request_time = time.time()
            else:
                self.request_count += 1

binance_limiter = BinanceRateLimiter()

# نظام تسجيل الاستردادات
class RedemptionLogger:
    def __init__(self, db_path="redemptions.db"):
        self.db_path = db_path
        self.init_database()
    
    def _convert_datetime_for_sqlite(self, dt):
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    
    def init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS redemptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                code TEXT,
                amount REAL,
                currency TEXT,
                status TEXT,
                timestamp TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usage_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                request_type TEXT,
                timestamp TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT UNIQUE,
                total_redemptions INTEGER DEFAULT 0,
                successful_redemptions INTEGER DEFAULT 0,
                total_amount REAL DEFAULT 0,
                unique_users INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE,
                value TEXT
            )
        ''')
        
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_redemptions_user_id ON redemptions(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_redemptions_timestamp ON redemptions(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_user_id ON usage_tracking(user_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_tracking(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_daily_stats_date ON daily_statistics(date)')
        
        default_settings = [
            ('rate_limit_minute', '20'),
            ('rate_limit_hour', '500'),  
            ('rate_limit_day', '2000'),
            ('auto_cleanup_days', '30'),
            ('language', 'ar'),
            ('max_codes_per_message', '30'),
            ('max_retries', '4'),
            ('retry_delay', '3'),
        ]
        
        cursor.executemany('''
            INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)
        ''', default_settings)
        
        conn.commit()
        conn.close()
    
    def log_redemption(self, user_id, username, code, amount, currency, status):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp_str = self._convert_datetime_for_sqlite(datetime.now())
        
        try:
            amount_float = float(amount)
        except (ValueError, TypeError):
            amount_float = 0.0
        
        cursor.execute('''
            INSERT INTO redemptions (user_id, username, code, amount, currency, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, code, amount_float, currency, status, timestamp_str))
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            INSERT OR IGNORE INTO daily_statistics (date) VALUES (?)
        ''', (today,))
        
        if status == 'success':
            cursor.execute('''
                UPDATE daily_statistics SET 
                total_redemptions = total_redemptions + 1,
                successful_redemptions = successful_redemptions + 1,
                total_amount = total_amount + ?
                WHERE date = ?
            ''', (amount_float, today))
        else:
            cursor.execute('''
                UPDATE daily_statistics SET 
                total_redemptions = total_redemptions + 1
                WHERE date = ?
            ''', (today,))
        
        cursor.execute('''
            UPDATE daily_statistics 
            SET unique_users = (
                SELECT COUNT(DISTINCT user_id) 
                FROM redemptions 
                WHERE date(timestamp) = date('now')
            )
            WHERE date = ?
        ''', (today,))
        
        conn.commit()
        conn.close()
    
    def get_user_redemptions(self, user_id, limit=15):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT code, amount, currency, status, timestamp 
            FROM redemptions 
            WHERE user_id = ? 
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        results = cursor.fetchall()
        conn.close()
        return results
    
    def get_setting(self, key, default=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else default
    
    def set_setting(self, key, value):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
        ''', (key, value))
        conn.commit()
        conn.close()
    
    def log_request(self, user_id, request_type):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        timestamp_str = self._convert_datetime_for_sqlite(datetime.now())
        
        cursor.execute('''
            INSERT INTO usage_tracking (user_id, request_type, timestamp)
            VALUES (?, ?, ?)
        ''', (user_id, request_type, timestamp_str))
        conn.commit()
        conn.close()
    
    def get_request_count(self, user_id, time_frame_minutes):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        time_threshold = datetime.now() - timedelta(minutes=time_frame_minutes)
        
        time_threshold_str = self._convert_datetime_for_sqlite(time_threshold)
        
        cursor.execute('''
            SELECT COUNT(*) FROM usage_tracking 
            WHERE user_id = ? AND timestamp >= ?
        ''', (user_id, time_threshold_str))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    
    def cleanup_old_data(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        auto_cleanup_days = int(self.get_setting('auto_cleanup_days', 30))
        cleanup_date = datetime.now() - timedelta(days=auto_cleanup_days)
        
        cleanup_date_str = self._convert_datetime_for_sqlite(cleanup_date)
        
        cursor.execute('DELETE FROM usage_tracking WHERE timestamp < ?', (cleanup_date_str,))
        cursor.execute('DELETE FROM redemptions WHERE timestamp < ?', (cleanup_date_str,))
        
        conn.commit()
        conn.close()
        logger.info(f"تم تنظيف البيانات الأقدم من {auto_cleanup_days} يوم")
    
    def get_daily_statistics(self, date=None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT total_redemptions, successful_redemptions, total_amount, unique_users
            FROM daily_statistics 
            WHERE date = ?
        ''', (date,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            total_redemptions, successful_redemptions, total_amount, unique_users = result
            success_rate = (successful_redemptions / total_redemptions * 100) if total_redemptions > 0 else 0
            
            return {
                'date': date,
                'total_redemptions': total_redemptions,
                'successful_redemptions': successful_redemptions,
                'total_amount': total_amount,
                'unique_users': unique_users,
                'success_rate': success_rate
            }
        else:
            return {
                'date': date,
                'total_redemptions': 0,
                'successful_redemptions': 0,
                'total_amount': 0,
                'unique_users': 0,
                'success_rate': 0
            }
    
    def get_multiple_days_statistics(self, days=7):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_date = (datetime.now() - timedelta(days=days-1)).strftime('%Y-%m-%d')
        
        cursor.execute('''
            SELECT date, total_redemptions, successful_redemptions, total_amount, unique_users
            FROM daily_statistics 
            WHERE date >= ?
            ORDER BY date DESC
        ''', (start_date,))
        
        results = cursor.fetchall()
        conn.close()
        
        stats = []
        for row in results:
            date, total_redemptions, successful_redemptions, total_amount, unique_users = row
            success_rate = (successful_redemptions / total_redemptions * 100) if total_redemptions > 0 else 0
            
            stats.append({
                'date': date,
                'total_redemptions': total_redemptions,
                'successful_redemptions': successful_redemptions,
                'total_amount': total_amount,
                'unique_users': unique_users,
                'success_rate': success_rate
            })
        
        return stats
    
    def export_to_csv(self, user_id=None, days=30):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        if user_id:
            query = '''
                SELECT user_id, username, code, amount, currency, status, timestamp
                FROM redemptions 
                WHERE timestamp >= ? AND user_id = ?
                ORDER BY timestamp DESC
            '''
            cursor.execute(query, (start_date, user_id))
        else:
            query = '''
                SELECT user_id, username, code, amount, currency, status, timestamp
                FROM redemptions 
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
            '''
            cursor.execute(query, (start_date,))
        
        rows = cursor.fetchall()
        conn.close()
        
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8')
        
        writer = csv.writer(temp_file)
        writer.writerow(['user_id', 'username', 'code', 'amount', 'currency', 'status', 'timestamp'])
        writer.writerows(rows)
        
        temp_file.close()
        
        return temp_file.name

redemption_logger = RedemptionLogger()

# نظام التخزين المؤقت المتقدم
class AdvancedCacheSystem:
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()
        self.processed_codes_db = "processed_codes.db"
        self.init_processed_codes_db()
    
    def init_processed_codes_db(self):
        conn = sqlite3.connect(self.processed_codes_db)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_codes (
                code TEXT PRIMARY KEY,
                status TEXT,
                amount REAL,
                currency TEXT,
                timestamp TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    def get(self, key):
        with self.lock:
            if key in self.cache and self.cache[key]['expiry'] > time.time():
                return self.cache[key]['value']
            
            conn = sqlite3.connect(self.processed_codes_db)
            cursor = conn.cursor()
            cursor.execute('SELECT status, amount, currency FROM processed_codes WHERE code = ?', (key.replace("code_", ""),))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                status, amount, currency = result
                cached_value = {
                    'status': status,
                    'amount': amount,
                    'currency': currency,
                    'from_db': True
                }
                self.cache[key] = {
                    'value': cached_value,
                    'expiry': time.time() + 3600
                }
                return cached_value
            
            return None
    
    def set(self, key, value, expiry_seconds=300):
        with self.lock:
            self.cache[key] = {
                'value': value,
                'expiry': time.time() + expiry_seconds
            }
            
            code = key.replace("code_", "")
            if 'status' in value and 'amount' in value:
                conn = sqlite3.connect(self.processed_codes_db)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR REPLACE INTO processed_codes (code, status, amount, currency, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (code, value['status'], value.get('amount', 0), value.get('currency', 'USD'), 
                      datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()
    
    def clear_expired(self):
        with self.lock:
            current_time = time.time()
            expired_keys = [k for k, v in self.cache.items() if v['expiry'] <= current_time]
            for key in expired_keys:
                del self.cache[key]

    def cleanup_24h_codes(self):
        try:
            conn = sqlite3.connect(self.processed_codes_db)
            cursor = conn.cursor()
            
            twenty_four_hours_ago = datetime.now() - timedelta(hours=24)
            cleanup_date_str = twenty_four_hours_ago.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute('DELETE FROM processed_codes WHERE timestamp >= ?', (cleanup_date_str,))
            db_deleted = cursor.rowcount
            
            with self.lock:
                keys_to_delete = []
                current_time = time.time()
                
                for key, value in self.cache.items():
                    if 'expiry' in value and value['expiry'] > current_time - 86400:
                        keys_to_delete.append(key)
                
                for key in keys_to_delete:
                    del self.cache[key]
            
            conn.commit()
            conn.close()
            
            logger.info(f"تم حذف {db_deleted} كود من التخزين المؤقت لآخر 24 ساعة")
            return db_deleted, len(keys_to_delete)
            
        except Exception as e:
            logger.error(f"خطأ في تنظيف الأكواد المؤقتة: {e}")
            return 0, 0

cache_system = AdvancedCacheSystem()

# نظام طابور المهام
task_queue = queue.Queue()
processing = False

def smart_task_processor():
    global processing
    processing = True
    
    while not task_queue.empty():
        try:
            task = task_queue.get_nowait()
            
            if task['type'] == 'multiple_codes':
                time.sleep(1.5)
            
            if task['type'] == 'single_code':
                process_single_code_async(task['message'], task['code'])
            elif task['type'] == 'multiple_codes':
                process_multiple_codes_async(task['message'], task['codes'])
            
            task_queue.task_done()
            time.sleep(0.8)
            
        except queue.Empty:
            break
        except Exception as e:
            logger.error(f"خطأ في معالجة المهمة: {e}")
            time.sleep(2)
    
    processing = False

def add_to_task_queue(task):
    task_queue.put(task)
    
    if not processing:
        threading.Thread(target=smart_task_processor, daemon=True).start()

def rate_limit_check(user_id):
    minute_limit = int(redemption_logger.get_setting('rate_limit_minute', 20))
    hour_limit = int(redemption_logger.get_setting('rate_limit_hour', 500))
    day_limit = int(redemption_logger.get_setting('rate_limit_day', 2000))
    
    minute_count = redemption_logger.get_request_count(user_id, 1)
    hour_count = redemption_logger.get_request_count(user_id, 60)
    day_count = redemption_logger.get_request_count(user_id, 1440)
    
    if minute_count >= minute_limit:
        return False, "⚠️ تجاوزت الحد المسموح للطلبات في الدقيقة"
    if hour_count >= hour_limit:
        return False, "⚠️ تجاوزت الحد المسموح للطلبات في الساعة"
    if day_count >= day_limit:
        return False, "⚠️ تجاوزت الحد المسموح للطلبات في اليوم"
    
    return True, ""

def create_binance_signature(api_secret, data):
    if not api_secret:
        logger.error("❌ API_SECRET غير معين أو فارغ")
        return "invalid_signature_empty_api_secret"
    
    try:
        return hmac.new(api_secret.encode('utf-8'), data.encode('utf-8'), hashlib.sha256).hexdigest()
    except AttributeError as e:
        logger.error(f"❌ خطأ في إنشاء التوقيع: {e}")
        return "invalid_signature_error"

def check_code_in_database(code):
    try:
        conn = sqlite3.connect("redemptions.db")
        cursor = conn.cursor()
        cursor.execute('''
            SELECT status, amount, currency, timestamp 
            FROM redemptions 
            WHERE code = ? 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''', (code,))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            status, amount, currency, timestamp = result
            return {
                'exists': True,
                'status': status,
                'amount': amount,
                'currency': currency,
                'timestamp': timestamp
            }
        return {'exists': False}
    except Exception as e:
        logger.error(f"خطأ في التحقق من الكود في قاعدة البيانات: {e}")
        return {'exists': False}

def is_valid_binance_code(code):
    pattern = r'^[A-Z0-9]{16}$'
    if not bool(re.match(pattern, code)):
        return False, "invalid_format"
    
    db_result = check_code_in_database(code)
    if db_result['exists']:
        return True, db_result['status']
    
    cached_result = cache_system.get(f"code_{code}")
    if cached_result:
        return True, cached_result['status']
    
    return True, "not_processed"

def extract_and_filter_codes(text):
    pattern = r'\b[A-Z0-9]{16}\b'
    all_codes = re.findall(pattern, text.upper())
    
    valid_codes = []
    skipped_codes = []
    
    for code in all_codes:
        db_result = check_code_in_database(code)
        if db_result['exists']:
            skipped_codes.append((code, db_result['status']))
            continue
            
        is_valid, status = is_valid_binance_code(code)
        if is_valid and status == "not_processed":
            valid_codes.append(code)
        else:
            skipped_codes.append((code, status))
    
    return valid_codes, skipped_codes

def send_initial_filter_report(message, valid_codes, skipped_codes):
    if not valid_codes and not skipped_codes:
        bot.send_message(message.chat.id,
                        "❌ *لم يتم العثور على أكواد صالحة*\n\n"
                        "يجب أن تكون الأكواد 16 حرفاً (أحرف كبيرة وأرقام فقط)",
                        parse_mode='Markdown',
                        reply_markup=create_main_keyboard(message.from_user.id))
        return False
    
    report_msg = f"""
🔍 *تقرير التحليل الأولي:*

• 📋 العدد الإجمالي: {len(valid_codes) + len(skipped_codes)}
• ✅ الصالحة للمعالجة: {len(valid_codes)}
• ⏭️ سيتم تخطيها: {len(skipped_codes)}
    """
    
    if skipped_codes:
        skipped_list = []
        for code, status in skipped_codes[:5]:
            if status == 'success':
                status_text = "✅ تم استرداده بنجاح مسبقاً"
            elif status == 'already_redeemed':
                status_text = "⚠️ مستخدم مسبقاً في Binance"
            elif status == 'failed':
                status_text = "❌ فشل في الاسترداد مسبقاً"
            else:
                status_text = f"⏭️ {status}"
            
            skipped_list.append(f"• {code} ({status_text})")
        
        if len(skipped_codes) > 5:
            skipped_list.append(f"• ... و {len(skipped_codes) - 5} أخرى")
        
        report_msg += f"\n\n📝 *الأكواد المتخطاة:*\n" + "\n".join(skipped_list)
    
    if valid_codes:
        valid_list = "\n".join([f"• {code}" for code in valid_codes[:3]])
        if len(valid_codes) > 3:
            valid_list += f"\n• ... و {len(valid_codes) - 3} أخرى"
        
        report_msg += f"\n\n🎯 *الأكواد التي سيتم معالجتها:*\n{valid_list}"
    
    bot.send_message(message.chat.id, report_msg, parse_mode='Markdown')
    
    if not valid_codes:
        bot.send_message(message.chat.id,
                        "⚠️ *لا توجد أكواد جديدة للمعالجة*",
                        parse_mode='Markdown',
                        reply_markup=create_main_keyboard(message.from_user.id))
        return False
    
    return True

def redeem_gift_card(code, retries=None):
    if retries is None:
        retries = int(redemption_logger.get_setting('max_retries', 4))
    
    binance_limiter.wait_if_needed()
    
    cached_result = cache_system.get(f"code_{code}")
    if cached_result and cached_result.get('from_db') != True:
        logger.info(f"تم استخدام النتيجة المخزنة مؤقتًا للكود: {code}")
        return cached_result
    
    try:
        api_key = os.getenv('API_KEY')
        api_secret = os.getenv('API_SECRET')
        
        if not api_key or not api_secret or api_key in ['مفتاح_Binance_API_هنا', 'API_KEY']:
            return {
                'success': False,
                'error': 'مفاتيح API غير معينة',
                'error_type': 'api_keys_not_set'
            }
        
        base_url = "https://api.binance.com"
        endpoint = "/sapi/v1/giftcard/redeemCode"
        
        for attempt in range(retries):
            try:
                params = {
                    'code': code,
                    'timestamp': int(time.time() * 1000)
                }
                
                query_string = urlencode(params)
                signature = create_binance_signature(api_secret, query_string)
                params['signature'] = signature
                
                headers = {
                    'X-MBX-APIKEY': api_key,
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                timeout = 15 if attempt == 0 else 25
                
                response = requests.post(
                    f"{base_url}{endpoint}",
                    params=params,
                    headers=headers,
                    timeout=timeout
                )
                
                if response.status_code == 429:
                    wait_time = 10 + (attempt * 5)
                    logger.warning(f"⏰ Rate limit للكود {code}, الانتظار {wait_time} ثانية")
                    time.sleep(wait_time)
                    continue
                    
                elif response.status_code >= 500:
                    wait_time = 5 + (attempt * 3)
                    logger.warning(f"🌐 خطأ خادم للكود {code}, الانتظار {wait_time} ثانية")
                    time.sleep(wait_time)
                    continue
                
                result = response.json()
                
                if result.get('success'):
                    success_data = {
                        'success': True,
                        'data': result.get('data', {}),
                        'already_redeemed': False,
                        'invalid_code': False
                    }
                    cache_system.set(f"code_{code}", success_data, expiry_seconds=86400)
                    return success_data
                    
                else:
                    error_msg = result.get('message', '').lower()
                    
                    if 'already redeemed' in error_msg:
                        return {
                            'success': False,
                            'already_redeemed': True,
                            'error': 'تم استرداده مسبقاً'
                        }
                    elif 'invalid' in error_msg:
                        return {
                            'success': False,
                            'invalid_code': True,
                            'error': 'كود غير صالح'
                        }
                    else:
                        if attempt < retries - 1:
                            wait_time = 3 + (attempt * 2)
                            logger.warning(f"🔄 محاولة {attempt + 2} للكود {code}, الانتظار {wait_time} ثانية")
                            time.sleep(wait_time)
                            continue
                        else:
                            return {
                                'success': False,
                                'error': result.get('message', 'خطأ غير معروف')
                            }
                
            except requests.exceptions.Timeout:
                if attempt < retries - 1:
                    wait_time = 8 + (attempt * 3)
                    logger.warning(f"⌛ timeout للكود {code}, المحاولة {attempt + 2}")
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        'success': False,
                        'error': 'انتهت مهلة الاتصال'
                    }
                    
            except Exception as e:
                if attempt < retries - 1:
                    wait_time = 4 + (attempt * 2)
                    logger.warning(f"⚠️ خطأ في الكود {code}, المحاولة {attempt + 2}")
                    time.sleep(wait_time)
                    continue
                else:
                    return {
                        'success': False,
                        'error': str(e)
                    }
                    
    except Exception as e:
        logger.error(f"خطأ غير متوقع في استرداد الكود {code}: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def send_admin_report(user, codes_data, redemption_type="single"):
    try:
        if ADMIN_USER_ID == 0:
            return
        
        user_info = f"👤 المستخدم: {user.first_name}"
        if user.username:
            user_info += f" (@{user.username})"
        user_info += f"\n🆔 الايدي: {user.id}"
        
        if redemption_type == "single":
            code_data = codes_data[0]
            report_message = f"""
📋 *تقرير استرداد جديد*

{user_info}
• الكود: `{code_data['code']}`
• الحالة: {code_data['status']}
• المبلغ: {code_data['amount']} {code_data['currency']}
• الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            """
        else:
            total_codes = len(codes_data)
            success_count = sum(1 for code in codes_data if code['status'] == 'success')
            already_redeemed_count = sum(1 for code in codes_data if code['status'] == 'already_redeemed')
            failed_count = sum(1 for code in codes_data if code['status'] == 'failed')
            total_amount = sum(float(code['amount']) for code in codes_data if code['status'] == 'success')
            
            report_message = f"""
📊 *تقرير استرداد جماعي*

{user_info}
• 📦 العدد الإجمالي: {total_codes}
• ✅ الناجحة: {success_count}
• ⚠️ المستخدمة مسبقاً: {already_redeemed_count}
• ❌ الفاشلة: {failed_count}
• 💰 المبلغ الإجمالي: {total_amount:.2f} USDT
• 🕒 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📝 *تفاصيل الأكواد:*
"""
            for i, code_data in enumerate(codes_data[:10]):
                status_icon = "✅" if code_data['status'] == 'success' else "⚠️" if code_data['status'] == 'already_redeemed' else "❌"
                report_message += f"\n{i+1}. {status_icon} `{code_data['code']}` - {code_data['amount']} {code_data['currency']}"
            
            if total_codes > 10:
                report_message += f"\n• ... و {total_codes - 10} كود أخرى"
        
        bot.send_message(ADMIN_USER_ID, report_message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"❌ خطأ في إرسال التقرير إلى المدير: {str(e)}")

def handle_bot_error(chat_id, error_message=None):
    error_msg = """
🔴 *الخدمة غير متوفرة الأن*
الرجاء المحاولة لاحقاً
    """
    
    try:
        bot.send_message(chat_id, error_msg, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"❌ فشل في إرسال رسالة الخطأ: {e}")

def global_error_handler(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"❌ خطأ غير متوقع في {func.__name__}: {e}")
            
            chat_id = None
            for arg in args:
                if hasattr(arg, 'chat') and hasattr(arg.chat, 'id'):
                    chat_id = arg.chat.id
                    break
                elif hasattr(arg, 'chat_id'):
                    chat_id = arg.chat_id
                    break
            
            if chat_id:
                handle_bot_error(chat_id, str(e))
            
            return None
    return wrapper

@global_error_handler
def process_single_code_async(message, code):
    try:
        processing_msg = bot.send_message(message.chat.id, 
                                        f"⏳ جاري معالجة الكود: `{code}`...",
                                        parse_mode='Markdown')
        
        result = redeem_gift_card(code)
        username = message.from_user.username or message.from_user.first_name
        
        if result.get('success'):
            amount_data = result.get('data', {}).get('amount', 0)
            currency = result.get('data', {}).get('currency', 'USDT')
            
            try:
                amount = float(amount_data)
            except (ValueError, TypeError):
                amount = 0.0
            
            redemption_logger.log_redemption(
                message.from_user.id, username, code, amount, currency, 'success'
            )
            
            response = f"""
✅ *تم الاسترداد بنجاح!*

📋 *التفاصيل:*
• الكود: `{code}`
• المبلغ: *{amount} {currency}*
• الحالة: ناجح ✅
            """
            
            send_admin_report(message.from_user, [{
                'code': code,
                'status': 'success',
                'amount': amount,
                'currency': currency
            }])
            
        elif result.get('already_redeemed'):
            redemption_logger.log_redemption(
                message.from_user.id, username, code, 0.0, 'USD', 'already_redeemed'
            )
            
            response = f"""
⚠️ *الكود تم استرداده مسبقاً*

• الكود: `{code}`
• الحالة: مستخدم سابقاً ⚠️
• المبلغ: 0.00 USDT (تم استرداده مسبقاً)
            """
            
            send_admin_report(message.from_user, [{
                'code': code,
                'status': 'already_redeemed',
                'amount': 0.0,
                'currency': 'USD'
            }])
            
        else:
            error_msg = result.get('error', 'خطأ غير معروف')
            
            redemption_logger.log_redemption(
                message.from_user.id, username, code, 0.0, 'USD', 'failed'
            )
            
            response = f"""
❌ *فشل الاسترداد*

• الكود: `{code}`
• الخطأ: {error_msg}
            """
            
            send_admin_report(message.from_user, [{
                'code': code,
                'status': 'failed',
                'amount': 0.0,
                'currency': 'USD',
                'error': error_msg
            }])
        
        bot.send_message(message.chat.id, response, 
                        parse_mode='Markdown',
                        reply_markup=create_main_keyboard(message.from_user.id))
        
        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except:
            pass
            
    except Exception as e:
        logger.error(f"خطأ في معالجة الكود {code}: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def process_multiple_codes_async(message, codes):
    try:
        MAX_CODES = int(redemption_logger.get_setting('max_codes_per_message', 30))
        if len(codes) > MAX_CODES:
            codes = codes[:MAX_CODES]
            bot.send_message(message.chat.id,
                            f"⚠️ *تم تحديد الحد الأقصى*\n"
                            f"تم اختيار أول {MAX_CODES} كود فقط",
                            parse_mode='Markdown')
        
        total_codes = len(codes)
        processing_msg = bot.send_message(message.chat.id, 
                                        f"⏳ جاري معالجة {total_codes} كود...",
                                        parse_mode='Markdown')
        
        results = []
        success_count = 0
        already_redeemed_count = 0
        failed_count = 0
        total_amount = 0.0
        
        for i, code in enumerate(codes, 1):
            try:
                progress = (i / total_codes) * 100
                try:
                    bot.edit_message_text(
                        f"⏳ جاري معالجة الكود {i} من {total_codes}\n"
                        f"📊 التقدم: {progress:.1f}%\n"
                        f"✅ الناجحة: {success_count} | ⚠️ المستخدمة: {already_redeemed_count} | ❌ الفاشلة: {failed_count}\n"
                        f"💰 المجموع: {total_amount:.2f} USDT",
                        message.chat.id,
                        processing_msg.message_id
                    )
                except:
                    pass
                
                result = redeem_gift_card(code)
                results.append((code, result))
                
                username = message.from_user.username or message.from_user.first_name
                
                if result.get('success'):
                    amount = float(result.get('data', {}).get('amount', 0))
                    currency = result.get('data', {}).get('currency', 'USDT')
                    
                    success_count += 1
                    total_amount += amount
                    redemption_logger.log_redemption(
                        message.from_user.id, username, code, amount, currency, 'success'
                    )
                    
                elif result.get('already_redeemed'):
                    already_redeemed_count += 1
                    redemption_logger.log_redemption(
                        message.from_user.id, username, code, 0.0, 'USD', 'already_redeemed'
                    )
                    
                else:
                    failed_count += 1
                    redemption_logger.log_redemption(
                        message.from_user.id, username, code, 0.0, 'USD', 'failed'
                    )
                
                time.sleep(0.8)
                
            except Exception as e:
                logger.error(f"خطأ في معالجة الكود {code}: {str(e)}")
                failed_count += 1
                results.append((code, {'error': str(e), 'success': False}))
                time.sleep(1.5)
        
        admin_report_data = []
        for code, result in results:
            if result.get('success'):
                amount_data = result.get('data', {}).get('amount', 0)
                currency = result.get('data', {}).get('currency', 'USDT')
                try:
                    amount = float(amount_data)
                except (ValueError, TypeError):
                    amount = 0.0
                admin_report_data.append({
                    'code': code,
                    'status': 'success',
                    'amount': amount,
                    'currency': currency
                })
            elif result.get('already_redeemed'):
                admin_report_data.append({
                    'code': code,
                    'status': 'already_redeemed',
                    'amount': 0.0,
                    'currency': 'USD'
                })
            else:
                admin_report_data.append({
                    'code': code,
                    'status': 'failed',
                    'amount': 0.0,
                    'currency': 'USD'
                })
        
        send_admin_report(message.from_user, admin_report_data, "multiple")
        
        total_processed = success_count + already_redeemed_count + failed_count
        
        summary = f"""
📊 *تقرير المعالجة:*

• 📦 العدد الإجمالي: {total_codes}
• ✅ الناجحة: {success_count}
• ⚠️ المستخدمة مسبقاً: {already_redeemed_count}
• ❌ الفاشلة: {failed_count}
• 💰 المبلغ الإجمالي: {total_amount:.2f} USDT
        """
        
        bot.send_message(message.chat.id, summary, parse_mode='Markdown')
        
        final_msg = f"""
🎯 *معالجة مكتملة!*

📊 لمشاهدة السجل: اضغط على "📊 استرداداتي"
        """
        
        bot.send_message(message.chat.id, final_msg,
                        parse_mode='Markdown',
                        reply_markup=create_main_keyboard(message.from_user.id))
        
        try:
            bot.delete_message(message.chat.id, processing_msg.message_id)
        except:
            pass
            
    except Exception as e:
        logger.error(f"خطأ في معالجة الأكواد المتعددة: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

def create_main_keyboard(user_id):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("🎁 استرداد كود"))
    keyboard.row(KeyboardButton("📊 استرداداتي"), KeyboardButton("ℹ️ المساعدة"))
    
    if user_id == ADMIN_USER_ID:
        keyboard.row(KeyboardButton("👨‍💻 لوحة التحكم"))
    
    return keyboard

def create_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.row(KeyboardButton("📈 الإحصائيات"), KeyboardButton("⚙️ الإعدادات"))
    keyboard.row(KeyboardButton("📤 تصدير البيانات"), KeyboardButton("🧹 تنظيف البيانات"))
    keyboard.row(KeyboardButton("📢 بث جماعي"))  # الزر الجديد
    keyboard.row(KeyboardButton("🔙 القائمة الرئيسية"))
    return keyboard

@global_error_handler
def send_welcome(message):
    redemption_logger.log_request(message.from_user.id, 'start')
    
    allowed, error_msg = rate_limit_check(message.from_user.id)
    if not allowed:
        bot.send_message(message.chat.id, error_msg)
        return
    
    welcome_text = """
🌟 *مرحباً بك في بوت استرداد أكواد Binance الاحترافي!* 🌟

⚡ *مميزات البوت:*
• ✅ استرداد أكواد Binance بسرعة واحترافية
• 📊 تتبع جميع عمليات الاسترداد بشكل مفصل
• 🛡️ نظام آمن يحافظ على خصوصيتك
• ⚡ معالجة متعددة للأكواد في وقت واحد

📝 *كيفية الاستخدام:*
1. أرسل كود الهدية (16 حرفاً) أو عدة أكواد
2. انتظر حتى انتهاء المعالجة
3. احصل على تقرير مفصل بنتائج الاسترداد

⚡ *نصائح للاستخدام الأمثل:*
- أرسل 10-20 كود في كل رسالة للحصول على أفضل أداء
- تأكد من صحة formato الأكواد (16 حرفاً، أحرف كبيرة وأرقام فقط)
- انتظر حتى انتهاء المعالجة قبل إرسال المزيد

📦 *الحد الأقصى: 30 كود في الرسالة الواحدة*

🔒 *خصوصيتك مهمة لنا:* لا يتم تخزين أي بيانات شخصية
    """
    
    bot.send_message(message.chat.id, welcome_text, 
                    parse_mode='Markdown', 
                    reply_markup=create_main_keyboard(message.from_user.id))

@global_error_handler
def help_menu(message):
    redemption_logger.log_request(message.from_user.id, 'help')
    
    allowed, error_msg = rate_limit_check(message.from_user.id)
    if not allowed:
        bot.send_message(message.chat.id, error_msg)
        return
    
    help_text = """
📖 *دليل الاستخدام:*

🎁 *كيفية الاسترداد:*
- أرسل كود الهدية (16 حرفاً)
- أو أرسل عدة أكواد معاً

📊 *لمعرفة السجل:*
- اضغط على "📊 استرداداتي"

⚠️ *ملاحظات:*
- المعالجة قد تستغرق وقتاً
- بعض الأكواد قد لا تعمل
- الحد الأقصى 30 كود في الرسالة
    """
    bot.send_message(message.chat.id, help_text, 
                    parse_mode='Markdown',
                    reply_markup=create_main_keyboard(message.from_user.id))

@global_error_handler
def show_redemptions(message):
    redemption_logger.log_request(message.from_user.id, 'my_redemptions')
    
    allowed, error_msg = rate_limit_check(message.from_user.id)
    if not allowed:
        bot.send_message(message.chat.id, error_msg)
        return
    
    try:
        redemptions = redemption_logger.get_user_redemptions(message.from_user.id)
        
        if not redemptions:
            bot.send_message(message.chat.id, 
                            "📭 لم تقم بأي عمليات استرداد بعد",
                            reply_markup=create_main_keyboard(message.from_user.id))
            return
        
        redemption_list = []
        total_success = 0.0
        success_count = 0
        already_redeemed_count = 0
        
        for i, (code, amount, currency, status, timestamp) in enumerate(redemptions, 1):
            if status == 'success':
                status_icon = "✅"
                total_success += float(amount)
                success_count += 1
            elif status == 'already_redeemed':
                status_icon = "⚠️"
                already_redeemed_count += 1
            else:
                status_icon = "❌"
            
            date_str = timestamp.split()[0] if isinstance(timestamp, str) else timestamp[:10]
            redemption_list.append(f"{i}. {status_icon} {code} - {amount} {currency} - {status}")
        
        response = f"""
📋 *سجل استرداداتك:*

{chr(10).join(redemption_list)}

💰 *الإجمالي الناجح:* {total_success:.2f} USDT
🎯 *عدد النجاحات:* {success_count}
⚠️ *المستخدمة مسبقاً:* {already_redeemed_count}
        """
        bot.send_message(message.chat.id, response, 
                        parse_mode='Markdown',
                        reply_markup=create_main_keyboard(message.from_user.id))
        
    except Exception as e:
        logger.error(f"خطأ في جلب سجل الاستردادات: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def ask_for_code(message):
    redemption_logger.log_request(message.from_user.id, 'redeem_code')
    
    allowed, error_msg = rate_limit_check(message.from_user.id)
    if not allowed:
        bot.send_message(message.chat.id, error_msg)
        return
    
    help_text = """
🎁 *استرداد أكواد Binance*

يمكنك إرسال:
- كود واحد فقط
- أو عدة أكواد معاً في نفس الرسالة

⚡ *ملاحظة مهمة:*
- الكود يجب أن يكون 16 حرفاً (أحرف إنجليزية كبيره وأرقام فقط)
- الحد الأقصى 30 كود في كل مرة

📤 **أرسل الأكواد الآن لبدء الاسترداد**
    """
    
    bot.send_message(message.chat.id, help_text, 
                    parse_mode='Markdown',
                    reply_markup=create_main_keyboard(message.from_user.id))

@global_error_handler
def admin_panel(message):
    bot.send_message(message.chat.id, "مرحباً بك في لوحة التحكم الإدارية", reply_markup=create_admin_keyboard())

@global_error_handler
def admin_back_to_main(message):
    bot.send_message(message.chat.id, "تم العودة إلى القائمة الرئيسية", reply_markup=create_main_keyboard(message.from_user.id))

@global_error_handler
def admin_statistics(message):
    try:
        today_stats = redemption_logger.get_daily_statistics()
        weekly_stats = redemption_logger.get_multiple_days_statistics(7)
        
        weekly_totals = {
            'total_redemptions': sum(day['total_redemptions'] for day in weekly_stats),
            'successful_redemptions': sum(day['successful_redemptions'] for day in weekly_stats),
            'total_amount': sum(day['total_amount'] for day in weekly_stats),
            'unique_users': len(set(day['date'] for day in weekly_stats))
        }
        
        response = f"""
📊 *الإحصائيات الإدارية - اليوم*

• 📅 التاريخ: {today_stats['date']}
• 📦 إجمالي المحاولات: {today_stats['total_redemptions']}
• ✅ المحاولات الناجحة: {today_stats['successful_redemptions']}
• 💰 المبلغ الإجمالي: {today_stats['total_amount']:.2f} USDT
• 👥 المستخدمون الفريدون: {today_stats['unique_users']}

📈 *إحصائيات آخر 7 أيام:*
• 📦 إجمالي المحاولات: {weekly_totals['total_redemptions']}
• ✅ المحاولات الناجحة: {weekly_totals['successful_redemptions']}
• 💰 المبلغ الإجمالي: {weekly_totals['total_amount']:.2f} USDT

⚙️ *الإعدادات الحالية:*
• الحد الأقصى/الدقيقة: {redemption_logger.get_setting('rate_limit_minute')}
• الحد الأقصى/الساعة: {redemption_logger.get_setting('rate_limit_hour')}
• الحد الأقصى/اليوم: {redemption_logger.get_setting('rate_limit_day')}
        """
        
        bot.send_message(message.chat.id, response, parse_mode='Markdown', reply_markup=create_admin_keyboard())
        
    except Exception as e:
        logger.error(f"خطأ في جلب الإحصائيات: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def admin_settings(message):
    try:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("حد الدقيقة", callback_data="setting_minute"),
            InlineKeyboardButton("حد الساعة", callback_data="setting_hour")
        )
        keyboard.row(
            InlineKeyboardButton("حد اليوم", callback_data="setting_day"),
            InlineKeyboardButton("أيام التنظيف", callback_data="setting_cleanup")
        )
        keyboard.row(InlineKeyboardButton("🔙 رجوع", callback_data="admin_back"))
        
        settings_text = """
⚙️ *الإعدادات الحالية:*

• الحد الأقصى للطلبات في الدقيقة: {minute}
• الحد الأقصى للطلبات في الساعة: {hour}
• الحد الأقصى للطلبات في اليوم: {day}
• أيام التنظيف التلقائي: {cleanup}

اختر الإعداد الذي تريد تعديله:
        """.format(
            minute=redemption_logger.get_setting('rate_limit_minute'),
            hour=redemption_logger.get_setting('rate_limit_hour'),
            day=redemption_logger.get_setting('rate_limit_day'),
            cleanup=redemption_logger.get_setting('auto_cleanup_days')
        )
        
        bot.send_message(message.chat.id, settings_text, parse_mode='Markdown', reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"خطأ في عرض الإعدادات: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def admin_export_data(message):
    try:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("📊 7 أيام", callback_data="export_7"),
            InlineKeyboardButton("📈 30 يوم", callback_data="export_30")
        )
        keyboard.row(
            InlineKeyboardButton("🗓️ 90 يوم", callback_data="export_90"),
            InlineKeyboardButton("📆 كل البيانات", callback_data="export_all")
        )
        keyboard.row(InlineKeyboardButton("🔙 رجوع", callback_data="admin_back"))
        
        bot.send_message(message.chat.id, "📤 اختر الفترة الزمنية للتصدير:", reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"خطأ في تصدير البيانات: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def admin_cleanup_data(message):
    try:
        keyboard = InlineKeyboardMarkup()
        keyboard.row(
            InlineKeyboardButton("🧹 تنظيف أكواد 24 ساعة", callback_data="cleanup_24h_codes"),
            InlineKeyboardButton("🧹 تنظيف كامل", callback_data="cleanup_now")
        )
        keyboard.row(InlineKeyboardButton("🔙 رجوع", callback_data="admin_back"))
        
        conn = sqlite3.connect("processed_codes.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM processed_codes WHERE timestamp >= datetime('now', '-1 day')")
        recent_codes = cursor.fetchone()[0]
        conn.close()
        
        cleanup_text = f"""
🧹 *خيارات تنظيف التخزين المؤقت*

• 📦 الأكواد في الذاكرة: {len(cache_system.cache)}
• 🗃️ الأكواد المؤقتة (24h): {recent_codes}

📊 *اختر نوع التنظيف:*
• تنظيف أكواد 24 ساعة - يحذف الأكواد الحديثة من التخزين المؤقت فقط
• تنظيف كامل - التنظيف العادي للبيانات القديمة
        """
        
        bot.send_message(message.chat.id, cleanup_text, parse_mode='Markdown', reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"خطأ في عرض خيارات التنظيف: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def admin_broadcast(message):
    try:
        if message.text == "📢 بث جماعي":
            msg = bot.send_message(message.chat.id, "أرسل الرسالة التي تريد بثها للمستخدمين:")
            bot.register_next_step_handler(msg, process_broadcast_message)
            return
            
    except Exception as e:
        logger.error(f"خطأ في البث الجماعي: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def process_broadcast_message(message):
    try:
        broadcast_text = message.text
        
        # الحصول على جميع المستخدمين الفريدين من قاعدة البيانات
        conn = sqlite3.connect("redemptions.db")
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT user_id FROM redemptions')
        user_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        # إضافة المستخدمين الجدد الذين لم يستخدموا البوت بعد
        user_ids.append(ADMIN_USER_ID)
        user_ids = list(set(user_ids))  # إزالة التكرارات
        
        success_count = 0
        fail_count = 0
        total_users = len(user_ids)
        
        progress_msg = bot.send_message(message.chat.id, 
                                      f"⏳ جاري إرسال الرسالة لـ {total_users} مستخدم...\n\n"
                                      f"✅ تم إرسالها لـ 0 مستخدم\n"
                                      f"❌ فشل إرسالها لـ 0 مستخدم")
        
        for index, user_id in enumerate(user_ids):
            try:
                # تخطي المستخدمين غير الصالحين
                if not user_id or user_id == 0:
                    continue
                    
                bot.send_message(user_id, f"📢 إشعار من إدارة البوت:\n\n{broadcast_text}")
                success_count += 1
                
                # تحديث رسالة التقدم كل 10 مستخدمين
                if index % 10 == 0:
                    try:
                        bot.edit_message_text(
                            f"⏳ جاري إرسال الرسالة لـ {total_users} مستخدم...\n\n"
                            f"✅ تم إرسالها لـ {success_count} مستخدم\n"
                            f"❌ فشل إرسالها لـ {fail_count} مستخدم",
                            message.chat.id,
                            progress_msg.message_id
                        )
                    except:
                        pass
                        
            except Exception as e:
                fail_count += 1
                logger.error(f"فشل إرسال رسالة للمستخدم {user_id}: {str(e)}")
            
            time.sleep(0.2)  # تقليل الضغط على API
        
        # إرسال التقرير النهائي
        report_text = f"""
📊 *تقرير البث الجماعي:*

• 👥 إجمالي المستهدفين: {total_users}
• ✅ تم الإرسال بنجاح: {success_count}
• ❌ فشل في الإرسال: {fail_count}
• 📈 نسبة النجاح: {(success_count/total_users*100):.1f}%
        """
        
        bot.send_message(message.chat.id, report_text, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"خطأ في معالجة البث الجماعي: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def handle_callback_query(call):
    try:
        if call.data.startswith("setting_"):
            setting_type = call.data.split("_")[1]
            setting_names = {
                "minute": "rate_limit_minute",
                "hour": "rate_limit_hour",
                "day": "rate_limit_day",
                "cleanup": "auto_cleanup_days"
            }
            
            if setting_type in setting_names:
                current_value = redemption_logger.get_setting(setting_names[setting_type])
                msg = bot.send_message(call.message.chat.id, f"أدخل القيمة الجديدة للإعداد ({setting_type}):\nالقيمة الحالية: {current_value}")
                bot.register_next_step_handler(msg, process_setting_change, setting_names[setting_type])
            
        elif call.data.startswith("export_"):
            if call.data == "export_7":
                days = 7
            elif call.data == "export_30":
                days = 30
            elif call.data == "export_90":
                days = 90
            else:
                days = 3650
            
            csv_file = redemption_logger.export_to_csv(days=days)
            
            with open(csv_file, 'rb') as f:
                bot.send_document(call.message.chat.id, f, caption=f"📊 بيانات الاستردادات لآخر {days} يوم")
            
            os.unlink(csv_file)
            
        elif call.data == "cleanup_now":
            redemption_logger.cleanup_old_data()
            bot.send_message(call.message.chat.id, "✅ تم تنظيف البيانات القديمة بنجاح")
            
        elif call.data == "cleanup_24h_codes":
            db_deleted, memory_deleted = cache_system.cleanup_24h_codes()
            
            bot.send_message(
                call.message.chat.id,
                f"✅ تم تنظيف الأكواد المؤقتة لآخر 24 ساعة\n\n"
                f"• 🗃️ الأكواد المحذوفة من قاعدة البيانات: {db_deleted}\n"
                f"• 💾 الأكواد المحذوفة من الذاكرة: {memory_deleted}\n"
                f"• 📊 ملاحظة: البيانات الدائمة لم يتم حذفها",
                parse_mode='Markdown'
            )
            
        elif call.data == "admin_back":
            bot.send_message(call.message.chat.id, "العودة إلى القائمة الإدارية", reply_markup=create_admin_keyboard())
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"خطأ في معالجة الاستجابة: {str(e)}")
        handle_bot_error(call.message.chat.id, str(e))

@global_error_handler
def process_setting_change(message, setting_key):
    try:
        new_value = message.text.strip()
        
        if not new_value.isdigit():
            bot.send_message(message.chat.id, "❌ يجب أن تكون القيمة رقمية")
            return
        
        redemption_logger.set_setting(setting_key, new_value)
        bot.send_message(message.chat.id, f"✅ تم تحديث الإعداد بنجاح\n{setting_key}: {new_value}", reply_markup=create_admin_keyboard())
        
    except Exception as e:
        logger.error(f"خطأ في تغيير الإعداد: {str(e)}")
        handle_bot_error(message.chat.id, str(e))

@global_error_handler
def handle_all_messages(message):
    if hasattr(message, 'text') and message.text == "👨‍💻 لوحة التحكم" and message.from_user.id != ADMIN_USER_ID:
        bot.send_message(message.chat.id, "⛔ ليس لديك صلاحية الوصول إلى هذه الميزة",
                        reply_markup=create_main_keyboard(message.from_user.id))
        return
    
    redemption_logger.log_request(message.from_user.id, 'message')
    
    allowed, error_msg = rate_limit_check(message.from_user.id)
    if not allowed:
        bot.send_message(message.chat.id, error_msg)
        return
    
    text = message.text.strip()
    
    if text in ["🎁 استرداد كود", "📊 استرداداتي", "ℹ️ المساعدة", "👨‍💻 لوحة التحكم", "📈 الإحصائيات", "⚙️ الإعدادات", "📤 تصدير البيانات", "🧹 تنظيف البيانات", "📢 بث جماعي", "🔙 القائمة الرئيسية"]:
        return
    
    valid_codes, skipped_codes = extract_and_filter_codes(text)
    
    if not send_initial_filter_report(message, valid_codes, skipped_codes):
        return
    
    if valid_codes:
        if len(valid_codes) == 1:
            add_to_task_queue({
                'type': 'single_code',
                'message': message,
                'code': valid_codes[0]
            })
            
            bot.send_message(message.chat.id, 
                            f"✅ تمت إضافة الكود إلى طابور المعالجة\n"
                            f"📋 الكود: `{valid_codes[0]}`",
                            parse_mode='Markdown')
        else:
            add_to_task_queue({
                'type': 'multiple_codes',
                'message': message,
                'codes': valid_codes
            })
            
            bot.send_message(message.chat.id, 
                            f"✅ تمت إضافة {len(valid_codes)} كود إلى طابور المعالجة\n"
                            f"⏳ جاري المعالجة...",
                            parse_mode='Markdown')

if hasattr(bot, 'message_handler'):
    bot.message_handler(commands=['start', 'help'])(send_welcome)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "ℹ️ المساعدة")(help_menu)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "📊 استرداداتي")(show_redemptions)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "🎁 استرداد كود")(ask_for_code)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "👨‍💻 لوحة التحكم" and message.from_user.id == ADMIN_USER_ID)(admin_panel)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "🔙 القائمة الرئيسية" and message.from_user.id == ADMIN_USER_ID)(admin_back_to_main)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "📈 الإحصائيات" and message.from_user.id == ADMIN_USER_ID)(admin_statistics)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "⚙️ الإعدادات" and message.from_user.id == ADMIN_USER_ID)(admin_settings)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "📤 تصدير البيانات" and message.from_user.id == ADMIN_USER_ID)(admin_export_data)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "🧹 تنظيف البيانات" and message.from_user.id == ADMIN_USER_ID)(admin_cleanup_data)
    bot.message_handler(func=lambda message: hasattr(message, 'text') and message.text == "📢 بث جماعي" and message.from_user.id == ADMIN_USER_ID)(admin_broadcast)
    bot.message_handler(func=lambda message: True)(handle_all_messages)

    if hasattr(bot, 'callback_query_handler'):
        bot.callback_query_handler(func=lambda call: True)(handle_callback_query)

def auto_cleanup():
    try:
        redemption_logger.cleanup_old_data()
        cache_system.clear_expired()
        logger.info("✅ تم التنظيف التلقائي بنجاح")
    except Exception as e:
        logger.error(f"❌ خطأ في التنظيف التلقائي: {str(e)}")
    finally:
        threading.Timer(24 * 60 * 60, auto_cleanup).start()

if __name__ == "__main__":
    logger.info("🚀 بدء تشغيل البوت...")
    
    threading.Timer(60, auto_cleanup).start()
    
    if not BOT_TOKEN or BOT_TOKEN == 'توكن_البوت_الخاص_بك':
        print("🔍 يعمل البوت في وضع الاختبار المحلي")
        print("💡 لاستخدام البوت الحقيقي، أضف BOT_TOKEN في ملف .env")
    else:
        print("🤖 بدء تشغيل البوت الحقيقي")
        while True:
            try:
                bot.polling(none_stop=True, timeout=120)
            except Exception as e:
                logger.error(f"❌ خطأ في تشغيل البوت: {e}")
                
                if ADMIN_USER_ID != 0:
                    try:
                        bot.send_message(ADMIN_USER_ID, 
                                       f"🔴 البوت توقف بسبب خطأ:\n{str(e)}",
                                       parse_mode='Markdown')
                    except:
                        pass
                
                logger.info("🔄 إعادة المحاولة بعد 15 ثانية...")
                time.sleep(15)