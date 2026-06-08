#!/usr/bin/env python3
"""
БОТ «ГДЕ ПОДРАБОТКА?»
Агрегатор вакансий для подростков 14-17 лет
Парсинг Avito + hh.ru API
Монетизация: Telegram Stars
С выбором категорий работы
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

BOT_TOKEN = "8883834523:AAGEabtv8AZ84PrlEBYL4gNCo22WYQgcJ0U"
DEEPSEEK_API_KEY = "sk-5cdac197514c404ab7b10935fb2dc996"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
HH_API_URL = "https://api.hh.ru/vacancies"
ADMIN_ID = 1827360709
PREMIUM_PRICE = 150
FREE_LIMIT = 3

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
log = logging.getLogger("job_bot")

class Database:
    def __init__(self, path: str = "jobs_db.json"):
        self.path = path
        self.users: Dict[int, Dict] = {}
        self.vacancies: List[Dict] = []
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.users = {int(k): v for k, v in data.get("users", {}).items()}
                self.vacancies = data.get("vacancies", [])
            log.info(f"База загружена: {len(self.users)} пользователей, {len(self.vacancies)} вакансий")
        except (FileNotFoundError, json.JSONDecodeError):
            self.users = {}
            self.vacancies = []
            log.info("База создана (пустая)")

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"users": self.users, "vacancies": self.vacancies}, f, ensure_ascii=False, indent=2)

    def get_user(self, uid: int) -> Dict:
        if uid not in self.users:
            self.users[uid] = {
                "city": None,
                "age_group": None,
                "job_type": "any",
                "paid": False,
                "daily_views": 0,
                "last_view_date": None,
                "favorites": [],
                "joined": datetime.now().isoformat()
            }
        return self.users[uid]

    def can_view(self, uid: int) -> bool:
        user = self.get_user(uid)
        if user["paid"]:
            return True
        today = datetime.now().date().isoformat()
        if user["last_view_date"] != today:
            user["daily_views"] = 0
            user["last_view_date"] = today
            self.save()
        return user["daily_views"] < FREE_LIMIT

    def increment_views(self, uid: int):
        user = self.get_user(uid)
        user["daily_views"] += 1
        user["last_view_date"] = datetime.now().date().isoformat()
        self.save()

    def set_paid(self, uid: int):
        self.get_user(uid)["paid"] = True
        self.save()

    def set_job_type(self, uid: int, job_type: str):
        self.get_user(uid)["job_type"] = job_type
        self.save()

    def get_vacancies(self, city: str, age_group: str, job_type: str = "any") -> List[Dict]:
        city_lower = city.lower().strip()
        results = []
        for v in self.vacancies:
            v_city = v.get("city", "").lower()
            if city_lower in v_city or v_city in city_lower or city_lower == "вся россия":
                if age_group in v.get("age_groups", ["14-15", "16-17", "18+"]):
                    if job_type == "any":
                        results.append(v)
                    elif job_type == "online" and v.get("job_type") == "online":
                        results.append(v)
                    elif job_type == "active" and v.get("job_type") == "active":
                        results.append(v)
        return results

    def add_vacancy(self, vacancy: Dict):
        for v in self.vacancies:
            if v.get("title") == vacancy.get("title") and v.get("city") == vacancy.get("city"):
                return
        self.vacancies.append(vacancy)
        self.save()

    def stats(self):
        total = len(self.users)
        paid = sum(1 for u in self.users.values() if u.get("paid"))
        return total, paid, len(self.vacancies)

db = Database()

def seed_vacancies():
    if len(db.vacancies) > 0:
        return
    test_jobs = [
        {"title": "Раздача листовок у метро", "description": "Раздача листовок у метро Кузнецкий мост. Работа для школьников и студентов.", "payment": "500 руб.", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "WhatsApp: +79001234567", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ", "description": "Работа промоутером в ТЦ Авиапарк. Дегустации, раздача образцов.", "payment": "1200 руб.", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "Тел: +79007654321", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на велосипеде", "description": "Доставка еды из ресторанов. График свободный.", "payment": "3000 руб./день", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "Анкета: https://clck.ru/example", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Написание отзывов на маркетплейсах", "description": "Удалённая работа. Писать отзывы на Wildberries, Ozon.", "payment": "50-100 руб./отзыв", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "Бот в ТГ: @reviews_bot", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Модератор чата (удалённо)", "description": "Следить за порядком в чате интернет-магазина. 2-3 часа в день.", "payment": "8000 руб./мес", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "online", "contact": "Резюме: job@shop.ru", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Расклейка объявлений", "description": "Расклейка объявлений на досках у подъездов. Район ЦАО.", "payment": "1500 руб.", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "Telegram: @promo_job", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Выгул собак", "description": "Выгул собак в районе Хамовники. 2 раза в день.", "payment": "500 руб./выгул", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "ТГ: @dogwalker", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Копирайтинг для соцсетей", "description": "Написание постов для Instagram/TG. Темы: мода, игры.", "payment": "300 руб./пост", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "online", "contact": "Портфолио: smm@agency.ru", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Раздача листовок у метро", "description": "Раздача у метро Невский проспект.", "payment": "500 руб.", "city": "Санкт-Петербург", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "ТГ: @spb_job", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ Галерея", "description": "Дегустация соков в ТЦ Галерея.", "payment": "1000 руб.", "city": "Санкт-Петербург", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "+79991112233", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Раздача листовок", "description": "Раздача листовок на Баумана.", "payment": "400 руб.", "city": "Казань", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "ТГ: @kazan_rabota", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на самокате", "description": "Доставка посылок по городу.", "payment": "2000 руб./день", "city": "Екатеринбург", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "Анкета: https://ekb.dostavka.ru", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
        {"title": "Написание отзывов (удалённо)", "description": "Писать отзывы на маркетплейсы.", "payment": "50-100 руб./отзыв", "city": "Новосибирск", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "Бот: @reviews_nsk", "source": "Прямое размещение", "date_added": datetime.now().isoformat()},
    ]
    for job in test_jobs:
        db.vacancies.append(job)
    db.save()
    log.info(f"Добавлено {len(test_jobs)} тестовых вакансий")

async def ai_gen(system: str, user: str, temp: float = 0.8) -> str:
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temp,
        "max_tokens": 800
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30) as r:
                if r.status == 200:
                    return (await r.json())["choices"][0]["message"]["content"]
                log.error(f"AI API error {r.status}")
                return "Ошибка генерации."
    except Exception as e:
        log.error(f"AI exception: {e}")
        return "Сервис временно недоступен."

def classify_job_type(title: str) -> str:
    title_lower = title.lower()
    online_keywords = ["удалён", "удален", "онлайн", "фриланс", "копирайт", "текст", "отзыв", "написани", "модерат", "smm", "дизайн", "перевод", "набор текст", "телефон", "интернет", "чат", "поддержк", "контент"]
    active_keywords = ["курьер", "раздач", "расклей", "промоутер", "уборк", "склад", "грузчик", "выгул", "бегун", "кухн", "официант", "бармен", "бариста", "стройк", "монтаж", "фасовк", "сборк", "заказа", "доставк", "такси"]
    for kw in online_keywords:
        if kw in title_lower:
            return "online"
    for kw in active_keywords:
        if kw in title_lower:
            return "active"
    return "active"

async def parse_avito(city: str, pages: int = 2) -> List[Dict]:
    vacancies = []
    city_domains = {
        "москва": "moskva", "санкт-петербург": "sankt-peterburg", "спб": "sankt-peterburg",
        "казань": "kazan", "екатеринбург": "ekaterinburg", "новосибирск": "novosibirsk",
        "краснодар": "krasnodar", "ростов-на-дону": "rostov-na-donu", "ростов": "rostov-na-donu",
        "нижний новгород": "nizhniy_novgorod", "челябинск": "chelyabinsk",
        "самара": "samara", "уфа": "ufa", "омск": "omsk", "пермь": "perm",
        "воронеж": "voronezh", "волгоград": "volgograd"
    }
    domain = city_domains.get(city.lower().strip(), city.lower().strip().replace(" ", "_"))
    keywords = [
        "подработка+с+14+лет", "работа+для+школьников", "раздача+листовок",
        "промоутер", "курьер+с+16", "расклейка+объявлений"
    ]
    headers_list = [
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
        {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36"},
    ]
    for keyword in keywords[:3]:
        for page in range(1, pages + 1):
            url = f"https://www.avito.ru/{domain}?q={keyword}&p={page}"
            headers = random.choice(headers_list)
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, timeout=20) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()
                soup = BeautifulSoup(html, "html.parser")
                items = soup.find_all("div", {"data-marker": "item"})
                for item in items[:3]:
                    try:
                        title_elem = item.find("h3", {"itemprop": "name"})
                        price_elem = item.find("meta", {"itemprop": "price"})
                        link_elem = item.find("a", {"data-marker": "item-title"})
                        title = title_elem.text.strip() if title_elem else "Без названия"
                        price = price_elem.get("content", "Не указана") if price_elem else "Не указана"
                        link = "https://www.avito.ru" + link_elem.get("href", "") if link_elem else url
                        if any(w in title.lower() for w in ["14", "15", "16", "17", "школьник", "студент", "подработк", "промоутер", "курьер", "раздач", "расклейк"]):
                            job_type = classify_job_type(title)
                            vacancies.append({
                                "title": title,
                                "description": f"Вакансия с Avito: {title}",
                                "payment": f"{price} руб." if price != "Не указана" else "Договорная",
                                "city": city,
                                "age_groups": ["14-15", "16-17", "18+"],
                                "job_type": job_type,
                                "contact": f"Ссылка: {link}",
                                "source": "Avito",
                                "date_added": datetime.now().isoformat()
                            })
                    except:
                        continue
                await asyncio.sleep(random.uniform(5, 10))
            except:
                continue
    log.info(f"Avito: найдено {len(vacancies)} вакансий для {city}")
    return vacancies

async def parse_hh(city_name: str, city_code: int = 1) -> List[Dict]:
    vacancies = []
    params = {
        "text": "подработка OR школьник OR студент OR без опыта OR промоутер OR курьер",
        "area": city_code,
        "experience": "noExperience",
        "employment": "part",
        "per_page": 10,
        "page": 0,
        "period": 7
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(HH_API_URL, params=params, timeout=15) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        for item in data.get("items", []):
            try:
                title = item.get("name", "Без названия")
                employer = item.get("employer", {}).get("name", "Не указан")
                salary = item.get("salary")
                if salary:
                    salary_from = salary.get("from", "")
                    salary_to = salary.get("to", "")
                    payment = f"{salary_from or '?'} - {salary_to or '?'} {salary.get('currency', 'руб.')}"
                else:
                    payment = "Не указана"
                url = item.get("alternate_url", "")
                snippet = item.get("snippet", {})
                responsibility = snippet.get("responsibility", "") or ""
                responsibility = re.sub(r'<[^>]+>', '', responsibility)
                job_type = classify_job_type(title)
                vacancies.append({
                    "title": title,
                    "description": f"{employer}. {responsibility[:150]}...",
                    "payment": payment,
                    "city": city_name,
                    "age_groups": ["16-17", "18+"],
                    "job_type": job_type,
                    "contact": f"Откликнуться: {url}",
                    "source": "hh.ru",
                    "date_added": datetime.now().isoformat()
                })
            except:
                continue
    except:
        pass
    log.info(f"hh.ru: найдено {len(vacancies)} вакансий для {city_name}")
    return vacancies

async def background_parsing():
    cities = ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск"]
    while True:
        log.info("Фоновый парсинг запущен")
        for city in cities:
            try:
                avito_jobs = await parse_avito(city, pages=1)
                for v in avito_jobs:
                    db.add_vacancy(v)
            except Exception as e:
                log.error(f"Ошибка Avito {city}: {e}")
            try:
                city_codes = {"Москва": 1, "Санкт-Петербург": 2, "Казань": 88, "Екатеринбург": 3, "Новосибирск": 4}
                code = city_codes.get(city, 1)
                hh_jobs = await parse_hh(city, code)
                for v in hh_jobs:
                    db.add_vacancy(v)
            except Exception as e:
                log.error(f"Ошибка hh {city}: {e}")
            await asyncio.sleep(5)
        cutoff = datetime.now() - timedelta(days=7)
        db.vacancies = [v for v in db.vacancies if datetime.fromisoformat(v["date_added"]) > cutoff]
        if len(db.vacancies) > 300:
            db.vacancies = db.vacancies[-300:]
        db.save()
        log.info(f"Парсинг завершён. Вакансий: {len(db.vacancies)}")
        await asyncio.sleep(3 * 60 * 60)

class Onboarding(StatesGroup):
    city = State()
    age = State()
    job_type = State()

def main_menu(is_paid: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💰 Смотреть вакансии", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="🔧 Выбрать тип работы", callback_data="change_job_type")],
        [InlineKeyboardButton(text="📍 Сменить город", callback_data="change_city")],
    ]
    if not is_paid:
        buttons.append([InlineKeyboardButton(text="💎 Премиум (149₽)", callback_data="premium_info")])
    buttons.append([InlineKeyboardButton(text="📤 Поделиться с другом", switch_inline_query="")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Любая работа", callback_data="jobtype_any")],
        [InlineKeyboardButton(text="💻 Удалёнка / Онлайн", callback_data="jobtype_online")],
        [InlineKeyboardButton(text="🏃 Активная (курьер, промоутер)", callback_data="jobtype_active")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="main")],
    ])

async def cmd_start(message: Message, state: FSMContext):
    user = db.get_user(message.from_user.id)
    if not user["city"]:
        await message.answer(
            "👋 *Привет! Я помогу найти подработку.*\n\n"
            "В каком городе ищешь? Напиши название.\n"
            "Например: _Москва, Казань, Краснодар_",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Москва", callback_data="setcity_Москва")],
                [InlineKeyboardButton(text="СПб", callback_data="setcity_Санкт-Петербург")],
                [InlineKeyboardButton(text="Казань", callback_data="setcity_Казань")],
            ]),
            parse_mode="Markdown"
        )
        await state.set_state(Onboarding.city)
    else:
        job_type_names = {"any": "Любая", "online": "Удалёнка", "active": "Активная"}
        jt = job_type_names.get(user.get("job_type", "any"), "Любая")
        views_left = max(0, FREE_LIMIT - user["daily_views"]) if not user["paid"] else "∞"
        await message.answer(
            f"👋 *С возвращением!*\n\n"
            f"📍 Город: *{user['city']}*\n"
            f"👤 Возраст: *{user['age_group']}*\n"
            f"🔧 Тип работы: *{jt}*\n"
            f"💎 Статус: *{'Премиум' if user['paid'] else 'Бесплатно (' + str(views_left) + ' сегодня)'}*\n\n"
            "Жми кнопку 👇",
            reply_markup=main_menu(user["paid"]),
            parse_mode="Markdown"
        )

async def set_city(call: CallbackQuery, state: FSMContext):
    city = call.data.replace("setcity_", "")
    user = db.get_user(call.from_user.id)
    user["city"] = city
    db.save()
    await call.message.edit_text(
        f"📍 Город: *{city}*\n\nТеперь укажи возраст:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="14-15 лет", callback_data="setage_14-15")],
            [InlineKeyboardButton(text="16-17 лет", callback_data="setage_16-17")],
            [InlineKeyboardButton(text="18+", callback_data="setage_18+")],
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.age)

async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    user = db.get_user(message.from_user.id)
    user["city"] = city
    db.save()
    await message.answer(
        f"📍 Город: *{city}*\n\nТеперь укажи возраст:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="14-15 лет", callback_data="setage_14-15")],
            [InlineKeyboardButton(text="16-17 лет", callback_data="setage_16-17")],
            [InlineKeyboardButton(text="18+", callback_data="setage_18+")],
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.age)

async def set_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("setage_", "")
    user = db.get_user(call.from_user.id)
    user["age_group"] = age
    db.save()
    await call.message.edit_text(
        f"✅ *Возраст: {age}*\n\n"
        "Теперь выбери тип работы:",
        reply_markup=job_type_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.job_type)

async def set_job_type(call: CallbackQuery, state: FSMContext):
    jt = call.data.replace("jobtype_", "")
    user = db.get_user(call.from_user.id)
    user["job_type"] = jt
    db.save()
    job_type_names = {"any": "Любая", "online": "Удалёнка", "active": "Активная"}
    await call.message.edit_text(
        f"✅ *Готово!*\n\n"
        f"📍 Город: *{user['city']}*\n"
        f"👤 Возраст: *{user['age_group']}*\n"
        f"🔧 Тип работы: *{job_type_names.get(jt, 'Любая')}*\n\n"
        "Теперь жми «Смотреть вакансии» и получай предложения!",
        reply_markup=main_menu(user["paid"]),
        parse_mode="Markdown"
    )
    await state.clear()

async def change_job_type(call: CallbackQuery):
    await call.message.edit_text(
        "🔧 *Выбери тип работы:*",
        reply_markup=job_type_keyboard(),
        parse_mode="Markdown"
    )

async def show_vacancies(call: CallbackQuery):
    user = db.get_user(call.from_user.id)
    if not user["city"]:
        await call.message.edit_text(
            "Сначала укажи город. Напиши /start",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⬅ В меню", callback_data="main")]
            ])
        )
        return
    if not db.can_view(call.from_user.id):
        await call.message.edit_text(
            f"🚫 *Лимит на сегодня исчерпан.*\n\n"
            f"Ты посмотрел {FREE_LIMIT} вакансии бесплатно.\n"
            f"💎 Премиум — *безлимит* + уведомления + избранное.\n"
            f"Всего 149 руб. навсегда.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Купить Премиум", callback_data="buy_premium")],
                [InlineKeyboardButton(text="⬅ В меню", callback_data="main")]
            ]),
            parse_mode="Markdown"
        )
        return
    job_type = user.get("job_type", "any")
    vacancies = db.get_vacancies(user.get("city", "Москва"), user.get("age_group", "16-17"), job_type)
    if not vacancies:
        await call.message.edit_text("🔍 *Ищу свежие вакансии...* Подожди.", parse_mode="Markdown")
        try:
            avito_jobs = await parse_avito(user.get("city", "Москва"), pages=1)
            for v in avito_jobs:
                db.add_vacancy(v)
        except:
            pass
        try:
            city_codes = {"Москва": 1, "Санкт-Петербург": 2, "Казань": 88, "Екатеринбург": 3, "Новосибирск": 4}
            code = city_codes.get(user.get("city", "Москва"), 1)
            hh_jobs = await parse_hh(user.get("city", "Москва"), code)
            for v in hh_jobs:
                db.add_vacancy(v)
        except:
            pass
        vacancies = db.get_vacancies(user.get("city", "Москва"), user.get("age_group", "16-17"), job_type)
    if not vacancies:
        await call.message.edit_text(
            "😔 По твоему фильтру пока нет вакансий.\nПопробуй выбрать «Любая работа» или подожди обновления.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔧 Сменить тип работы", callback_data="change_job_type")],
                [InlineKeyboardButton(text="⬅ В меню", callback_data="main")]
            ]),
            parse_mode="Markdown"
        )
        return
    db.increment_views(call.from_user.id)
    random.shuffle(vacancies)
    to_show = vacancies[:3]
    job_type_names = {"any": "Любая", "online": "Удалёнка", "active": "Активная"}
    jt_name = job_type_names.get(job_type, "Любая")
    response = f"💰 *Вакансии ({jt_name}) в {user.get('city', 'твоём городе')}:*\n\n"
    for i, v in enumerate(to_show, 1):
        type_emoji = "💻" if v.get("job_type") == "online" else "🏃"
        response += f"*{i}. {type_emoji} {v['title']}*\n"
        response += f"💵 {v['payment']}\n"
        response += f"📝 {v['description'][:120]}...\n"
        response += f"📞 {v['contact']}\n"
        response += f"🔹 {v['source']}\n\n"
    views_left = max(0, FREE_LIMIT - user["daily_views"])
    response += f"📊 Осталось сегодня: *{views_left if not user['paid'] else '∞'}*\n"
    if not user["paid"]:
        response += "💎 *Премиум* — безлимит навсегда."
    await call.message.edit_text(
        response,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё вакансии", callback_data="show_vacancies")],
            [InlineKeyboardButton(text="🔧 Сменить тип работы", callback_data="change_job_type")],
            [InlineKeyboardButton(text="💎 Премиум (безлимит)", callback_data="premium_info")],
            [InlineKeyboardButton(text="⬅ В меню", callback_data="main")]
        ]),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

async def premium_info(call: CallbackQuery):
    await call.message.edit_text(
        "💎 *Премиум-доступ*\n\n"
        "Что ты получаешь:\n"
        "💰 *Безлимитный просмотр* вакансий\n"
        "🔔 *Уведомления* о новых (скоро)\n"
        "✅ *Только проверенные* работодатели (скоро)\n"
        "📝 *Шаблоны откликов* — готовые тексты\n"
        "🛡 *Гайд «Как не попасть на мошенников»*\n"
        "📄 *Гайд «Самозанятость с 14 лет»*\n\n"
        f"💰 *{PREMIUM_PRICE} звёзд Telegram (~149 руб.)*\n"
        "🔐 Один раз — навсегда. Не подписка.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💎 Купить за {PREMIUM_PRICE}⭐", callback_data="buy_premium")],
            [InlineKeyboardButton(text="⬅ В меню", callback_data="main")]
        ]),
        parse_mode="Markdown"
    )

async def buy_premium(call: CallbackQuery):
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="Премиум «Где подработка?»",
        description="Безлимит вакансий, уведомления, гайды. Навсегда.",
        payload="jobs_premium_v1",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Доступ навсегда", amount=PREMIUM_PRICE)],
        start_parameter="jobs_premium"
    )

async def pre_checkout(pq: PreCheckoutQuery):
    await pq.answer(ok=True)

async def payment_success(message: Message):
    db.set_paid(message.from_user.id)
    await message.answer("💎 *
