#!/usr/bin/env python3
"""
БОТ «ГДЕ ПОДРАБОТКА?» — БОЕВАЯ ВЕРСИЯ
Агрегатор вакансий для подростков 14-17 лет
Парсинг Avito + hh.ru API через прокси
Тройная защита от засыпания
Монетизация: Telegram Stars
"""
import asyncio
import json
import logging
import random
import re
import aiohttp
import subprocess
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

PROXY_LIST = [
    "http://194.67.200.10:8080",
    "http://185.221.153.131:8080",
    "http://95.182.108.149:8080",
    "http://178.208.83.34:8080",
    "http://109.248.14.19:8080",
]

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
            log.info(f"База: {len(self.users)} пользователей, {len(self.vacancies)} вакансий")
        except:
            self.users = {}
            self.vacancies = []
            log.info("База пустая")

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
        user["city"] = "Москва"
        user["age_group"] = "16-17"
        user["job_type"] = "any"
        self.save()

    def get_vacancies(self, city: str, age_group: str, job_type: str = "any") -> List[Dict]:
        city_lower = city.lower().strip()
        results = []
        for v in self.vacancies:
            v_city = v.get("city", "").lower()
            v_age_groups = v.get("age_groups", ["14-15", "16-17", "18+"])
            v_job_type = v.get("job_type", "active")
            if city_lower in v_city or v_city in city_lower or v_city == "вся россия":
                if age_group in v_age_groups:
                    if job_type == "any" or job_type == v_job_type:
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
        db.vacancies = []
    jobs = [
        {"title": "Раздача листовок у метро Кузнецкий мост", "description": "Раздача рекламных листовок. 4 часа в день. Можно без опыта.", "payment": "500 руб.", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (495) 123-45-67\n📱 WhatsApp: +7 (926) 111-22-33", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на велосипеде/самокате", "description": "Доставка еды из ресторанов. Свободный график. Ежедневные выплаты.", "payment": "3000 руб./день", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (495) 222-33-44\n🔗 https://clck.ru/courier_msk", "source": "Яндекс.Еда", "date_added": datetime.now().isoformat()},
        {"title": "Написание отзывов на маркетплейсах", "description": "Удалённая работа. Писать отзывы на Wildberries, Ozon. Обучение бесплатно.", "payment": "100 руб./отзыв", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "📱 Telegram: @otzyvy_bot\n🔗 https://t.me/otzyvy_bot", "source": "Маркетплейсы", "date_added": datetime.now().isoformat()},
        {"title": "Модератор чата интернет-магазина", "description": "Удалённо. Следить за порядком в чате, отвечать на вопросы. 2-3 часа в день.", "payment": "8000 руб./мес", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "online", "contact": "📧 hr@fashionshop.ru\n📞 +7 (495) 333-55-66", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Выгул собак в центре", "description": "Выгул собак в районе Хамовники. 2 раза в день. Подходит школьникам.", "payment": "500 руб./выгул", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (916) 444-55-66\n📱 WhatsApp: +7 (916) 444-55-66", "source": "Частное лицо", "date_added": datetime.now().isoformat()},
        {"title": "Расклейка объявлений на подъездах", "description": "Расклейка объявлений в районе ЦАО. Оплата за каждую доску.", "payment": "1500 руб.", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (903) 777-88-99", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Копирайтинг для соцсетей", "description": "Написание постов для Instagram/Telegram. Темы: мода, игры, кино.", "payment": "300 руб./пост", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "online", "contact": "📧 smm@content.ru\n🔗 https://hh.ru/vacancy/copywriter", "source": "hh.ru", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ Галерея", "description": "Раздача образцов кофе в ТЦ. 3 часа в день. Обучение на месте.", "payment": "1200 руб.", "city": "Санкт-Петербург", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (812) 111-22-33\n📱 WhatsApp: +7 (921) 333-44-55", "source": "Рекламное агентство", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на самокате по центру", "description": "Доставка посылок. Самокат предоставляется. Ежедневная оплата.", "payment": "2000 руб./день", "city": "Санкт-Петербург", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (812) 444-55-66\n🔗 https://clck.ru/spb_courier", "source": "Достависта", "date_added": datetime.now().isoformat()},
        {"title": "Онлайн-консультант в чат", "description": "Поддержка клиентов интернет-магазина. Удалённо. Обучение.", "payment": "15000 руб./мес", "city": "Санкт-Петербург", "age_groups": ["16-17", "18+"], "job_type": "online", "contact": "📧 job@spb-shop.ru\n🔗 https://hh.ru/vacancy/consultant", "source": "hh.ru", "date_added": datetime.now().isoformat()},
        {"title": "Раздача листовок на Баумана", "description": "Раздача листовок на пешеходной улице. 3-4 часа.", "payment": "400 руб.", "city": "Казань", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (843) 222-33-44", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ Кольцо", "description": "Дегустация напитков в ТЦ. Выходные, 4 часа.", "payment": "1000 руб.", "city": "Казань", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (917) 555-66-77\n📱 WhatsApp: +7 (917) 555-66-77", "source": "Рекламное агентство", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на самокате", "description": "Доставка посылок по городу. Самокат свой или предоставим.", "payment": "2000 руб./день", "city": "Екатеринбург", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (343) 111-22-33\n🔗 https://clck.ru/ekb_courier", "source": "Достависта", "date_added": datetime.now().isoformat()},
        {"title": "Написание отзывов удалённо", "description": "Писать отзывы на маркетплейсы. Гибкий график.", "payment": "50-100 руб./отзыв", "city": "Екатеринбург", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "📱 Telegram: @otzyvy_ekb\n🔗 https://t.me/otzyvy_ekb", "source": "Маркетплейсы", "date_added": datetime.now().isoformat()},
        {"title": "Расклейка объявлений", "description": "Расклейка на подъездах в центре. Оплата за количество.", "payment": "1000 руб.", "city": "Новосибирск", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (383) 222-33-44", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Модератор чата удалённо", "description": "Следить за чатом интернет-магазина. 3 часа в день.", "payment": "7000 руб./мес", "city": "Новосибирск", "age_groups": ["16-17", "18+"], "job_type": "online", "contact": "📧 hr@nsk-shop.ru\n🔗 https://hh.ru/vacancy/moderator_nsk", "source": "hh.ru", "date_added": datetime.now().isoformat()},
        {"title": "Раздача листовок на Красной", "description": "Раздача листовок на главной улице. 3-4 часа.", "payment": "500 руб.", "city": "Краснодар", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (861) 111-22-33", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ Красная Площадь", "description": "Раздача образцов кофе. Выходные.", "payment": "1100 руб.", "city": "Краснодар", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (918) 444-55-66", "source": "Рекламное агентство", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на велосипеде", "description": "Доставка еды. Свободный график.", "payment": "2500 руб./день", "city": "Ростов-на-Дону", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (863) 222-33-44\n🔗 https://clck.ru/rostov_courier", "source": "Яндекс.Еда", "date_added": datetime.now().isoformat()},
        {"title": "Выгул собак на набережной", "description": "Выгул собак, Верхневолжская набережная.", "payment": "400 руб./выгул", "city": "Нижний Новгород", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (831) 111-22-33", "source": "Частное лицо", "date_added": datetime.now().isoformat()},
        {"title": "Расклейка объявлений ЧТЗ", "description": "Расклейка на подъездах в районе ЧТЗ.", "payment": "1200 руб.", "city": "Челябинск", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (351) 222-33-44", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Раздача листовок на набережной", "description": "Раздача листовок. 3-4 часа.", "payment": "450 руб.", "city": "Самара", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (846) 111-22-33", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ", "description": "Дегустация соков в ТЦ. Выходные.", "payment": "900 руб.", "city": "Уфа", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (347) 222-33-44", "source": "Рекламное агентство", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на автобусе", "description": "Доставка документов по городу. Проездной оплачивается.", "payment": "1500 руб./день", "city": "Омск", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (3812) 11-22-33", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Раздача листовок на набережной", "description": "Центральная набережная. 3 часа.", "payment": "400 руб.", "city": "Волгоград", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (8442) 11-22-33", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Расклейка объявлений центр", "description": "Расклейка в центральном районе.", "payment": "1000 руб.", "city": "Воронеж", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (473) 222-33-44", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ Планета", "description": "Раздача листовок в ТЦ. Выходные.", "payment": "1000 руб.", "city": "Красноярск", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (391) 111-22-33", "source": "Рекламное агентство", "date_added": datetime.now().isoformat()},
        {"title": "Курьер пеший по центру", "description": "Доставка документов. Центр города.", "payment": "1800 руб./день", "city": "Пермь", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "📞 +7 (342) 222-33-44", "source": "Прямой работодатель", "date_added": datetime.now().isoformat()},
        {"title": "Помощь по хозяйству", "description": "Уборка территории, помощь на участке. 3-4 часа.", "payment": "800 руб.", "city": "Павловск", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (47362) 2-34-56\n📱 WhatsApp: +7 (920) 111-22-33", "source": "Частное лицо", "date_added": datetime.now().isoformat()},
        {"title": "Выгул собак в центре Павловска", "description": "Выгул собак ул. Советская. 2 раза в день.", "payment": "300 руб./выгул", "city": "Павловск", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "📞 +7 (920) 444-55-66", "source": "Частное лицо", "date_added": datetime.now().isoformat()},
        {"title": "Написание отзывов удалённо", "description": "Писать отзывы на WB/Ozon. Можно из любого города.", "payment": "50-100 руб./отзыв", "city": "Павловск", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "📱 Telegram: @otzyvy_bot\n🔗 https://t.me/otzyvy_bot", "source": "Маркетплейсы", "date_added": datetime.now().isoformat()},
        {"title": "Транскрибация аудио в текст", "description": "Расшифровка аудиозаписей. Удалённо. Подходит новичкам.", "payment": "200 руб./час", "city": "Вся Россия", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "📧 transcribe@work.ru\n🔗 https://hh.ru/vacancy/transcribe", "source": "hh.ru", "date_added": datetime.now().isoformat()},
        {"title": "Дизайн аватарок для соцсетей", "description": "Создание аватарок на заказ. Можно без опыта, научим.", "payment": "200 руб./шт", "city": "Вся Россия", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "📱 Telegram: @design_bot\n🔗 https://t.me/design_bot", "source": "Фриланс", "date_added": datetime.now().isoformat()},
        {"title": "Набор текста со сканов", "description": "Набор текста с фотографий. Удалённо.", "payment": "150 руб./1000 знаков", "city": "Вся Россия", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "📧 text@job.ru\n🔗 https://hh.ru/vacancy/typist", "source": "hh.ru", "date_added": datetime.now().isoformat()},
    ]
    for j in jobs:
        db.vacancies.append(j)
    db.save()
    log.info(f"Добавлено {len(jobs)} стартовых вакансий")

def get_proxy():
    return random.choice(PROXY_LIST) if PROXY_LIST else None

async def ai_gen(system: str, user: str, temp: float = 0.8) -> str:
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "temperature": temp, "max_tokens": 800}
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=30) as r:
                if r.status == 200:
                    return (await r.json())["choices"][0]["message"]["content"]
                return "Ошибка генерации."
    except:
        return "Сервис недоступен."

def classify(title: str) -> str:
    t = title.lower()
    for w in ["удалён", "онлайн", "отзыв", "модерат", "копирайт", "текст", "транскриб", "дизайн", "набор текст"]:
        if w in t:
            return "online"
    return "active"

async def parse_avito(city: str, pages: int = 2) -> List[Dict]:
    vacancies = []
    city_domains = {
        "москва": "moskva", "санкт-петербург": "sankt-peterburg", "спб": "sankt-peterburg",
        "казань": "kazan", "екатеринбург": "ekaterinburg", "новосибирск": "novosibirsk",
        "краснодар": "krasnodar", "ростов-на-дону": "rostov-na-donu", "ростов": "rostov-na-donu",
        "нижний новгород": "nizhniy_novgorod", "челябинск": "chelyabinsk",
        "самара": "samara", "уфа": "ufa", "омск": "omsk", "пермь": "perm",
        "воронеж": "voronezh", "волгоград": "volgograd", "красноярск": "krasnoyarsk",
    }
    domain = city_domains.get(city.lower().strip(), city.lower().strip().replace(" ", "_"))
    keywords = ["подработка+с+14+лет", "работа+для+школьников", "раздача+листовок", "промоутер", "курьер+с+16"]
    headers_list = [
        {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"},
        {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36"},
    ]
    for keyword in keywords[:2]:
        for page in range(1, pages + 1):
            url = f"https://www.avito.ru/{domain}?q={keyword}&p={page}"
            headers = random.choice(headers_list)
            proxy = get_proxy()
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, proxy=proxy, timeout=25) as resp:
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
                            job_type = classify(title)
                            vacancies.append({
                                "title": title,
                                "description": f"Вакансия с Avito: {title}",
                                "payment": f"{price} руб." if price != "Не указана" else "Договорная",
                                "city": city,
                                "age_groups": ["14-15", "16-17", "18+"],
                                "job_type": job_type,
                                "contact": f"📞 Ссылка на Avito:\n🔗 {link}",
                                "source": "Avito",
                                "date_added": datetime.now().isoformat()
                            })
                    except:
                        continue
                await asyncio.sleep(random.uniform(3, 8))
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
    proxy = get_proxy()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(HH_API_URL, params=params, proxy=proxy, timeout=20) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        for item in data.get("items", []):
            try:
                title = item.get("name", "Без названия")
                employer = item.get("employer", {}).get("name", "Не указан")
                salary = item.get("salary")
                if salary:
                    payment = f"{salary.get('from','?')} - {salary.get('to','?')} {salary.get('currency','руб.')}"
                else:
                    payment = "Не указана"
                url = item.get("alternate_url", "")
                snippet = item.get("snippet", {})
                responsibility = snippet.get("responsibility", "") or ""
                responsibility = re.sub(r'<[^>]+>', '', responsibility)
                job_type = classify(title)
                vacancies.append({
                    "title": title,
                    "description": f"{employer}. {responsibility[:150]}...",
                    "payment": payment,
                    "city": city_name,
                    "age_groups": ["16-17", "18+"],
                    "job_type": job_type,
                    "contact": f"📞 Откликнуться на hh.ru:\n🔗 {url}",
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
    cities = ["Москва", "Санкт-Петербург", "Казань", "Екатеринбург", "Новосибирск",
              "Краснодар", "Нижний Новгород", "Челябинск", "Самара", "Уфа",
              "Омск", "Волгоград", "Воронеж", "Красноярск", "Пермь", "Ростов-на-Дону"]
    city_codes = {"Москва": 1, "Санкт-Петербург": 2, "Казань": 88, "Екатеринбург": 3,
                  "Новосибирск": 4, "Краснодар": 53, "Нижний Новгород": 66, "Челябинск": 104,
                  "Самара": 78, "Уфа": 99, "Омск": 68, "Волгоград": 40, "Воронеж": 26,
                  "Красноярск": 54, "Пермь": 72, "Ростов-на-Дону": 76}
    while True:
        log.info("Фоновый парсинг запущен")
        for city in cities:
            try:
                avito_jobs = await parse_avito(city, pages=1)
                for v in avito_jobs:
                    db.add_vacancy(v)
                log.info(f"Avito {city}: +{len(avito_jobs)}")
            except Exception as e:
                log.error(f"Ошибка Avito {city}: {e}")
            try:
                code = city_codes.get(city, 1)
                hh_jobs = await parse_hh(city, code)
                for v in hh_jobs:
                    db.add_vacancy(v)
                log.info(f"hh.ru {city}: +{len(hh_jobs)}")
            except Exception as e:
                log.error(f"Ошибка hh {city}: {e}")
            await asyncio.sleep(3)
        cutoff = datetime.now() - timedelta(days=14)
        db.vacancies = [v for v in db.vacancies if datetime.fromisoformat(v["date_added"]) > cutoff]
        if len(db.vacancies) > 500:
            db.vacancies = db.vacancies[-500:]
        db.save()
        log.info(f"Парсинг завершён. Всего вакансий: {len(db.vacancies)}")
        await asyncio.sleep(30 * 60)

async def keep_alive():
    """Само-пинг каждые 5 минут чтобы бот не засыпал"""
    await asyncio.sleep(60)
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://job-bot-new.onrender.com", timeout=10) as r:
                    log.info(f"Keep-alive ping: {r.status}")
        except:
            log.warning("Keep-alive ping failed")
        await asyncio.sleep(300)

class Onboarding(StatesGroup):
    city = State()
    age = State()
    job_type = State()

def main_menu(is_paid: bool = False) -> InlineKeyboardMarkup:
    btns = [
        [InlineKeyboardButton(text="💰 Смотреть вакансии", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="🔧 Тип работы", callback_data="change_job_type")],
        [InlineKeyboardButton(text="👤 Возраст", callback_data="change_age")],
        [InlineKeyboardButton(text="📍 Город", callback_data="change_city")],
    ]
    if not is_paid:
        btns.append([InlineKeyboardButton(text="💎 Премиум (149₽)", callback_data="premium_info")])
    btns.append([InlineKeyboardButton(text="📤 Поделиться", switch_inline_query="")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Любая", callback_data="jobtype_any")],
        [InlineKeyboardButton(text="💻 Удалёнка", callback_data="jobtype_online")],
        [InlineKeyboardButton(text="🏃 Активная", callback_data="jobtype_active")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="main")],
    ])

def age_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="14-15", callback_data="setage_14-15")],
        [InlineKeyboardButton(text="16-17", callback_data="setage_16-17")],
        [InlineKeyboardButton(text="18+", callback_data="setage_18+")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="main")],
    ])

async def cmd_start(message: Message, state: FSMContext):
    u = db.get_user(message.from_user.id)
    if not u["city"]:
        await message.answer(
            "👋 *Привет!*\nВ каком городе ищешь работу?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Москва", callback_data="setcity_Москва")],
                [InlineKeyboardButton(text="СПб", callback_data="setcity_Санкт-Петербург")],
                [InlineKeyboardButton(text="Другой город", callback_data="setcity_other")],
            ]),
            parse_mode="Markdown"
        )
        await state.set_state(Onboarding.city)
    else:
        v = "∞" if u["paid"] else str(max(0, FREE_LIMIT - u["daily_views"]))
        await message.answer(
            f"👋 *Меню*\n📍 {u['city']} | 👤 {u['age_group']}\n💎 {'Премиум' if u['paid'] else 'Бесплатно ('+v+' сегодня)'}",
            reply_markup=main_menu(u["paid"]),
            parse_mode="Markdown"
        )

async def set_city(call: CallbackQuery, state: FSMContext):
    city = call.data.replace("setcity_", "")
    if city == "other":
        await call.message.edit_text("📍 Напиши название города:", parse_mode="Markdown")
        await state.set_state(Onboarding.city)
        return
    db.set_city(call.from_user.id, city)
    await call.message.edit_text(
        f"📍 *{city}*\nУкажи возраст:",
        reply_markup=age_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.age)

async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    db.set_city(message.from_user.id, city)
    await message.answer(
        f"📍 *{city}*\nУкажи возраст:",
        reply_markup=age_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.age)

async def set_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("setage_", "")
    db.set_age(call.from_user.id, age)
    await call.message.edit_text(
        f"✅ *Возраст: {age}*\nВыбери тип работы:",
        reply_markup=job_type_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.job_type)

async def set_job_type(call: CallbackQuery, state: FSMContext):
    jt = call.data.replace("jobtype_", "")
    db.set_job_type(call.from_user.id, jt)
    names = {"any": "Любая", "online": "Удалёнка", "active": "Активная"}
    await call.message.edit_text(
        f"✅ *Готово!*\nТип: *{names.get(jt)}*\nЖми «Смотреть вакансии»",
        reply_markup=main_menu(False),
        parse_mode="Markdown"
    )
    await state.clear()

async def change_job_type(call: CallbackQuery):
    await call.message.edit_text("🔧 *Тип работы:*", reply_markup=job_type_keyboard(), parse_mode="Markdown")

async def change_age(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("👤 *Возраст:*", reply_markup=age_keyboard(), parse_mode="Markdown")
    await state.set_state(Onboarding.age)

async def show_vacancies(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    if not u["city"]:
        await call.message.edit_text("Сначала /start", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]))
        return
    if not db.can_view(call.from_user.id):
        await call.message.edit_text(
            "🚫 *Лимит.*\n💎 Премиум — безлимит за 149 руб.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 Купить", callback_data="buy_premium")],
                [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
            ]),
            parse_mode="Markdown"
        )
        return
    vacs = db.get_vacancies(u.get("city", "Москва"), u.get("age_group", "16-17"), u.get("job_type", "any"))
    if not vacs:
        await call.message.edit_text(
            "😔 Нет вакансий под твой фильтр. Смени город, возраст или тип работы.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔧 Сменить фильтры", callback_data="main")]
            ]),
            parse_mode="Markdown"
        )
        return
    db.increment_views(call.from_user.id)
    random.shuffle(vacs)
    to_show = vacs[:3]
    names = {"any": "Любая", "online": "Удалёнка", "active": "Активная"}
    resp = f"💰 *Вакансии ({names.get(u.get('job_type','any'))}) в {u.get('city')}:*\n\n"
    for i, v in enumerate(to_show, 1):
        e = "💻" if v.get("job_type") == "online" else "🏃"
        resp += f"*{i}. {e} {v['title']}*\n💵 {v['payment']}\n📝 {v['description'][:120]}...\n\n"
    v_left = max(0, FREE_LIMIT - u["daily_views"])
    resp += f"📊 Осталось: *{v_left if not u['paid'] else '∞'}*\n"
    if not u["paid"]:
        resp += "💎 *Премиум* — безлимит."
    keyboard_buttons = [
        [InlineKeyboardButton(text="🔄 Ещё", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="💎 Премиум", callback_data="premium_info")],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
    ]
    for i, v in enumerate(to_show, 1):
        keyboard_buttons.insert(-1, [InlineKeyboardButton(text=f"📞 Показать контакт #{i}", callback_data=f"contact_{i}")])
    await call.message.edit_text(
        resp,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_buttons),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    # Сохраняем показываемые вакансии для callback'а контактов
    db.get_user(call.from_user.id)["_last_shown"] = to_show
    db.save()

async def show_contact(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    to_show = u.get("_last_shown", [])
    if not to_show:
        await call.answer("Сначала посмотри вакансии")
        return
    idx = int(call.data.replace("contact_", "")) - 1
    if idx >= len(to_show):
        await call.answer("Вакансия не найдена")
        return
    v = to_show[idx]
    await call.message.answer(
        f"📞 *Контакт для:* {v['title']}\n\n{v['contact']}",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await call.answer()

async def premium_info(call: CallbackQuery):
    await call.message.edit_text(
        f"💎 *Премиум*\nБезлимит, уведомления, гайды.\n💰 {PREMIUM_PRICE}⭐ (~149 руб.)\nНавсегда.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"💎 Купить ({PREMIUM_PRICE}⭐)", callback_data="buy_premium")],
            [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
        ]),
        parse_mode="Markdown"
    )

async def buy_premium(call: CallbackQuery):
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="Премиум",
        description="Безлимит навсегда",
        payload="prem",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label="Доступ", amount=PREMIUM_PRICE)],
        start_parameter="prem"
    )

async def pre_checkout(pq: PreCheckoutQuery):
    await pq.answer(ok=True)

async def payment_success(message: Message):
    db.set_paid(message.from_user.id)
    await message.answer("💎 *Готово!* Безлимит активен.", reply_markup=main_menu(True), parse_mode="Markdown")

async def change_city(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📍 Новый город:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Отмена", callback_data="main")]]), parse_mode="Markdown")
    await state.set_state(Onboarding.city)

async def main_handler(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    v = "∞" if u.get("paid") else str(max(0, FREE_LIMIT - u["daily_views"]))
    await call.message.edit_text(
        f"👋 *Меню*\n📍 {u.get('city','?')} | 👤 {u.get('age_group','?')}\n💎 {'Премиум' if u.get('paid') else 'Бесплатно ('+v+' сегодня)'}",
        reply_markup=main_menu(u.get("paid", False)),
        parse_mode="Markdown"
    )

async def stats_cmd(message: Message):
    if message.from_user.id == ADMIN_ID:
        t, p, v = db.stats()
        await message.answer(f"👥 {t} | 💎 {p} | 📋 {v} | ⭐ ~{p*PREMIUM_PRICE}")

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
    dp.callback_query.register(set_city, F.data.startswith("setcity_"))
    dp.message.register(process_city, Onboarding.city)
    dp.callback_query.register(set_age, F.data.startswith("setage_"))
    dp.callback_query.register(set_job_type, F.data.startswith("jobtype_"))
    dp.callback_query.register(change_job_type, F.data == "change_job_type")
    dp.callback_query.register(change_age, F.data == "change_age")
    dp.callback_query.register(main_handler, F.data == "main")
    dp.callback_query.register(show_vacancies, F.data == "show_vacancies")
    dp.callback_query.register(show_contact, F.data.startswith("contact_"))
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
