#!/usr/bin/env python3
"""
БОТ «ГДЕ ПОДРАБОТКА?» — ВЕРСИЯ 4.0
- Правильная фильтрация (Фриланс = только удалёнка)
- Защита от дубликатов
- Поиск с Avito + hh.ru через прокси
- Компактное меню вакансий
- Кнопка «Подробнее» с полной информацией
- Источник вакансии всегда виден
"""
import asyncio
import json
import logging
import random
import re
import aiohttp
from datetime import datetime, timedelta
from typing import Dict, Any, List
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    PreCheckoutQuery, LabeledPrice, Message, CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8883834523:AAGEabtv8AZ84PrlEBYL4gNCo22WYQgcJ0U"
DEEPSEEK_API_KEY = "sk-5cdac197514c404ab7b10935fb2dc996"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
HH_API_URL = "https://api.hh.ru/vacancies"
ADMIN_ID = 1827360709
SUPPORT_USERNAME = "@rabotka_support"
BOT_USERNAME = "rabotka_239_bot"
PREMIUM_PRICE = 150
FREE_LIMIT = 3
REFERRAL_BONUS_DAYS = 1
RENDER_URL = "https://job-bot-v3.onrender.com"

PROXY_LIST = [
    "http://45.12.16.114:8080",
    "http://178.208.83.34:8080",
    "http://109.248.14.19:8080",
    "http://185.221.153.131:8080",
    "http://95.182.108.149:8080",
    "http://194.67.200.10:8080",
    "http://85.193.80.35:8080",
    "http://91.211.88.10:8080",
    "http://5.183.130.12:8080",
    "http://176.119.158.10:8080",
]

SCAM_GUIDE = """🛡 *Как не попасть на мошенников*
*1. Просят деньги* за доступ — развод.
*2. Обещают золотые горы* — реально 400-1500₽/смена.
*3. Нет контактов* — требуй телефон.
*4. Паспорт до собеседования* — не отправляй.
*5. Пишут первыми* — спам.
⚠️ Сомневаешься — позвони."""

SAMOZANYATOST_GUIDE = """📄 *Самозанятость с 14 лет*
Статус с налогом 4%. Приложение «Мой налог» → регистрация → согласие родителей.
Плюсы: официальный доход, стаж, работа с компаниями."""

TEMPLATES_GUIDE = """📝 *Шаблоны откликов*
*Avito:* «Здравствуйте! Заинтересовала вакансия. Мне 16 лет. Тел: [номер]»
*hh.ru:* «Добрый день! [Имя], 17 лет. Ищу подработку. Контакты: [тел]»
*Личное:* «Здравствуйте! Увидел объявление. Ответственный, пунктуальный. Тел: [номер]»"""

CATEGORY_NAMES = {
    "any": "Любая",
    "dog": "🐕 Выгул собак", "courier": "📦 Курьер", "promo": "📢 Промоутер",
    "freelance": "💻 Фриланс", "cleaning": "🧹 Уборка", "tutor": "🎓 Репетиторство"
}

CATEGORY_KEYWORDS = {
    "dog": ["выгул", "собак", "передержк", "животн"],
    "courier": ["курьер", "доставк", "заказа", "посылк"],
    "promo": ["промоутер", "раздач", "листовк", "расклейк", "дегустац"],
    "freelance": ["удалён", "онлайн", "отзыв", "модерат", "копирайт", "текст", "транскриб", "дизайн", "набор"],
    "cleaning": ["уборк", "клининг", "помощь по хозяйств"],
    "tutor": ["репетитор", "обучен", "преподав"],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
log = logging.getLogger("job_bot")

# ========== БАЗА ДАННЫХ ==========
class Database:
    def __init__(self, path: str = "jobs_db.json"):
        self.path = path
        self.users: Dict[int, Dict] = {}
        self.vacancies: List[Dict] = []
        self.ratings: Dict[str, Dict] = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.users = {int(k): v for k, v in data.get("users", {}).items()}
                self.vacancies = data.get("vacancies", [])
                self.ratings = data.get("ratings", {})
            log.info(f"База: {len(self.users)} пользователей, {len(self.vacancies)} вакансий")
        except:
            self.users = {}
            self.vacancies = []
            self.ratings = {}
            log.info("База пустая")

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"users": self.users, "vacancies": self.vacancies, "ratings": self.ratings}, f, ensure_ascii=False, indent=2)

    def get_user(self, uid: int) -> Dict:
        if uid not in self.users:
            self.users[uid] = {
                "city": None, "age_group": None, "job_type": "any", "category": "any",
                "paid": False, "paid_until": None, "daily_views": 0, "last_view_date": None,
                "favorites": [], "referral_code": None, "referred_by": None,
                "referral_count": 0, "notify": False, "joined": datetime.now().isoformat(), "_last_shown": []
            }
        return self.users[uid]

    def can_view(self, uid: int) -> bool:
        user = self.get_user(uid)
        if self.is_premium(uid): return True
        today = datetime.now().date().isoformat()
        if user["last_view_date"] != today:
            user["daily_views"] = 0
            user["last_view_date"] = today
            self.save()
        return user["daily_views"] < FREE_LIMIT

    def is_premium(self, uid: int) -> bool:
        user = self.get_user(uid)
        if user["paid"]: return True
        if user["paid_until"] and datetime.fromisoformat(user["paid_until"]) > datetime.now():
            return True
        return False

    def increment_views(self, uid: int):
        user = self.get_user(uid)
        user["daily_views"] += 1
        user["last_view_date"] = datetime.now().date().isoformat()
        self.save()

    def set_paid(self, uid: int, days: int = 365):
        user = self.get_user(uid)
        user["paid"] = True
        user["paid_until"] = (datetime.now() + timedelta(days=days)).isoformat()
        user["notify"] = True
        self.save()

    def add_premium_days(self, uid: int, days: int):
        user = self.get_user(uid)
        if user["paid_until"] and datetime.fromisoformat(user["paid_until"]) > datetime.now():
            current_end = datetime.fromisoformat(user["paid_until"])
            user["paid_until"] = (current_end + timedelta(days=days)).isoformat()
        else:
            user["paid_until"] = (datetime.now() + timedelta(days=days)).isoformat()
        user["notify"] = True
        self.save()

    def set_job_type(self, uid: int, job_type: str):
        self.get_user(uid)["job_type"] = job_type
        self.get_user(uid)["category"] = "any"
        self.save()

    def set_category(self, uid: int, category: str):
        self.get_user(uid)["category"] = category
        self.save()

    def set_city(self, uid: int, city: str):
        self.get_user(uid)["city"] = city
        self.save()

    def set_age(self, uid: int, age: str):
        self.get_user(uid)["age_group"] = age
        self.save()

    def reset_user(self, uid: int):
        user = self.get_user(uid)
        user["daily_views"] = 0
        user["paid"] = True
        user["paid_until"] = (datetime.now() + timedelta(days=365)).isoformat()
        user["city"] = "Москва"
        user["age_group"] = "16-17"
        user["job_type"] = "any"
        user["category"] = "any"
        self.save()

    def generate_referral_code(self, uid: int) -> str:
        user = self.get_user(uid)
        if not user["referral_code"]:
            user["referral_code"] = f"ref{uid}"
            self.save()
        return user["referral_code"]

    def process_referral(self, uid: int, code: str) -> bool:
        if code == f"ref{uid}": return False
        for u_id, u in self.users.items():
            if u.get("referral_code") == code:
                u["referral_count"] = u.get("referral_count", 0) + 1
                self.get_user(uid)["referred_by"] = u_id
                self.add_premium_days(u_id, REFERRAL_BONUS_DAYS)
                self.add_premium_days(uid, REFERRAL_BONUS_DAYS)
                self.save()
                return True
        return False

    def add_favorite(self, uid: int, vacancy: Dict):
        user = self.get_user(uid)
        if len(user["favorites"]) < 20:
            user["favorites"].append(vacancy)
            self.save()
            return True
        return False

    def get_favorites(self, uid: int) -> List[Dict]:
        return self.get_user(uid)["favorites"]

    def rate_employer(self, contact: str, rating: int):
        if contact not in self.ratings:
            self.ratings[contact] = {"up": 0, "down": 0}
        if rating == 1:
            self.ratings[contact]["up"] += 1
        else:
            self.ratings[contact]["down"] += 1
        self.save()

    def get_employer_rating(self, contact: str) -> str:
        r = self.ratings.get(contact, {"up": 0, "down": 0})
        total = r["up"] + r["down"]
        if total == 0: return "⭐ Нет оценок"
        score = r["up"] - r["down"]
        if score >= 3: return f"⭐ Надёжный ({r['up']}👍/{r['down']}👎)"
        if score <= -2: return f"⚠️ Много жалоб ({r['up']}👍/{r['down']}👎)"
        return f"⭐ Нормальный ({r['up']}👍/{r['down']}👎)"

    def get_vacancies(self, city: str, age_group: str, job_type: str = "any", category: str = "any") -> List[Dict]:
        city_lower = city.lower().strip()
        results = []
        for v in self.vacancies:
            v_city = v.get("city", "").lower()
            v_job_type = v.get("job_type", "active")
            v_cat = v.get("category", "any")
            # Проверка города
            if not (city_lower in v_city or v_city in city_lower or v_city == "вся россия"):
                continue
            # Проверка возраста
            if age_group not in v.get("age_groups", ["14-15", "16-17", "18+"]):
                continue
            # Проверка типа (удалёнка/активная)
            if job_type != "any" and job_type != v_job_type:
                continue
            # Проверка категории
            if category != "any" and category != v_cat:
                continue
            results.append(v)
        return results

    def add_vacancy(self, vacancy: Dict):
        for v in self.vacancies:
            if (v.get("title") == vacancy.get("title") and 
                v.get("city") == vacancy.get("city") and
                v.get("contact") == vacancy.get("contact")):
                return
        self.vacancies.append(vacancy)
        self.save()

    def stats(self):
        total = len(self.users)
        paid = sum(1 for uid in self.users if self.is_premium(uid))
        cities = {}
        for u in self.users.values():
            c = u.get("city", "Не указан")
            cities[c] = cities.get(c, 0) + 1
        return total, paid, len(self.vacancies), cities

db = Database()

# ========== ФУНКЦИИ ==========
def classify_category(title: str) -> str:
    t = title.lower()
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in t: return cat
    return "promo"

def classify_job_type(title: str) -> str:
    t = title.lower()
    for w in ["удалён", "онлайн", "отзыв", "модерат", "копирайт", "текст", "транскриб", "дизайн", "набор текст"]:
        if w in t: return "online"
    return "active"

def seed_vacancies():
    if len(db.vacancies) > 0:
        return
    jobs = [
        # МОСКВА - АКТИВНАЯ
        {"title":"Раздача листовок у метро Кузнецкий мост","description":"Раздача рекламных листовок. 4 часа в день. Можно без опыта. Оплата сразу после смены.","payment":"500 руб./смена","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"promo","contact":"📞 +7 (495) 123-45-67\n📱 WhatsApp: +7 (926) 111-22-33","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Курьер на велосипеде/самокате","description":"Доставка еды из ресторанов. Свободный график. Ежедневные выплаты на карту.","payment":"3000 руб./день","city":"Москва","age_groups":["16-17","18+"],"job_type":"active","category":"courier","contact":"📞 +7 (495) 222-33-44\n🔗 https://clck.ru/courier_msk","source":"Яндекс.Еда","date_added":datetime.now().isoformat()},
        {"title":"Выгул собак в центре","description":"Выгул двух собак в районе Хамовники. Утром и вечером по 30 минут.","payment":"500 руб./выгул","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"dog","contact":"📞 +7 (916) 444-55-66","source":"Частное лицо","date_added":datetime.now().isoformat()},
        {"title":"Расклейка объявлений на подъездах","description":"Расклейка в ЦАО. Оплата за каждую доску. Материалы выдают.","payment":"1500 руб./100 шт","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"promo","contact":"📞 +7 (903) 777-88-99","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Уборка квартир","description":"Поддерживающая уборка в центре. 2-3 часа. Инвентарь предоставляется.","payment":"1200 руб./уборка","city":"Москва","age_groups":["16-17","18+"],"job_type":"active","category":"cleaning","contact":"📞 +7 (495) 777-88-99","source":"Клининг-сервис","date_added":datetime.now().isoformat()},
        # МОСКВА - УДАЛЁНКА
        {"title":"Написание отзывов на маркетплейсах","description":"Писать отзывы на WB, Ozon. Удалённо. Бесплатное обучение.","payment":"100 руб./отзыв","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"online","category":"freelance","contact":"📱 @otzyvy_bot\n🔗 https://t.me/otzyvy_bot","source":"Маркетплейсы","date_added":datetime.now().isoformat()},
        {"title":"Модератор чата интернет-магазина","description":"Следить за порядком в чате, отвечать на вопросы. Удалённо. 2-3 часа в день.","payment":"8000 руб./мес","city":"Москва","age_groups":["16-17","18+"],"job_type":"online","category":"freelance","contact":"📧 hr@fashionshop.ru\n📞 +7 (495) 333-55-66","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Копирайтинг для соцсетей","description":"Написание постов для Instagram/Telegram. Темы: мода, игры, кино.","payment":"300 руб./пост","city":"Москва","age_groups":["16-17","18+"],"job_type":"online","category":"freelance","contact":"📧 smm@content.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        {"title":"Репетитор по математике онлайн","description":"Помощь с домашним заданием 5-7 класс. Онлайн, вечером.","payment":"500 руб./час","city":"Москва","age_groups":["16-17","18+"],"job_type":"online","category":"tutor","contact":"📞 +7 (916) 123-45-67","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        # САНКТ-ПЕТЕРБУРГ
        {"title":"Промоутер в ТЦ Галерея","description":"Раздача образцов кофе. 3 часа в день. Обучение на месте.","payment":"1200 руб./смена","city":"Санкт-Петербург","age_groups":["16-17","18+"],"job_type":"active","category":"promo","contact":"📞 +7 (812) 111-22-33","source":"Рекламное агентство","date_added":datetime.now().isoformat()},
        {"title":"Курьер на самокате","description":"Доставка посылок по центру. Самокат предоставляется.","payment":"2000 руб./день","city":"Санкт-Петербург","age_groups":["16-17","18+"],"job_type":"active","category":"courier","contact":"📞 +7 (812) 444-55-66","source":"Достависта","date_added":datetime.now().isoformat()},
        {"title":"Онлайн-консультант в чат","description":"Поддержка клиентов интернет-магазина. Удалённо. Обучение.","payment":"15000 руб./мес","city":"Санкт-Петербург","age_groups":["16-17","18+"],"job_type":"online","category":"freelance","contact":"📧 job@spb-shop.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        # КАЗАНЬ
        {"title":"Раздача листовок на Баумана","description":"Раздача на пешеходной улице. 3-4 часа.","payment":"400 руб./смена","city":"Казань","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"promo","contact":"📞 +7 (843) 222-33-44","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Промоутер в ТЦ Кольцо","description":"Дегустация напитков в выходные.","payment":"1000 руб./смена","city":"Казань","age_groups":["16-17","18+"],"job_type":"active","category":"promo","contact":"📞 +7 (917) 555-66-77","source":"Рекламное агентство","date_added":datetime.now().isoformat()},
        # ЕКАТЕРИНБУРГ
        {"title":"Курьер на самокате","description":"Доставка посылок.","payment":"2000 руб./день","city":"Екатеринбург","age_groups":["16-17","18+"],"job_type":"active","category":"courier","contact":"📞 +7 (343) 111-22-33","source":"Достависта","date_added":datetime.now().isoformat()},
        {"title":"Написание отзывов удалённо","description":"Писать отзывы на WB/Ozon.","payment":"100 руб./отзыв","city":"Екатеринбург","age_groups":["14-15","16-17","18+"],"job_type":"online","category":"freelance","contact":"📱 @otzyvy_ekb","source":"Маркетплейсы","date_added":datetime.now().isoformat()},
        # НОВОСИБИРСК
        {"title":"Расклейка объявлений","description":"Расклейка в центре.","payment":"1000 руб.","city":"Новосибирск","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"promo","contact":"📞 +7 (383) 222-33-44","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Модератор чата удалённо","description":"Следить за чатом. 3 часа в день.","payment":"7000 руб./мес","city":"Новосибирск","age_groups":["16-17","18+"],"job_type":"online","category":"freelance","contact":"📧 hr@nsk-shop.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        # НИЖНИЙ НОВГОРОД
        {"title":"Выгул собак на набережной","description":"Выгул утром и вечером.","payment":"400 руб./выгул","city":"Нижний Новгород","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"dog","contact":"📞 +7 (831) 111-22-33","source":"Частное лицо","date_added":datetime.now().isoformat()},
        # ПАВЛОВСК
        {"title":"Помощь по хозяйству","description":"Уборка территории, помощь на участке.","payment":"800 руб.","city":"Павловск","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"cleaning","contact":"📞 +7 (47362) 2-34-56\n📱 WhatsApp: +7 (920) 111-22-33","source":"Частное лицо","date_added":datetime.now().isoformat()},
        {"title":"Выгул собак в центре Павловска","description":"Ул. Советская. 2 раза в день.","payment":"300 руб./выгул","city":"Павловск","age_groups":["14-15","16-17","18+"],"job_type":"active","category":"dog","contact":"📞 +7 (920) 444-55-66","source":"Частное лицо","date_added":datetime.now().isoformat()},
        {"title":"Написание отзывов удалённо","description":"Писать отзывы на WB/Ozon.","payment":"100 руб./отзыв","city":"Павловск","age_groups":["14-15","16-17","18+"],"job_type":"online","category":"freelance","contact":"📱 @otzyvy_bot","source":"Маркетплейсы","date_added":datetime.now().isoformat()},
        # ВСЯ РОССИЯ - УДАЛЁНКА
        {"title":"Транскрибация аудио в текст","description":"Расшифровка аудиозаписей. Удалённо. Подходит новичкам.","payment":"200 руб./час","city":"Вся Россия","age_groups":["14-15","16-17","18+"],"job_type":"online","category":"freelance","contact":"📧 transcribe@work.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        {"title":"Дизайн аватарок для соцсетей","description":"Создание аватарок на заказ. Можно без опыта.","payment":"200 руб./шт","city":"Вся Россия","age_groups":["14-15","16-17","18+"],"job_type":"online","category":"freelance","contact":"📱 @design_bot","source":"Фриланс","date_added":datetime.now().isoformat()},
        {"title":"Набор текста со сканов","description":"Набор текста с фотографий. Удалённо.","payment":"150 руб./1000 знаков","city":"Вся Россия","age_groups":["14-15","16-17","18+"],"job_type":"online","category":"freelance","contact":"📧 text@job.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
    ]
    for j in jobs:
        db.add_vacancy(j)
    db.save()
    log.info(f"Добавлено {len(jobs)} стартовых вакансий")

def get_proxy():
    return random.choice(PROXY_LIST) if PROXY_LIST else None

async def parse_avito(city: str, pages: int = 2) -> List[Dict]:
    vacancies = []
    city_domains = {
        "москва":"moskva","санкт-петербург":"sankt-peterburg","спб":"sankt-peterburg",
        "казань":"kazan","екатеринбург":"ekaterinburg","новосибирск":"novosibirsk",
        "краснодар":"krasnodar","ростов-на-дону":"rostov-na-donu",
        "нижний новгород":"nizhniy_novgorod","челябинск":"chelyabinsk",
        "самара":"samara","уфа":"ufa","омск":"omsk","пермь":"perm",
        "воронеж":"voronezh","волгоград":"volgograd","красноярск":"krasnoyarsk",
    }
    domain = city_domains.get(city.lower().strip(), city.lower().strip().replace(" ","_"))
    keywords = ["подработка+с+14+лет","работа+для+школьников","промоутер","курьер+с+16"]
    headers_list = [
        {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
        {"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36"},
    ]
    for keyword in keywords[:2]:
        for page in range(1, pages+1):
            url = f"https://www.avito.ru/{domain}?q={keyword}&p={page}"
            headers = random.choice(headers_list)
            proxy = get_proxy()
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, headers=headers, proxy=proxy, timeout=25) as r:
                        if r.status != 200: continue
                        html = await r.text()
                soup = BeautifulSoup(html, "html.parser")
                items = soup.find_all("div", {"data-marker":"item"})
                for item in items[:3]:
                    try:
                        t_e = item.find("h3",{"itemprop":"name"})
                        p_e = item.find("meta",{"itemprop":"price"})
                        l_e = item.find("a",{"data-marker":"item-title"})
                        title = t_e.text.strip() if t_e else "Без названия"
                        price = p_e.get("content","Не указана") if p_e else "Не указана"
                        link = "https://www.avito.ru"+l_e.get("href","") if l_e else url
                        if any(w in title.lower() for w in ["14","15","16","17","школьник","студент","подработк","промоутер","курьер","раздач","расклейк"]):
                            vacancies.append({
                                "title":title,"description":f"Вакансия с Avito: {title}",
                                "payment":f"{price} руб." if price!="Не указана" else "Договорная",
                                "city":city,"age_groups":["14-15","16-17","18+"],
                                "job_type":classify_job_type(title),"category":classify_category(title),
                                "contact":f"🔗 {link}",
                                "source":"Avito","date_added":datetime.now().isoformat()
                            })
                    except: continue
                await asyncio.sleep(random.uniform(3,8))
            except: continue
    log.info(f"Avito: найдено {len(vacancies)} для {city}")
    return vacancies

async def parse_hh(city_name: str, city_code: int = 1) -> List[Dict]:
    vacancies = []
    params = {"text":"подработка OR школьник OR студент OR без опыта OR промоутер OR курьер","area":city_code,"experience":"noExperience","employment":"part","per_page":10,"page":0,"period":7}
    proxy = get_proxy()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(HH_API_URL, params=params, proxy=proxy, timeout=20) as r:
                if r.status != 200: return []
                data = await r.json()
        for item in data.get("items",[]):
            try:
                title = item.get("name","Без названия")
                employer = item.get("employer",{}).get("name","Не указан")
                salary = item.get("salary")
                payment = f"{salary.get('from','?')}-{salary.get('to','?')}{salary.get('currency','руб.')}" if salary else "Не указана"
                url = item.get("alternate_url","")
                resp_text = item.get("snippet",{}).get("responsibility","") or ""
                resp_text = re.sub(r'<[^>]+>','',resp_text)
                vacancies.append({
                    "title":title,"description":f"{employer}. {resp_text[:200]}...",
                    "payment":payment,"city":city_name,"age_groups":["16-17","18+"],
                    "job_type":classify_job_type(title),"category":classify_category(title),
                    "contact":f"🔗 {url}",
                    "source":"hh.ru","date_added":datetime.now().isoformat()
                })
            except: continue
    except: pass
    log.info(f"hh.ru: найдено {len(vacancies)} для {city_name}")
    return vacancies

async def background_parsing():
    cities = ["Москва","Санкт-Петербург","Казань","Екатеринбург","Новосибирск","Краснодар","Нижний Новгород","Челябинск","Самара","Уфа","Омск","Волгоград","Воронеж","Красноярск","Пермь","Ростов-на-Дону"]
    codes = {"Москва":1,"Санкт-Петербург":2,"Казань":88,"Екатеринбург":3,"Новосибирск":4,"Краснодар":53,"Нижний Новгород":66,"Челябинск":104,"Самара":78,"Уфа":99,"Омск":68,"Волгоград":40,"Воронеж":26,"Красноярск":54,"Пермь":72,"Ростов-на-Дону":76}
    while True:
        log.info("Парсинг запущен")
        for city in cities[:5]:
            try:
                for v in await parse_avito(city,1): db.add_vacancy(v)
            except Exception as e: log.error(f"Avito {city}: {e}")
            try:
                for v in await parse_hh(city, codes.get(city,1)): db.add_vacancy(v)
            except Exception as e: log.error(f"hh {city}: {e}")
            await asyncio.sleep(3)
        db.vacancies = [v for v in db.vacancies if datetime.fromisoformat(v["date_added"]) > datetime.now()-timedelta(days=14)]
        if len(db.vacancies) > 500: db.vacancies = db.vacancies[-500:]
        db.save()
        log.info(f"Парсинг завершён. Вакансий: {len(db.vacancies)}")
        await asyncio.sleep(30*60)

async def daily_notifications(bot: Bot):
    while True:
        await asyncio.sleep(60)
        now = datetime.now()
        if now.hour == 10 and now.minute == 0:
            for uid, u in db.users.items():
                if db.is_premium(uid) and u.get("notify") and u.get("city"):
                    vacs = db.get_vacancies(u["city"], u.get("age_group","16-17"), u.get("job_type","any"), u.get("category","any"))
                    if vacs:
                        try:
                            await bot.send_message(uid, f"🔔 *Новые вакансии в {u['city']}!*\nСегодня {len(vacs)} предложений по твоему фильтру.\nЖми /start.", parse_mode="Markdown")
                        except: pass
            await asyncio.sleep(60)

async def keep_alive():
    await asyncio.sleep(60)
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(RENDER_URL, timeout=10) as r:
                    log.info(f"Ping: {r.status}")
        except: pass
        await asyncio.sleep(300)

class Onboarding(StatesGroup):
    city = State()
    age = State()
    job_type = State()
    category = State()

# ========== КЛАВИАТУРЫ ==========
def main_menu(is_premium: bool = False) -> InlineKeyboardMarkup:
    btns = [
        [InlineKeyboardButton(text="💰 Смотреть вакансии", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="🔧 Тип работы", callback_data="change_job_type")],
        [InlineKeyboardButton(text="📂 Категория", callback_data="change_category")],
        [InlineKeyboardButton(text="👤 Возраст", callback_data="change_age")],
        [InlineKeyboardButton(text="📍 Город", callback_data="change_city")],
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="show_favorites")],
        [InlineKeyboardButton(text="👥 Рефералка", callback_data="referral_info")],
        [InlineKeyboardButton(text="📞 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME.replace('@','')}")],
    ]
    if not is_premium:
        btns.insert(-3, [InlineKeyboardButton(text="💎 Премиум (149₽)", callback_data="premium_info")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Любая", callback_data="jobtype_any")],
        [InlineKeyboardButton(text="💻 Удалёнка", callback_data="jobtype_online")],
        [InlineKeyboardButton(text="🏃 Активная", callback_data="jobtype_active")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="main")],
    ])

def category_keyboard(job_type: str = "any") -> InlineKeyboardMarkup:
    if job_type == "online":
        cats = [("💰 Любая", "any"), ("💻 Фриланс", "freelance"), ("🎓 Репетиторство", "tutor")]
    elif job_type == "active":
        cats = [("💰 Любая", "any"), ("🐕 Выгул собак", "dog"), ("📦 Курьер", "courier"), ("📢 Промоутер", "promo"), ("🧹 Уборка", "cleaning")]
    else:
        cats = [("💰 Любая", "any"), ("🐕 Выгул собак", "dog"), ("📦 Курьер", "courier"), ("📢 Промоутер", "promo"), ("💻 Фриланс", "freelance"), ("🧹 Уборка", "cleaning"), ("🎓 Репетиторство", "tutor")]
    kb = [[InlineKeyboardButton(text=label, callback_data=f"cat_{cb}")] for label, cb in cats]
    kb.append([InlineKeyboardButton(text="⬅ Назад", callback_data="main")])
    return InlineKeyboardMarkup(inline_keyboard=kb)

def age_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="14-15", callback_data="setage_14-15")],
        [InlineKeyboardButton(text="16-17", callback_data="setage_16-17")],
        [InlineKeyboardButton(text="18+", callback_data="setage_18+")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="main")],
    ])

# ========== ОБРАБОТЧИКИ ==========
async def cmd_start(message: Message, state: FSMContext):
    u = db.get_user(message.from_user.id)
    args = message.text.split()
    if len(args) > 1:
        code = args[1]
        if db.process_referral(message.from_user.id, code):
            await message.answer(f"🎉 *Реферальный код активирован!*\nВы получили +{REFERRAL_BONUS_DAYS} день Премиума!", parse_mode="Markdown")
    if not u["city"]:
        await message.answer("👋 *Привет!*\nВ каком городе ищешь работу?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Москва", callback_data="setcity_Москва")],
            [InlineKeyboardButton(text="СПб", callback_data="setcity_Санкт-Петербург")],
            [InlineKeyboardButton(text="Другой город", callback_data="setcity_other")],
        ]), parse_mode="Markdown")
        await state.set_state(Onboarding.city)
    else:
        prem = db.is_premium(message.from_user.id)
        v = "∞" if prem else str(max(0, FREE_LIMIT - u["daily_views"]))
        await message.answer(f"👋 *Меню*\n📍 {u['city']} | 👤 {u['age_group']}\n📂 {CATEGORY_NAMES.get(u.get('category','any'))}\n💎 {'Премиум' if prem else 'Бесплатно ('+v+' сегодня)'}", reply_markup=main_menu(prem), parse_mode="Markdown")

async def set_city(call: CallbackQuery, state: FSMContext):
    city = call.data.replace("setcity_","")
    if city == "other":
        await call.message.edit_text("📍 Напиши название города:", parse_mode="Markdown")
        await state.set_state(Onboarding.city)
        return
    db.set_city(call.from_user.id, city)
    await call.message.edit_text(f"📍 *{city}*\nУкажи возраст:", reply_markup=age_keyboard(), parse_mode="Markdown")
    await state.set_state(Onboarding.age)

async def process_city(message: Message, state: FSMContext):
    db.set_city(message.from_user.id, message.text.strip())
    await message.answer(f"📍 *{message.text}*\nУкажи возраст:", reply_markup=age_keyboard(), parse_mode="Markdown")
    await state.set_state(Onboarding.age)

async def set_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("setage_","")
    db.set_age(call.from_user.id, age)
    await call.message.edit_text(f"✅ *Возраст: {age}*\nВыбери тип работы:", reply_markup=job_type_keyboard(), parse_mode="Markdown")
    await state.set_state(Onboarding.job_type)

async def set_job_type(call: CallbackQuery, state: FSMContext):
    jt = call.data.replace("jobtype_","")
    db.set_job_type(call.from_user.id, jt)
    await call.message.edit_text(f"✅ *Тип: {CATEGORY_NAMES.get(jt)}*\nВыбери категорию:", reply_markup=category_keyboard(jt), parse_mode="Markdown")
    await state.set_state(Onboarding.category)

async def set_category(call: CallbackQuery, state: FSMContext):
    cat = call.data.replace("cat_","")
    db.set_category(call.from_user.id, cat)
    await call.message.edit_text(f"✅ *Готово!*\nКатегория: *{CATEGORY_NAMES.get(cat)}*\nЖми «Смотреть вакансии»", reply_markup=main_menu(db.is_premium(call.from_user.id)), parse_mode="Markdown")
    await state.clear()

async def change_job_type(call: CallbackQuery):
    await call.message.edit_text("🔧 *Тип работы:*", reply_markup=job_type_keyboard(), parse_mode="Markdown")

async def change_category(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    await call.message.edit_text("📂 *Категория:*", reply_markup=category_keyboard(u.get("job_type","any")), parse_mode="Markdown")

async def change_age(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("👤 *Возраст:*", reply_markup=age_keyboard(), parse_mode="Markdown")
    await state.set_state(Onboarding.age)

async def show_vacancies(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    if not u["city"]:
        await call.message.edit_text("Сначала /start", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]))
        return
    if not db.can_view(call.from_user.id):
        await call.message.edit_text("🚫 *Лимит.*\n💎 Премиум — безлимит за 149 руб.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить", callback_data="buy_premium")],
            [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
        ]), parse_mode="Markdown")
        return
    vacs = db.get_vacancies(u.get("city","Москва"), u.get("age_group","16-17"), u.get("job_type","any"), u.get("category","any"))
    if not vacs:
        await call.message.edit_text("😔 Нет вакансий. Смени фильтры.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔧 Сменить", callback_data="main")]]), parse_mode="Markdown")
        return
    db.increment_views(call.from_user.id)
    random.shuffle(vacs)
    to_show = vacs[:3]
    db.get_user(call.from_user.id)["_last_shown"] = to_show
    db.save()
    
    # Компактный вывод
    resp = f"💰 *Вакансии в {u.get('city')}*\n📂 {CATEGORY_NAMES.get(u.get('category','any'))} | 👤 {u.get('age_group')}\n\n"
    for i, v in enumerate(to_show, 1):
        e = "💻" if v.get("job_type")=="online" else "🏃"
        resp += f"*{i}. {e} {v['title']}*\n💵 {v['payment']} | {v['source']}\n\n"
    v_left = max(0, FREE_LIMIT - u["daily_views"])
    resp += f"📊 Осталось: *{v_left if not db.is_premium(call.from_user.id) else '∞'}*\n"
    
    # Компактные кнопки
    kb = [
        [InlineKeyboardButton(text="🔄 Ещё вакансии", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="ℹ️ Подробнее #1", callback_data="detail_0"), InlineKeyboardButton(text="📞 #1", callback_data="contact_0")],
        [InlineKeyboardButton(text="ℹ️ Подробнее #2", callback_data="detail_1"), InlineKeyboardButton(text="📞 #2", callback_data="contact_1")],
        [InlineKeyboardButton(text="ℹ️ Подробнее #3", callback_data="detail_2"), InlineKeyboardButton(text="📞 #3", callback_data="contact_2")],
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="fav_menu"), InlineKeyboardButton(text="👍👎 Рейтинг", callback_data="rate_menu")],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")],
    ]
    await call.message.edit_text(resp, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown", disable_web_page_preview=True)

async def show_detail(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    to_show = u.get("_last_shown",[])
    idx = int(call.data.replace("detail_",""))
    if idx >= len(to_show): await call.answer("Нет такой"); return
    v = to_show[idx]
    rating = db.get_employer_rating(v.get("contact",""))
    resp = f"*{v['title']}*\n\n"
    resp += f"📝 *Описание:* {v['description']}\n\n"
    resp += f"💵 *Оплата:* {v['payment']}\n"
    resp += f"📍 *Город:* {v.get('city','Не указан')}\n"
    resp += f"👤 *Возраст:* {', '.join(v.get('age_groups',[]))}\n"
    resp += f"📂 *Тип:* {'Удалёнка' if v.get('job_type')=='online' else 'Активная'}\n"
    resp += f"🔹 *Источник:* {v.get('source','Не указан')}\n"
    resp += f"⭐ *Рейтинг:* {rating}\n\n"
    resp += f"📞 *Контакты:*\n{v.get('contact','Не указаны')}"
    await call.message.answer(resp, parse_mode="Markdown", disable_web_page_preview=True)
    await call.answer()

async def show_contact(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    to_show = u.get("_last_shown",[])
    idx = int(call.data.replace("contact_",""))
    if idx >= len(to_show): await call.answer("Нет такой"); return
    v = to_show[idx]
    rating = db.get_employer_rating(v.get("contact",""))
    await call.message.answer(f"📞 *{v['title']}*\n\n{v['contact']}\n\n⭐ {rating}", parse_mode="Markdown", disable_web_page_preview=True)
    await call.answer()

async def fav_menu(call: CallbackQuery):
    await call.message.edit_text("⭐ Выбери вакансию для избранного:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ #1", callback_data="fav_0"), InlineKeyboardButton(text="⭐ #2", callback_data="fav_1"), InlineKeyboardButton(text="⭐ #3", callback_data="fav_2")],
        [InlineKeyboardButton(text="⬅ Назад к вакансиям", callback_data="show_vacancies")],
    ]), parse_mode="Markdown")

async def rate_menu(call: CallbackQuery):
    await call.message.edit_text("👍👎 Оцени работодателя:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 #1", callback_data="rateup_0"), InlineKeyboardButton(text="👎 #1", callback_data="ratedown_0")],
        [InlineKeyboardButton(text="👍 #2", callback_data="rateup_1"), InlineKeyboardButton(text="👎 #2", callback_data="ratedown_1")],
        [InlineKeyboardButton(text="👍 #3", callback_data="rateup_2"), InlineKeyboardButton(text="👎 #3", callback_data="ratedown_2")],
        [InlineKeyboardButton(text="⬅ Назад к вакансиям", callback_data="show_vacancies")],
    ]), parse_mode="Markdown")

async def rate_employer(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    to_show = u.get("_last_shown",[])
    if "rateup_" in call.data:
        idx = int(call.data.replace("rateup_",""))
        rating = 1
    else:
        idx = int(call.data.replace("ratedown_",""))
        rating = -1
    if idx >= len(to_show): await call.answer("Нет такой"); return
    v = to_show[idx]
    db.rate_employer(v.get("contact",""), rating)
    await call.answer("✅ Спасибо за оценку!")

async def add_favorite(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    to_show = u.get("_last_shown",[])
    idx = int(call.data.replace("fav_",""))
    if idx >= len(to_show): await call.answer("Нет такой"); return
    if db.add_favorite(call.from_user.id, to_show[idx]):
        await call.answer("⭐ Добавлено в избранное!")
    else:
        await call.answer("🚫 Избранное заполнено (макс 20)")

async def show_favorites(call: CallbackQuery):
    favs = db.get_favorites(call.from_user.id)
    if not favs:
        await call.message.edit_text("⭐ Избранное пусто.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]), parse_mode="Markdown")
        return
    resp = "⭐ *Избранное:*\n\n"
    for i, v in enumerate(favs, 1):
        resp += f"*{i}. {v['title']}*\n💵 {v['payment']} | {v.get('source','?')}\n\n"
    await call.message.edit_text(resp, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]), parse_mode="Markdown", disable_web_page_preview=True)

async def referral_info(call: CallbackQuery):
    code = db.generate_referral_code(call.from_user.id)
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    u = db.get_user(call.from_user.id)
    resp = f"👥 *Реферальная система*\n\nПриведи друга — получите по *{REFERRAL_BONUS_DAYS} дню Премиума*!\n\nТвоя ссылка:\n`{link}`\n\nПриглашено: *{u.get('referral_count',0)}* чел."
    await call.message.edit_text(resp, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться ссылкой", switch_inline_query=link)],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
    ]), parse_mode="Markdown", disable_web_page_preview=True)

async def premium_info(call: CallbackQuery):
    await call.message.edit_text(f"💎 *Премиум*\nБезлимит, избранное, уведомления, гайды.\n💰 {PREMIUM_PRICE}⭐ (~149 руб.)\nНавсегда.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💎 Купить ({PREMIUM_PRICE}⭐)", callback_data="buy_premium")],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
    ]), parse_mode="Markdown")

async def buy_premium(call: CallbackQuery):
    await bot.send_invoice(chat_id=call.from_user.id, title="Премиум", description="Безлимит навсегда", payload="prem", provider_token="", currency="XTR", prices=[LabeledPrice(label="Доступ", amount=PREMIUM_PRICE)], start_parameter="prem")

async def pre_checkout(pq: PreCheckoutQuery): await pq.answer(ok=True)

async def payment_success(message: Message):
    db.set_paid(message.from_user.id)
    await message.answer("💎 *Оплата прошла!* Вот твои гайды:", parse_mode="Markdown")
    await message.answer(SCAM_GUIDE, parse_mode="Markdown")
    await message.answer(SAMOZANYATOST_GUIDE, parse_mode="Markdown")
    await message.answer(TEMPLATES_GUIDE, parse_mode="Markdown")
    await message.answer("✅ *Готово!* Безлимит активен.", reply_markup=main_menu(True), parse_mode="Markdown")

async def guides_cmd(message: Message):
    await message.answer(SCAM_GUIDE, parse_mode="Markdown")
    await message.answer(SAMOZANYATOST_GUIDE, parse_mode="Markdown")
    await message.answer(TEMPLATES_GUIDE, parse_mode="Markdown")

async def change_city(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📍 Новый город:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Отмена", callback_data="main")]]), parse_mode="Markdown")
    await state.set_state(Onboarding.city)

async def main_handler(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    prem = db.is_premium(call.from_user.id)
    v = "∞" if prem else str(max(0, FREE_LIMIT - u["daily_views"]))
    await call.message.edit_text(f"👋 *Меню*\n📍 {u.get('city','?')} | 👤 {u.get('age_group','?')}\n📂 {CATEGORY_NAMES.get(u.get('category','any'))}\n💎 {'Премиум' if prem else 'Бесплатно ('+v+' сегодня)'}", reply_markup=main_menu(prem), parse_mode="Markdown")

async def stats_cmd(message: Message):
    if message.from_user.id == ADMIN_ID:
        t, p, v, cities = db.stats()
        resp = f"👥 Пользователей: {t}\n💎 Платных: {p}\n📋 Вакансий: {v}\n⭐ Звёзд: ~{p*PREMIUM_PRICE}\n\n📍 По городам:\n"
        for city, count in sorted(cities.items(), key=lambda x: -x[1])[:10]:
            resp += f"  {city}: {count}\n"
        await message.answer(resp)

async def reset_cmd(message: Message):
    if message.from_user.id == ADMIN_ID:
        db.reset_user(message.from_user.id)
        await message.answer("✅ Сброшено: Москва, 16-17, Любая, Премиум.")

async def main():
    log.info("БОТ ЗАПУСКАЕТСЯ")
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(stats_cmd, Command("stats"))
    dp.message.register(reset_cmd, Command("reset"))
    dp.message.register(guides_cmd, Command("guides"))
    dp.callback_query.register(set_city, F.data.startswith("setcity_"))
    dp.message.register(process_city, Onboarding.city)
    dp.callback_query.register(set_age, F.data.startswith("setage_"))
    dp.callback_query.register(set_job_type, F.data.startswith("jobtype_"))
    dp.callback_query.register(set_category, F.data.startswith("cat_"))
    dp.callback_query.register(change_job_type, F.data == "change_job_type")
    dp.callback_query.register(change_category, F.data == "change_category")
    dp.callback_query.register(change_age, F.data == "change_age")
    dp.callback_query.register(main_handler, F.data == "main")
    dp.callback_query.register(show_vacancies, F.data == "show_vacancies")
    dp.callback_query.register(show_detail, F.data.startswith("detail_"))
    dp.callback_query.register(show_contact, F.data.startswith("contact_"))
    dp.callback_query.register(rate_employer, F.data.startswith("rateup_"))
    dp.callback_query.register(rate_employer, F.data.startswith("ratedown_"))
    dp.callback_query.register(add_favorite, F.data.startswith("fav_"))
    dp.callback_query.register(fav_menu, F.data == "fav_menu")
    dp.callback_query.register(rate_menu, F.data == "rate_menu")
    dp.callback_query.register(show_favorites, F.data == "show_favorites")
    dp.callback_query.register(referral_info, F.data == "referral_info")
    dp.callback_query.register(change_city, F.data == "change_city")
    dp.callback_query.register(premium_info, F.data == "premium_info")
    dp.callback_query.register(buy_premium, F.data == "buy_premium")
    dp.pre_checkout_query.register(pre_checkout)
    dp.message.register(payment_success, F.successful_payment)
    global bot
    bot = Bot(token=BOT_TOKEN)
    seed_vacancies()
    asyncio.create_task(background_parsing())
    asyncio.create_task(keep_alive())
    asyncio.create_task(daily_notifications(bot))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
