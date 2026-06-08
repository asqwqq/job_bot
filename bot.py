#!/usr/bin/env python3
"""
БОТ «ГДЕ ПОДРАБОТКА?» — ВЕРСИЯ 2.1
- Свежие прокси
- Кнопка поддержки @rabotka_support
- Готовые гайды
- Избранное
- Статистика по городам
- Тройная защита от засыпания
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
SUPPORT_USERNAME = "@rabotka_support"
PREMIUM_PRICE = 150
FREE_LIMIT = 3

PROXY_LIST = [
    "http://45.12.16.114:8080",
    "http://178.208.83.34:8080",
    "http://109.248.14.19:8080",
    "http://185.221.153.131:8080",
    "http://95.182.108.149:8080",
    "http://194.67.200.10:8080",
    "http://85.193.80.35:8080",
    "http://91.211.88.10:8080",
]

SCAM_GUIDE = """🛡 *Как не попасть на мошенников при поиске работы*

*1. Просят деньги за «доступ к вакансиям»*
Настоящий работодатель никогда не просит денег за трудоустройство. Если говорят «купите доступ к базе» или «оплатите оформление» — это развод.

*2. Обещают «золотые горы»*
Зарплата 100 000₽ за раздачу листовок? Это фейк. Реальная оплата для подростков: 400-1500₽ за смену, 15 000-25 000₽ в месяц.

*3. Нет контактов работодателя*
Только ник в Telegram без телефона и названия компании? Скорее всего мошенник. Требуй прямой номер телефона.

*4. Просят паспортные данные до собеседования*
Паспорт нужен только при оформлении трудового договора. Если просят прислать фото паспорта просто так — НЕ отправляй.

*5. «Вы выиграли вакансию»*
Если вам пишут первыми с предложением работы — это спам-рассылка мошенников.

⚠️ *Правило:* если сомневаешься — позвони по номеру, а не пиши в чат. Мошенники избегают звонков."""

SAMOZANYATOST_GUIDE = """📄 *Самозанятость с 14 лет*

*Что это?*
Самозанятость — это официальный статус, который позволяет работать и платить налог 4% с доходов. Можно с 14 лет с согласия родителей.

*Как оформить:*
1. Скачай приложение «Мой налог» (бесплатно)
2. Зарегистрируйся по паспорту
3. Покажи родителям — им нужно подписать согласие (в свободной форме)
4. Всё, ты самозанятый

*Плюсы:*
- Официальный доход (можно показать банку)
- Копятся пенсионные баллы
- Можно работать с юрлицами (компаниями)
- Налог всего 4%

*Минусы:*
- Нельзя нанимать сотрудников
- Доход до 2.4 млн в год
- Не все работодатели оформляют официально

*Как платить налог:*
Приложение само считает. Раз в месяц присылает уведомление — нажимаешь «Оплатить». Всё."""

TEMPLATES_GUIDE = """📝 *Шаблоны откликов*

*Для Avito:*
«Здравствуйте! Заинтересовала ваша вакансия. Мне 16 лет, есть согласие родителей на работу. Готов приступить. Когда можно подойти? Мой телефон: [твой номер]»

*Для hh.ru:*
«Добрый день! Меня зовут [имя], мне 17 лет. Ищу подработку на лето. Без опыта, но быстро учусь. Готов выполнить тестовое задание. Контакты: [телефон], [email]»

*Для личного сообщения работодателю:*
«Здравствуйте! Увидел ваше объявление о поиске [должность]. Я студент/школьник, ищу подработку. Ответственный, пунктуальный. Готов обсудить детали. Мой номер: [телефон]»

💡 *Совет:* всегда указывай реальный телефон. Работодатели не любят анонимов."""

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
                "city": None, "age_group": None, "job_type": "any",
                "paid": False, "daily_views": 0, "last_view_date": None,
                "favorites": [], "joined": datetime.now().isoformat(), "_last_shown": []
            }
        return self.users[uid]

    def can_view(self, uid: int) -> bool:
        user = self.get_user(uid)
        if user["paid"]: return True
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

    def add_favorite(self, uid: int, vacancy: Dict):
        user = self.get_user(uid)
        if len(user["favorites"]) < 20:
            user["favorites"].append(vacancy)
            self.save()
            return True
        return False

    def get_favorites(self, uid: int) -> List[Dict]:
        return self.get_user(uid)["favorites"]

    def get_vacancies(self, city: str, age_group: str, job_type: str = "any") -> List[Dict]:
        city_lower = city.lower().strip()
        results = []
        for v in self.vacancies:
            v_city = v.get("city", "").lower()
            if city_lower in v_city or v_city in city_lower or v_city == "вся россия":
                if age_group in v.get("age_groups", ["14-15", "16-17", "18+"]):
                    if job_type == "any" or job_type == v.get("job_type", "active"):
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
        cities = {}
        for u in self.users.values():
            c = u.get("city", "Не указан")
            cities[c] = cities.get(c, 0) + 1
        return total, paid, len(self.vacancies), cities

db = Database()

def seed_vacancies():
    if len(db.vacancies) > 0:
        db.vacancies = []
    jobs = [
        {"title":"Раздача листовок у метро Кузнецкий мост","description":"Раздача рекламных листовок. 4 часа. Можно без опыта.","payment":"500 руб.","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (495) 123-45-67\n📱 WhatsApp: +7 (926) 111-22-33","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Курьер на велосипеде/самокате","description":"Доставка еды. Свободный график. Ежедневные выплаты.","payment":"3000 руб./день","city":"Москва","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (495) 222-33-44\n🔗 https://clck.ru/courier_msk","source":"Яндекс.Еда","date_added":datetime.now().isoformat()},
        {"title":"Написание отзывов на маркетплейсах","description":"Удалённо. WB, Ozon. Обучение бесплатно.","payment":"100 руб./отзыв","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"online","contact":"📱 @otzyvy_bot\n🔗 https://t.me/otzyvy_bot","source":"Маркетплейсы","date_added":datetime.now().isoformat()},
        {"title":"Модератор чата интернет-магазина","description":"Удалённо. 2-3 часа в день.","payment":"8000 руб./мес","city":"Москва","age_groups":["16-17","18+"],"job_type":"online","contact":"📧 hr@fashionshop.ru\n📞 +7 (495) 333-55-66","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Выгул собак в центре","description":"Хамовники. 2 раза в день.","payment":"500 руб./выгул","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (916) 444-55-66","source":"Частное лицо","date_added":datetime.now().isoformat()},
        {"title":"Расклейка объявлений","description":"ЦАО. Оплата за доску.","payment":"1500 руб.","city":"Москва","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (903) 777-88-99","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Копирайтинг для соцсетей","description":"Посты для Instagram/TG.","payment":"300 руб./пост","city":"Москва","age_groups":["16-17","18+"],"job_type":"online","contact":"📧 smm@content.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        {"title":"Промоутер в ТЦ Галерея","description":"Раздача образцов. 3 часа.","payment":"1200 руб.","city":"Санкт-Петербург","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (812) 111-22-33","source":"Рекламное агентство","date_added":datetime.now().isoformat()},
        {"title":"Курьер на самокате","description":"Доставка посылок. Самокат дают.","payment":"2000 руб./день","city":"Санкт-Петербург","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (812) 444-55-66","source":"Достависта","date_added":datetime.now().isoformat()},
        {"title":"Онлайн-консультант","description":"Поддержка клиентов. Удалённо.","payment":"15000 руб./мес","city":"Санкт-Петербург","age_groups":["16-17","18+"],"job_type":"online","contact":"📧 job@spb-shop.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        {"title":"Раздача листовок на Баумана","description":"Пешеходная улица. 3-4 часа.","payment":"400 руб.","city":"Казань","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (843) 222-33-44","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Промоутер в ТЦ Кольцо","description":"Дегустация напитков.","payment":"1000 руб.","city":"Казань","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (917) 555-66-77","source":"Рекламное агентство","date_added":datetime.now().isoformat()},
        {"title":"Курьер на самокате","description":"Доставка посылок.","payment":"2000 руб./день","city":"Екатеринбург","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (343) 111-22-33","source":"Достависта","date_added":datetime.now().isoformat()},
        {"title":"Написание отзывов","description":"Удалённо. WB/Ozon.","payment":"100 руб./отзыв","city":"Екатеринбург","age_groups":["14-15","16-17","18+"],"job_type":"online","contact":"📱 @otzyvy_ekb","source":"Маркетплейсы","date_added":datetime.now().isoformat()},
        {"title":"Расклейка объявлений","description":"Центр.","payment":"1000 руб.","city":"Новосибирск","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (383) 222-33-44","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Модератор чата","description":"Удалённо. 3 часа.","payment":"7000 руб./мес","city":"Новосибирск","age_groups":["16-17","18+"],"job_type":"online","contact":"📧 hr@nsk-shop.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        {"title":"Раздача листовок на Красной","description":"Главная улица.","payment":"500 руб.","city":"Краснодар","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (861) 111-22-33","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Промоутер в ТЦ","description":"Раздача образцов.","payment":"1100 руб.","city":"Краснодар","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (918) 444-55-66","source":"Рекламное агентство","date_added":datetime.now().isoformat()},
        {"title":"Курьер на велосипеде","description":"Доставка еды.","payment":"2500 руб./день","city":"Ростов-на-Дону","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (863) 222-33-44","source":"Яндекс.Еда","date_added":datetime.now().isoformat()},
        {"title":"Выгул собак","description":"Набережная.","payment":"400 руб./выгул","city":"Нижний Новгород","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (831) 111-22-33","source":"Частное лицо","date_added":datetime.now().isoformat()},
        {"title":"Расклейка объявлений","description":"Район ЧТЗ.","payment":"1200 руб.","city":"Челябинск","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (351) 222-33-44","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Раздача листовок","description":"Набережная.","payment":"450 руб.","city":"Самара","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (846) 111-22-33","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Промоутер в ТЦ","description":"Дегустация соков.","payment":"900 руб.","city":"Уфа","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (347) 222-33-44","source":"Рекламное агентство","date_added":datetime.now().isoformat()},
        {"title":"Курьер на автобусе","description":"Доставка документов.","payment":"1500 руб./день","city":"Омск","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (3812) 11-22-33","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Раздача листовок","description":"Центральная набережная.","payment":"400 руб.","city":"Волгоград","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (8442) 11-22-33","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Расклейка объявлений","description":"Центральный район.","payment":"1000 руб.","city":"Воронеж","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (473) 222-33-44","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Промоутер в ТЦ Планета","description":"Раздача листовок.","payment":"1000 руб.","city":"Красноярск","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (391) 111-22-33","source":"Рекламное агентство","date_added":datetime.now().isoformat()},
        {"title":"Курьер пеший","description":"Центр.","payment":"1800 руб./день","city":"Пермь","age_groups":["16-17","18+"],"job_type":"active","contact":"📞 +7 (342) 222-33-44","source":"Прямой работодатель","date_added":datetime.now().isoformat()},
        {"title":"Помощь по хозяйству","description":"Уборка территории, помощь на участке.","payment":"800 руб.","city":"Павловск","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (47362) 2-34-56\n📱 WhatsApp: +7 (920) 111-22-33","source":"Частное лицо","date_added":datetime.now().isoformat()},
        {"title":"Выгул собак в центре","description":"Ул. Советская. 2 раза в день.","payment":"300 руб./выгул","city":"Павловск","age_groups":["14-15","16-17","18+"],"job_type":"active","contact":"📞 +7 (920) 444-55-66","source":"Частное лицо","date_added":datetime.now().isoformat()},
        {"title":"Написание отзывов","description":"Удалённо. WB/Ozon.","payment":"50-100 руб./отзыв","city":"Павловск","age_groups":["14-15","16-17","18+"],"job_type":"online","contact":"📱 @otzyvy_bot","source":"Маркетплейсы","date_added":datetime.now().isoformat()},
        {"title":"Транскрибация аудио","description":"Расшифровка в текст. Удалённо.","payment":"200 руб./час","city":"Вся Россия","age_groups":["14-15","16-17","18+"],"job_type":"online","contact":"📧 transcribe@work.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
        {"title":"Дизайн аватарок","description":"Аватарки для соцсетей.","payment":"200 руб./шт","city":"Вся Россия","age_groups":["14-15","16-17","18+"],"job_type":"online","contact":"📱 @design_bot","source":"Фриланс","date_added":datetime.now().isoformat()},
        {"title":"Набор текста","description":"Со сканов. Удалённо.","payment":"150 руб./1000 зн.","city":"Вся Россия","age_groups":["14-15","16-17","18+"],"job_type":"online","contact":"📧 text@job.ru","source":"hh.ru","date_added":datetime.now().isoformat()},
    ]
    for j in jobs:
        db.vacancies.append(j)
    db.save()
    log.info(f"Добавлено {len(jobs)} стартовых вакансий")

def get_proxy():
    return random.choice(PROXY_LIST) if PROXY_LIST else None

def classify(title: str) -> str:
    t = title.lower()
    for w in ["удалён", "онлайн", "отзыв", "модерат", "копирайт", "текст", "транскриб", "дизайн", "набор текст"]:
        if w in t: return "online"
    return "active"

async def parse_avito(city: str, pages: int = 2) -> List[Dict]:
    vacancies = []
    city_domains = {
        "москва":"moskva","санкт-петербург":"sankt-peterburg","спб":"sankt-peterburg",
        "казань":"kazan","екатеринбург":"ekaterinburg","новосибирск":"novosibirsk",
        "краснодар":"krasnodar","ростов-на-дону":"rostov-na-donu","ростов":"rostov-na-donu",
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
                                "job_type":classify(title),
                                "contact":f"📞 Ссылка на Avito:\n🔗 {link}",
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
                    "title":title,"description":f"{employer}. {resp_text[:150]}...",
                    "payment":payment,"city":city_name,"age_groups":["16-17","18+"],
                    "job_type":classify(title),
                    "contact":f"📞 Откликнуться на hh.ru:\n🔗 {url}",
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
        for city in cities:
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

async def keep_alive():
    await asyncio.sleep(60)
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://job-bot-final.onrender.com", timeout=10) as r:
                    log.info(f"Ping: {r.status}")
        except: pass
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
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="show_favorites")],
        [InlineKeyboardButton(text="📞 Поддержка", url=f"https://t.me/{SUPPORT_USERNAME.replace('@','')}")],
    ]
    if not is_paid:
        btns.insert(-2, [InlineKeyboardButton(text="💎 Премиум (149₽)", callback_data="premium_info")])
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
        await message.answer("👋 *Привет!*\nВ каком городе ищешь работу?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Москва", callback_data="setcity_Москва")],
            [InlineKeyboardButton(text="СПб", callback_data="setcity_Санкт-Петербург")],
            [InlineKeyboardButton(text="Другой город", callback_data="setcity_other")],
        ]), parse_mode="Markdown")
        await state.set_state(Onboarding.city)
    else:
        v = "∞" if u["paid"] else str(max(0, FREE_LIMIT - u["daily_views"]))
        await message.answer(f"👋 *Меню*\n📍 {u['city']} | 👤 {u['age_group']}\n💎 {'Премиум' if u['paid'] else 'Бесплатно ('+v+' сегодня)'}", reply_markup=main_menu(u["paid"]), parse_mode="Markdown")

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
    names = {"any":"Любая","online":"Удалёнка","active":"Активная"}
    await call.message.edit_text(f"✅ *Готово!*\nТип: *{names.get(jt)}*\nЖми «Смотреть вакансии»", reply_markup=main_menu(False), parse_mode="Markdown")
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
        await call.message.edit_text("🚫 *Лимит.*\n💎 Премиум — безлимит за 149 руб.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить", callback_data="buy_premium")],
            [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
        ]), parse_mode="Markdown")
        return
    vacs = db.get_vacancies(u.get("city","Москва"), u.get("age_group","16-17"), u.get("job_type","any"))
    if not vacs:
        await call.message.edit_text("😔 Нет вакансий. Смени фильтры.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔧 Сменить", callback_data="main")]]), parse_mode="Markdown")
        return
    db.increment_views(call.from_user.id)
    random.shuffle(vacs)
    to_show = vacs[:3]
    names = {"any":"Любая","online":"Удалёнка","active":"Активная"}
    resp = f"💰 *Вакансии ({names.get(u.get('job_type','any'))}) в {u.get('city')}:*\n\n"
    for i, v in enumerate(to_show, 1):
        e = "💻" if v.get("job_type")=="online" else "🏃"
        resp += f"*{i}. {e} {v['title']}*\n💵 {v['payment']}\n📝 {v['description'][:100]}...\n\n"
    v_left = max(0, FREE_LIMIT - u["daily_views"])
    resp += f"📊 Осталось: *{v_left if not u['paid'] else '∞'}*\n"
    if not u["paid"]: resp += "💎 *Премиум* — безлимит."
    kb = [
        [InlineKeyboardButton(text="🔄 Ещё", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="💎 Премиум", callback_data="premium_info")],
        [InlineKeyboardButton(text="⭐ В избранное #1", callback_data=f"fav_0")],
        [InlineKeyboardButton(text="⭐ В избранное #2", callback_data=f"fav_1")],
        [InlineKeyboardButton(text="⭐ В избранное #3", callback_data=f"fav_2")],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
    ]
    for i in range(3):
        kb.insert(-1, [InlineKeyboardButton(text=f"📞 Контакт #{i+1}", callback_data=f"contact_{i}")])
    db.get_user(call.from_user.id)["_last_shown"] = to_show
    db.save()
    await call.message.edit_text(resp, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown", disable_web_page_preview=True)

async def show_contact(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    to_show = u.get("_last_shown",[])
    if not to_show: await call.answer("Сначала посмотри вакансии"); return
    idx = int(call.data.replace("contact_",""))
    if idx >= len(to_show): await call.answer("Нет такой"); return
    v = to_show[idx]
    await call.message.answer(f"📞 *{v['title']}*\n\n{v['contact']}", parse_mode="Markdown", disable_web_page_preview=True)
    await call.answer()

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
        await call.message.edit_text("⭐ Избранное пусто. Добавляй вакансии кнопкой «В избранное».", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]), parse_mode="Markdown")
        return
    resp = "⭐ *Избранное:*\n\n"
    for i, v in enumerate(favs, 1):
        resp += f"*{i}. {v['title']}*\n💵 {v['payment']}\n📞 {v['contact'][:50]}...\n\n"
    await call.message.edit_text(resp, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]), parse_mode="Markdown", disable_web_page_preview=True)

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
    await message.answer("✅ *Готово!* Безлимит активен. Гайды всегда доступны по команде /guides", reply_markup=main_menu(True), parse_mode="Markdown")

async def guides_cmd(message: Message):
    await message.answer(SCAM_GUIDE, parse_mode="Markdown")
    await message.answer(SAMOZANYATOST_GUIDE, parse_mode="Markdown")
    await message.answer(TEMPLATES_GUIDE, parse_mode="Markdown")

async def change_city(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📍 Новый город:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Отмена", callback_data="main")]]), parse_mode="Markdown")
    await state.set_state(Onboarding.city)

async def main_handler(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    v = "∞" if u.get("paid") else str(max(0, FREE_LIMIT - u["daily_views"]))
    await call.message.edit_text(f"👋 *Меню*\n📍 {u.get('city','?')} | 👤 {u.get('age_group','?')}\n💎 {'Премиум' if u.get('paid') else 'Бесплатно ('+v+' сегодня)'}", reply_markup=main_menu(u.get("paid",False)), parse_mode="Markdown")

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
    dp.callback_query.register(change_job_type, F.data == "change_job_type")
    dp.callback_query.register(change_age, F.data == "change_age")
    dp.callback_query.register(main_handler, F.data == "main")
    dp.callback_query.register(show_vacancies, F.data == "show_vacancies")
    dp.callback_query.register(show_contact, F.data.startswith("contact_"))
    dp.callback_query.register(add_favorite, F.data.startswith("fav_"))
    dp.callback_query.register(show_favorites, F.data == "show_favorites")
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
