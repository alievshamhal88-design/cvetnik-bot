import sqlite3
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='data/database.sqlite'):
        # Создаем папку data, если её нет
        os.makedirs('data/photos', exist_ok=True)
        
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        # Основная таблица для фото (оставляем как есть)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id TEXT UNIQUE,
                file_path TEXT,
                posted INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                posted_at TIMESTAMP
            )
        ''')
        
        # Новая таблица для букетов (ваша база для выбора)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS bouquets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                description TEXT,
                photo_file_id TEXT UNIQUE NOT NULL,
                photo_path TEXT,
                price INTEGER DEFAULT 0,
                category TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица для дней рождения
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS birthdays (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                recipient_name TEXT NOT NULL,
                birth_date TEXT NOT NULL,  -- формат MM-DD
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица для подписок
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                recipient_name TEXT NOT NULL,
                recipient_phone TEXT,
                recipient_address TEXT,
                frequency TEXT NOT NULL,  -- 'weekly', 'monthly'
                custom_day INTEGER,
                budget INTEGER NOT NULL,
                auto_confirm INTEGER DEFAULT 0,
                active INTEGER DEFAULT 1,
                next_date TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        self.conn.commit()
        logger.info("✅ Все таблицы созданы")
    
    # ========== МЕТОДЫ ДЛЯ БУКЕТОВ ==========
    def add_bouquet(self, file_id, file_path, name=None, price=0, category=None):
        try:
            self.cursor.execute(
                'INSERT OR IGNORE INTO bouquets (photo_file_id, photo_path, name, price, category) VALUES (?, ?, ?, ?, ?)',
                (file_id, file_path, name, price, category)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления букета: {e}")
            return False
    
    def get_random_bouquet(self):
        self.cursor.execute('SELECT * FROM bouquets ORDER BY RANDOM() LIMIT 1')
        row = self.cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'name': row[1],
                'description': row[2],
                'photo_file_id': row[3],
                'photo_path': row[4],
                'price': row[5],
                'category': row[6]
            }
        return None
    
    def get_bouquets_by_category(self, category, limit=5):
        self.cursor.execute(
            'SELECT * FROM bouquets WHERE category = ? ORDER BY RANDOM() LIMIT ?',
            (category, limit)
        )
        rows = self.cursor.fetchall()
        return [{
            'id': r[0], 'name': r[1], 'description': r[2],
            'photo_file_id': r[3], 'photo_path': r[4],
            'price': r[5], 'category': r[6]
        } for r in rows]
    
    # ========== МЕТОДЫ ДЛЯ ДНЕЙ РОЖДЕНИЯ ==========
    def add_birthday(self, user_id, recipient_name, birth_date):
        try:
            self.cursor.execute(
                'INSERT INTO birthdays (user_id, recipient_name, birth_date) VALUES (?, ?, ?)',
                (user_id, recipient_name, birth_date)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления дня рождения: {e}")
            return False
    
    def get_birthdays_by_date(self, month_day):
        self.cursor.execute(
            'SELECT * FROM birthdays WHERE birth_date = ?',
            (month_day,)
        )
        rows = self.cursor.fetchall()
        return [{
            'id': r[0], 'user_id': r[1],
            'recipient_name': r[2], 'birth_date': r[3]
        } for r in rows]
    
    def get_user_birthdays(self, user_id):
        self.cursor.execute(
            'SELECT * FROM birthdays WHERE user_id = ?',
            (user_id,)
        )
        rows = self.cursor.fetchall()
        return [{
            'id': r[0], 'recipient_name': r[2],
            'birth_date': r[3]
        } for r in rows]
    
    # ========== МЕТОДЫ ДЛЯ ПОДПИСОК ==========
    def add_subscription(self, data):
        try:
            self.cursor.execute('''
                INSERT INTO subscriptions 
                (user_id, recipient_name, recipient_phone, recipient_address, 
                 frequency, custom_day, budget, auto_confirm, next_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['user_id'], data['recipient_name'], data['recipient_phone'],
                data['recipient_address'], data['frequency'], data.get('custom_day'),
                data['budget'], data['auto_confirm'], data['next_date']
            ))
            self.conn.commit()
            return self.cursor.lastrowid
        except Exception as e:
            logger.error(f"Ошибка добавления подписки: {e}")
            return None
    
    def get_active_subscriptions(self, date=None):
        query = 'SELECT * FROM subscriptions WHERE active = 1'
        params = []
        if date:
            query += ' AND next_date = ?'
            params.append(date)
        
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        return [{
            'id': r[0], 'user_id': r[1], 'recipient_name': r[2],
            'recipient_phone': r[3], 'recipient_address': r[4],
            'frequency': r[5], 'custom_day': r[6], 'budget': r[7],
            'auto_confirm': r[8], 'active': r[9], 'next_date': r[10]
        } for r in rows]
    
    def update_subscription_next_date(self, sub_id, next_date):
        self.cursor.execute(
            'UPDATE subscriptions SET next_date = ? WHERE id = ?',
            (next_date, sub_id)
        )
        self.conn.commit()
    
    # ========== СТАРЫЕ МЕТОДЫ (ДЛЯ ФОТО) ==========
    def add_photo(self, file_id, file_path):
        try:
            self.cursor.execute(
                'INSERT OR IGNORE INTO photos (file_id, file_path) VALUES (?, ?)',
                (file_id, file_path)
            )
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Ошибка добавления фото: {e}")
            return False
    
    def get_random_unposted_photo(self):
        self.cursor.execute(
            'SELECT id, file_id, file_path FROM photos WHERE posted = 0 ORDER BY RANDOM() LIMIT 1'
        )
        row = self.cursor.fetchone()
        if row:
            return {'id': row[0], 'file_id': row[1], 'file_path': row[2]}
        return None
    
    def mark_as_posted(self, photo_id):
        self.cursor.execute(
            'UPDATE photos SET posted = 1, posted_at = CURRENT_TIMESTAMP WHERE id = ?',
            (photo_id,)
        )
        self.conn.commit()
    
    def get_stats(self):
        self.cursor.execute('SELECT COUNT(*) FROM photos')
        total = self.cursor.fetchone()[0]
        self.cursor.execute('SELECT COUNT(*) FROM photos WHERE posted = 1')
        posted = self.cursor.fetchone()[0]
        return {'total': total, 'posted': posted, 'pending': total - posted}
    
    def reset_all_photos(self):
        self.cursor.execute('UPDATE photos SET posted = 0')
        self.conn.commit()
        logger.info("🔄 Все фото сброшены")
    
    def close(self):
        self.conn.close()
