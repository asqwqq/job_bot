#!/usr/bin/env python3
"""
БОТ «ГДЕ ПОДРАБОТКА?» — ВЕРСИЯ 5.2 FINAL
- Парсинг Avito + hh.ru + YouDo + Rabota.ru
- Прокси подключён
- Дубликаты исключены
- Markdown без лишних слэшей
- Веб-сервер для Render
- Защита от стоп-слов и спама
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
from aiohttp import web

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8883834523:AAGEabtv8AZ84PrlEBYL4gNCo22WYQgcJ0U"
DEEPSEEK_API_KEY = "sk-5cdac197514c404ab7b10935fb2dc996"
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
HH_API_URL = "https://api.hh.ru/vacancies"
RABOTA_API_URL = "https://api.rabota.ru/vacancies"
YOUDO_URL = "https://youdo.com"
ADMIN_ID = 1827360709
SUPPORT_USERNAME = "@rabotka_support"
BOT_USERNAME = "rabotka_239_bot"
PREMIUM_PRICE = 150
FREE_LIMIT = 3
REFERRAL_BONUS_DAYS = 1
PROXY_URL = "http://RWzBHe:uWwuKX@45.10.64.86:8000"

STOP_WORDS = [
    "клад", "закладк", "кладмен", "соль", "скорость", "травк", "шишк", "бошк",
    "гашиш", "меф", "амф", "фен", "экстази", "лсд", "марк", "героин", "кокаин",
    "спайс", "снюс", "вейп", "жиж", "одноразк", "залит", "заклад", "магнит",
    "тайник", "прикоп", "кладк", "наркот", "дур", "план", "гаш", "шмал",
]

SCAM_GUIDE = "🛡 Как не попасть на мошенников\n1. Просят деньги за доступ — развод.\n2. Обещают золотые горы — реально 400-1500 руб./смена.\n3. Нет контактов — требуй телефон.\n4. Паспорт до собеседования — не отправляй.\n5. Пишут первыми — спам."

SAMOZANYATOST_GUIDE = "📄 Самозанятость с 14 лет\nСтатус с налогом 4%. Приложение «Мой налог» → регистрация → согласие родителей."

TEMPLATES_GUIDE = "📝 Шаблоны откликов\nAvito: «Здравствуйте! Заинтересовала вакансия. Мне 16 лет. Тел: [номер]»\nhh.ru: «Добрый день! [Имя], 17 лет. Ищу подработку. Контакты: [тел]»\nYouDo: «Здравствуйте! Готов выполнить задание. Тел: [номер]»"

CATEGORY_NAMES = {
    "any": "Любая", "dog": "🐕 Выгул собак", "courier": "📦 Курьер",
    "promo": "📢 Промоутер", "freelance": "💻 Фриланс",
    "cleaning": "🧹 Уборка", "tutor": "🎓 Репетиторство"
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

def esc_md(text: str) -> str:
    if not text: return ""
    for ch in ['*', '_', '`', '[']:
        text = text.replace(ch, '\\' + ch)
    return text

class Database:
    def __init__(self, path: str = "jobs_db.json"):
        self.path = path
        self.users: Dict[int, Dict] = {}
        self.vacancies: List[Dict] = []
        self.ratings: Dict[str, Dict] = {}
        self.reports: Dict[str, List[int]] = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.users = {int(k): v for k, v in data.get("users", {}).items()}
                self.vacancies = data.get("vacancies", [])
                self.ratings = data.get("ratings", {})
                self.reports = data.get("reports", {})
            log.info(f"База: {len(self.users)} польз., {len(self.vacancies)} вакансий")
        except:
            self.users = {}; self.vacancies = []; self.ratings = {}; self.reports = {}
            log.info("База пустая")

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"users": self.users, "vacancies": self.vacancies, "ratings": self.ratings, "reports": self.reports}, f, ensure_ascii=False, indent=2)

    def get_user(self, uid: int) -> Dict:
        if uid not in self.users:
            self.users[uid] = {
                "city": None, "age_group": None, "job_type": "any", "category": "any",
                "paid": False, "paid_until": None, "daily_views": 0, "last_view_date": None,
                "favorites": [], "referral_code": None, "referred_by": None,
                "referral_count": 0, "notify": False, "joined": datetime.now().isoformat(),
                "_last_shown": [], "_last_action": 0, "_action_count": 0
            }
        return self.users[uid]

    def check_spam(self, uid: int) -> bool:
        user = self.get_user(uid)
        now = datetime.now().timestamp()
        if now - user["_last_action"] > 60: user["_action_count"] = 0; user["_last_action"] = now
        user["_action_count"] += 1; self.save()
        return user["_action_count"] <= 10

    def can_view(self, uid: int) -> bool:
        user = self.get_user(uid)
        if self.is_premium(uid): return True
        today = datetime.now().date().isoformat()
        if user["last_view_date"] != today: user["daily_views"] = 0; user["last_view_date"] = today; self.save()
        return user["daily_views"] < FREE_LIMIT

    def is_premium(self, uid: int) -> bool:
        user = self.get_user(uid)
        return user["paid"] or (user["paid_until"] and datetime.fromisoformat(user["paid_until"]) > datetime.now())

    def increment_views(self, uid: int):
        user = self.get_user(uid); user["daily_views"] += 1; user["last_view_date"] = datetime.now().date().isoformat(); self.save()

    def set_paid(self, uid: int, days: int = 365):
        user = self.get_user(uid); user["paid"] = True; user["paid_until"] = (datetime.now() + timedelta(days=days)).isoformat(); user["notify"] = True; self.save()

    def add_premium_days(self, uid: int, days: int):
        user = self.get_user(uid)
        if user["paid_until"] and datetime.fromisoformat(user["paid_until"]) > datetime.now():
            user["paid_until"] = (datetime.fromisoformat(user["paid_until"]) + timedelta(days=days)).isoformat()
        else: user["paid_until"] = (datetime.now() + timedelta(days=days)).isoformat()
        user["notify"] = True; self.save()

    def set_job_type(self, uid: int, jt: str): self.get_user(uid)["job_type"] = jt; self.get_user(uid)["category"] = "any"; self.save()
    def set_category(self, uid: int, cat: str): self.get_user(uid)["category"] = cat; self.save()
    def set_city(self, uid: int, city: str): self.get_user(uid)["city"] = city; self.save()
    def set_age(self, uid: int, age: str): self.get_user(uid)["age_group"] = age; self.save()

    def reset_user(self, uid: int):
        user = self.get_user(uid)
        user.update({"daily_views": 0, "paid": True, "city": "Москва", "age_group": "16-17", "job_type": "any", "category": "any"})
        user["paid_until"] = (datetime.now() + timedelta(days=365)).isoformat(); self.save()

    def generate_referral_code(self, uid: int) -> str:
        user = self.get_user(uid)
        if not user["referral_code"]: user["referral_code"] = f"ref{uid}"; self.save()
        return user["referral_code"]

    def process_referral(self, uid: int, code: str) -> bool:
        if code == f"ref{uid}": return False
        for u_id, u in self.users.items():
            if u.get("referral_code") == code:
                u["referral_count"] = u.get("referral_count", 0) + 1
                self.get_user(uid)["referred_by"] = u_id
                self.add_premium_days(u_id, REFERRAL_BONUS_DAYS); self.add_premium_days(uid, REFERRAL_BONUS_DAYS)
                self.save(); return True
        return False

    def add_favorite(self, uid: int, v: Dict):
        user = self.get_user(uid)
        if len(user["favorites"]) < 20: user["favorites"].append(v); self.save(); return True
        return False

    def get_favorites(self, uid: int) -> List[Dict]: return self.get_user(uid)["favorites"]

    def rate_employer(self, contact: str, rating: int):
        if contact not in self.ratings: self.ratings[contact] = {"up": 0, "down": 0}
        if rating == 1: self.ratings[contact]["up"] += 1
        else: self.ratings[contact]["down"] += 1
        self.save()

    def report_vacancy(self, vid: str, uid: int) -> int:
        if vid not in self.reports: self.reports[vid] = []
        if uid not in self.reports[vid]: self.reports[vid].append(uid)
        self.save(); return len(self.reports[vid])

    def get_employer_rating(self, contact: str) -> str:
        r = self.ratings.get(contact, {"up": 0, "down": 0})
        total = r["up"] + r["down"]
        if total == 0: return "Нет оценок"
        score = r["up"] - r["down"]
        if score >= 3: return f"Надёжный ({r['up']}/{total})"
        if score <= -2: return f"Много жалоб ({r['up']}/{total})"
        return f"Нормальный ({r['up']}/{total})"

    def get_vacancies(self, city: str, age_group: str, job_type: str = "any", category: str = "any") -> List[Dict]:
        city_lower = city.lower().strip(); results = []
        for v in self.vacancies:
            if v.get("hidden"): continue
            vc = v.get("city","").lower()
            if not (city_lower in vc or vc in city_lower or vc == "вся россия"): continue
            if age_group not in v.get("age_groups", []): continue
            if job_type != "any" and job_type != v.get("job_type","active"): continue
            if category != "any" and category != v.get("category","any"): continue
            results.append(v)
        return results

    def vacancy_exists(self, title: str, city: str, contact: str) -> bool:
        title_lower = title.strip().lower(); city_lower = city.strip().lower(); contact_lower = contact.strip().lower()
        for v in self.vacancies:
            if (v.get("title","").strip().lower() == title_lower and 
                v.get("city","").strip().lower() == city_lower and
                v.get("contact","").strip().lower() == contact_lower):
                return True
        return False

    def add_vacancy(self, vacancy: Dict):
        if has_stop_words(vacancy.get("title","") + " " + vacancy.get("description","")): return
        if self.vacancy_exists(vacancy.get("title",""), vacancy.get("city",""), vacancy.get("contact","")): return
        self.vacancies.append(vacancy); self.save()

    def stats(self):
        total = len(self.users); paid = sum(1 for uid in self.users if self.is_premium(uid))
        cities = {}
        for u in self.users.values(): c = u.get("city", "Не указан"); cities[c] = cities.get(c, 0) + 1
        return total, paid, len(self.vacancies), cities

db = Database()

def has_stop_words(text: str) -> bool: return any(sw in text.lower() for sw in STOP_WORDS)
def validate_city(text: str) -> bool: return bool(re.match(r'^[а-яёА-ЯЁ\s\-]{1,30}$', text.strip()))

def classify_category(title: str) -> str:
    t = title.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if any(kw in t for kw in kws): return cat
    return "promo"

def classify_job_type(title: str) -> str:
    if any(w in title.lower() for w in ["удалён","онлайн","отзыв","модерат","копирайт","текст","транскриб","дизайн","набор"]): return "online"
    return "active"

async def parse_avito(city: str) -> List[Dict]:
    vacancies = []
    city_domains = {"москва":"moskva","санкт-петербург":"sankt-peterburg","спб":"sankt-peterburg","казань":"kazan","екатеринбург":"ekaterinburg","новосибирск":"novosibirsk"}
    domain = city_domains.get(city.lower().strip(), city.lower().strip().replace(" ","_"))
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"https://www.avito.ru/{domain}?q=подработка+для+школьников", headers={"User-Agent":"Mozilla/5.0"}, proxy=PROXY_URL, timeout=20) as r:
                if r.status != 200: return []
                html = await r.text()
        soup = BeautifulSoup(html, "html.parser")
        for item in soup.find_all("div", {"data-marker":"item"})[:3]:
            try:
                t_e = item.find("h3",{"itemprop":"name"}); p_e = item.find("meta",{"itemprop":"price"}); l_e = item.find("a",{"data-marker":"item-title"})
                title = t_e.text.strip() if t_e else ""; price = p_e.get("content","") if p_e else ""; link = "https://www.avito.ru"+l_e.get("href","") if l_e else ""
                if title and link:
                    vacancies.append({"title":title,"description":f"Вакансия с Avito","payment":f"{price} руб." if price else "Договорная","city":city,"age_groups":["14-15","16-17","18+"],"job_type":classify_job_type(title),"category":classify_category(title),"contact":f"🔗 {link}","source":"Avito","date_added":datetime.now().isoformat()})
            except: continue
    except: pass
    return vacancies

async def parse_hh(city_name: str, city_code: int = 1) -> List[Dict]:
    vacancies = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(HH_API_URL, params={"text":"подработка OR школьник OR студент","area":city_code,"experience":"noExperience","employment":"part","per_page":5,"page":0}, proxy=PROXY_URL, timeout=15) as r:
                if r.status != 200: return []
                data = await r.json()
        for item in data.get("items",[]):
            try:
                title = item.get("name",""); url = item.get("alternate_url","")
                salary = item.get("salary")
                payment = f"{salary.get('from','?')}-{salary.get('to','?')} {salary.get('currency','руб.')}" if salary else "Не указана"
                resp_text = re.sub(r'<[^>]+>','',item.get("snippet",{}).get("responsibility","") or "")
                if title and url:
                    vacancies.append({"title":title,"description":f"{item.get('employer',{}).get('name','')}. {resp_text[:150]}","payment":payment,"city":city_name,"age_groups":["16-17","18+"],"job_type":classify_job_type(title),"category":classify_category(title),"contact":f"🔗 {url}","source":"hh.ru","date_added":datetime.now().isoformat()})
            except: continue
    except: pass
    return vacancies

async def parse_rabota(city_name: str) -> List[Dict]:
    vacancies = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{RABOTA_API_URL}?query=подработка+школьник&region={city_name}&limit=5", timeout=15) as r:
                if r.status != 200: return []
                data = await r.json()
        for item in data.get("vacancies",[])[:5]:
            try:
                title = item.get("title",""); url = item.get("url","")
                if title and url:
                    vacancies.append({"title":title,"description":item.get("description","")[:200],"payment":item.get("salary","Не указана"),"city":city_name,"age_groups":["16-17","18+"],"job_type":classify_job_type(title),"category":classify_category(title),"contact":f"🔗 {url}","source":"Rabota.ru","date_added":datetime.now().isoformat()})
            except: continue
    except: pass
    return vacancies

async def parse_youdо(city_name: str) -> List[Dict]:
    vacancies = []
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{YOUDO_URL}/{city_name.lower().replace(' ','-')}", headers={"User-Agent":"Mozilla/5.0"}, proxy=PROXY_URL, timeout=20) as r:
                if r.status != 200: return []
                html = await r.text()
        soup = BeautifulSoup(html, "html.parser")
        for task in soup.find_all("div", class_="task")[:3]:
            try:
                title = task.find("a", class_="task-title"); price = task.find("div", class_="task-price")
                if title:
                    vacancies.append({"title":title.text.strip(),"description":"Задание на YouDo","payment":price.text.strip() if price else "Договорная","city":city_name,"age_groups":["14-15","16-17","18+"],"job_type":classify_job_type(title.text),"category":classify_category(title.text),"contact":f"🔗 {YOUDO_URL}{title.get('href','')}","source":"YouDo","date_added":datetime.now().isoformat()})
            except: continue
    except: pass
    return vacancies

async def background_parsing():
    cities = ["Москва","Санкт-Петербург","Казань","Екатеринбург","Новосибирск"]
    codes = {"Москва":1,"Санкт-Петербург":2,"Казань":88,"Екатеринбург":3,"Новосибирск":4}
    while True:
        log.info("Парсинг запущен")
        for city in cities:
            for parser in [parse_avito, parse_rabota, parse_youdо]:
                try:
                    for v in await parser(city): db.add_vacancy(v)
                except Exception as e: log.error(f"{parser.__name__} {city}: {e}")
            try:
                for v in await parse_hh(city, codes.get(city,1)): db.add_vacancy(v)
            except Exception as e: log.error(f"hh {city}: {e}")
            await asyncio.sleep(2)
        db.vacancies = [v for v in db.vacancies if datetime.fromisoformat(v["date_added"]) > datetime.now()-timedelta(days=14)]
        if len(db.vacancies) > 500: db.vacancies = db.vacancies[-500:]
        db.save()
        log.info(f"Парсинг завершён. Вакансий: {len(db.vacancies)}")
        await asyncio.sleep(30*60)

async def daily_notifications(bot: Bot):
    while True:
        await asyncio.sleep(60)
        if datetime.now().hour == 10 and datetime.now().minute == 0:
            for uid in list(db.users.keys())[:50]:
                if db.is_premium(uid):
                    u = db.get_user(uid)
                    if u.get("notify") and u.get("city"):
                        try: await bot.send_message(uid, f"🔔 Новые вакансии в {u['city']}!\nЖми /start.")
                        except: pass
            await asyncio.sleep(60)

async def handle_health(request): return web.Response(text="OK")

async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health); app.router.add_get("/health", handle_health)
    runner = web.AppRunner(app); await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8080).start()
    log.info("Веб-сервер на 8080")

class Onboarding(StatesGroup):
    city = State(); age = State(); job_type = State(); category = State()

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
    if not is_premium: btns.insert(-3, [InlineKeyboardButton(text="💎 Премиум (149₽)", callback_data="premium_info")])
    return InlineKeyboardMarkup(inline_keyboard=btns)

def job_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Любая", callback_data="jobtype_any")],
        [InlineKeyboardButton(text="💻 Удалёнка", callback_data="jobtype_online")],
        [InlineKeyboardButton(text="🏃 Активная", callback_data="jobtype_active")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="main")],
    ])

def category_keyboard(job_type: str = "any") -> InlineKeyboardMarkup:
    if job_type == "online": cats = [("💰 Любая", "any"), ("💻 Фриланс", "freelance"), ("🎓 Репетиторство", "tutor")]
    elif job_type == "active": cats = [("💰 Любая", "any"), ("🐕 Выгул собак", "dog"), ("📦 Курьер", "courier"), ("📢 Промоутер", "promo"), ("🧹 Уборка", "cleaning")]
    else: cats = [("💰 Любая", "any"), ("🐕 Выгул собак", "dog"), ("📦 Курьер", "courier"), ("📢 Промоутер", "promo"), ("💻 Фриланс", "freelance"), ("🧹 Уборка", "cleaning"), ("🎓 Репетиторство", "tutor")]
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

async def cmd_start(message: Message, state: FSMContext):
    u = db.get_user(message.from_user.id)
    args = message.text.split()
    if len(args) > 1 and db.process_referral(message.from_user.id, args[1]):
        await message.answer(f"🎉 Реферальный код активирован! +{REFERRAL_BONUS_DAYS} день Премиума!")
    if not u["city"]:
        await message.answer("👋 Привет!\nВ каком городе ищешь работу?", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Москва", callback_data="setcity_Москва")],
            [InlineKeyboardButton(text="СПб", callback_data="setcity_Санкт-Петербург")],
            [InlineKeyboardButton(text="Другой город", callback_data="setcity_other")],
        ]))
        await state.set_state(Onboarding.city)
    else:
        prem = db.is_premium(message.from_user.id)
        v = "∞" if prem else str(max(0, FREE_LIMIT - u["daily_views"]))
        await message.answer(f"👋 Меню\n📍 {u['city']} | 👤 {u['age_group']}\n📂 {CATEGORY_NAMES.get(u.get('category','any'))}\n💎 {'Премиум' if prem else 'Бесплатно ('+v+' сегодня)'}", reply_markup=main_menu(prem))

async def set_city(call: CallbackQuery, state: FSMContext):
    city = call.data.replace("setcity_","")
    if city == "other": await call.message.edit_text("📍 Напиши город (только русские буквы):"); await state.set_state(Onboarding.city); return
    db.set_city(call.from_user.id, city)
    await call.message.edit_text(f"📍 {city}\nУкажи возраст:", reply_markup=age_keyboard()); await state.set_state(Onboarding.age)

async def process_city(message: Message, state: FSMContext):
    city = message.text.strip()
    if not validate_city(city) or has_stop_words(city): await message.answer("❌ Только русские буквы, без цифр. Попробуй ещё раз:"); return
    db.set_city(message.from_user.id, city)
    await message.answer(f"📍 {city}\nУкажи возраст:", reply_markup=age_keyboard()); await state.set_state(Onboarding.age)

async def set_age(call: CallbackQuery, state: FSMContext):
    db.set_age(call.from_user.id, call.data.replace("setage_",""))
    await call.message.edit_text("✅ Выбери тип работы:", reply_markup=job_type_keyboard()); await state.set_state(Onboarding.job_type)

async def set_job_type(call: CallbackQuery, state: FSMContext):
    jt = call.data.replace("jobtype_",""); db.set_job_type(call.from_user.id, jt)
    await call.message.edit_text("✅ Выбери категорию:", reply_markup=category_keyboard(jt)); await state.set_state(Onboarding.category)

async def set_category(call: CallbackQuery, state: FSMContext):
    db.set_category(call.from_user.id, call.data.replace("cat_",""))
    await call.message.edit_text("✅ Готово!\nЖми «Смотреть вакансии»", reply_markup=main_menu(db.is_premium(call.from_user.id))); await state.clear()

async def change_job_type(call: CallbackQuery): await call.message.edit_text("🔧 Тип работы:", reply_markup=job_type_keyboard())
async def change_category(call: CallbackQuery): await call.message.edit_text("📂 Категория:", reply_markup=category_keyboard(db.get_user(call.from_user.id).get("job_type","any")))
async def change_age(call: CallbackQuery, state: FSMContext): await call.message.edit_text("👤 Возраст:", reply_markup=age_keyboard()); await state.set_state(Onboarding.age)

async def show_vacancies(call: CallbackQuery):
    if not db.check_spam(call.from_user.id): await call.answer("⚠️ Слишком много запросов. Подожди."); return
    u = db.get_user(call.from_user.id)
    if not u["city"]: await call.message.edit_text("Сначала /start", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]])); return
    if not db.can_view(call.from_user.id):
        await call.message.edit_text("🚫 Лимит.\n💎 Премиум — безлимит за 149 руб.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💎 Купить", callback_data="buy_premium")], [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
        ])); return
    vacs = db.get_vacancies(u.get("city","Москва"), u.get("age_group","16-17"), u.get("job_type","any"), u.get("category","any"))
    if not vacs: await call.message.edit_text("😔 Нет вакансий.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]])); return
    db.increment_views(call.from_user.id)
    random.shuffle(vacs); to_show = vacs[:3]
    db.get_user(call.from_user.id)["_last_shown"] = to_show; db.save()
    resp = f"💰 Вакансии в {esc_md(u.get('city','?'))}\n📂 {CATEGORY_NAMES.get(u.get('category','any'))} | 👤 {u.get('age_group')}\n\n"
    for i, v in enumerate(to_show, 1):
        e = "💻" if v.get("job_type")=="online" else "🏃"
        resp += f"{i}. {e} {esc_md(v['title'])}\n💵 {esc_md(v['payment'])} | {esc_md(v['source'])}\n\n"
    v_left = max(0, FREE_LIMIT - u["daily_views"])
    resp += f"📊 Осталось: {v_left if not db.is_premium(call.from_user.id) else '∞'}"
    kb = [
        [InlineKeyboardButton(text="🔄 Ещё", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="ℹ️ #1", callback_data="detail_0"), InlineKeyboardButton(text="📞 #1", callback_data="contact_0"), InlineKeyboardButton(text="⚠️ Жалоба #1", callback_data="report_0")],
        [InlineKeyboardButton(text="ℹ️ #2", callback_data="detail_1"), InlineKeyboardButton(text="📞 #2", callback_data="contact_1"), InlineKeyboardButton(text="⚠️ Жалоба #2", callback_data="report_1")],
        [InlineKeyboardButton(text="ℹ️ #3", callback_data="detail_2"), InlineKeyboardButton(text="📞 #3", callback_data="contact_2"), InlineKeyboardButton(text="⚠️ Жалоба #3", callback_data="report_2")],
        [InlineKeyboardButton(text="⭐ Избранное", callback_data="fav_menu"), InlineKeyboardButton(text="👍👎 Оценить", callback_data="rate_menu")],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")],
    ]
    await call.message.edit_text(resp, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), disable_web_page_preview=True)

async def show_detail(call: CallbackQuery):
    to_show = db.get_user(call.from_user.id).get("_last_shown",[])
    idx = int(call.data.replace("detail_",""))
    if idx >= len(to_show): await call.answer("Нет"); return
    v = to_show[idx]
    resp = f"{esc_md(v['title'])}\n\n📝 {esc_md(v['description'])}\n\n💵 {esc_md(v['payment'])}\n📍 {esc_md(v.get('city','?'))}\n🔹 {esc_md(v.get('source','?'))}\n\n📞 {esc_md(v.get('contact',''))}"
    await call.message.answer(resp, disable_web_page_preview=True)
    await call.answer()

async def show_contact(call: CallbackQuery):
    to_show = db.get_user(call.from_user.id).get("_last_shown",[])
    idx = int(call.data.replace("contact_",""))
    if idx >= len(to_show): await call.answer("Нет"); return
    await call.message.answer(f"📞 {esc_md(to_show[idx]['title'])}\n\n{to_show[idx]['contact']}", disable_web_page_preview=True)
    await call.answer()

async def report_vacancy(call: CallbackQuery):
    to_show = db.get_user(call.from_user.id).get("_last_shown",[])
    idx = int(call.data.replace("report_",""))
    if idx >= len(to_show): await call.answer("Нет"); return
    v = to_show[idx]; count = db.report_vacancy(f"{v.get('title','')}_{v.get('city','')}", call.from_user.id)
    if count >= 3: v["hidden"] = True; db.save(); await call.answer("⚠️ Вакансия скрыта.")
    else: await call.answer(f"⚠️ Жалоба принята ({count}/3).")

async def rate_employer(call: CallbackQuery):
    to_show = db.get_user(call.from_user.id).get("_last_shown",[])
    if "rateup_" in call.data: db.rate_employer(to_show[int(call.data.replace("rateup_",""))].get("contact",""), 1)
    else: db.rate_employer(to_show[int(call.data.replace("ratedown_",""))].get("contact",""), -1)
    await call.answer("✅ Спасибо!")

async def add_favorite(call: CallbackQuery):
    to_show = db.get_user(call.from_user.id).get("_last_shown",[])
    if db.add_favorite(call.from_user.id, to_show[int(call.data.replace("fav_",""))]): await call.answer("⭐ Добавлено!")
    else: await call.answer("🚫 Заполнено")

async def fav_menu(call: CallbackQuery):
    await call.message.edit_text("⭐ Выбери:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ #1", callback_data="fav_0"), InlineKeyboardButton(text="⭐ #2", callback_data="fav_1"), InlineKeyboardButton(text="⭐ #3", callback_data="fav_2")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="show_vacancies")],
    ]))

async def rate_menu(call: CallbackQuery):
    await call.message.edit_text("👍👎 Выбери:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👍 #1", callback_data="rateup_0"), InlineKeyboardButton(text="👎 #1", callback_data="ratedown_0")],
        [InlineKeyboardButton(text="👍 #2", callback_data="rateup_1"), InlineKeyboardButton(text="👎 #2", callback_data="ratedown_1")],
        [InlineKeyboardButton(text="👍 #3", callback_data="rateup_2"), InlineKeyboardButton(text="👎 #3", callback_data="ratedown_2")],
        [InlineKeyboardButton(text="⬅ Назад", callback_data="show_vacancies")],
    ]))

async def show_favorites(call: CallbackQuery):
    favs = db.get_favorites(call.from_user.id)
    if not favs: await call.message.edit_text("⭐ Пусто.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]])); return
    resp = "⭐ Избранное:\n\n" + "\n".join([f"{i}. {esc_md(v['title'])}\n💵 {esc_md(v['payment'])}\n" for i,v in enumerate(favs,1)])
    await call.message.edit_text(resp, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]), disable_web_page_preview=True)

async def referral_info(call: CallbackQuery):
    code = db.generate_referral_code(call.from_user.id)
    await call.message.edit_text(f"👥 Рефералка\nПриведи друга — +{REFERRAL_BONUS_DAYS} день Премиума!\n\nСсылка:\nhttps://t.me/{BOT_USERNAME}?start={code}\n\nПриглашено: {db.get_user(call.from_user.id).get('referral_count',0)}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", switch_inline_query=f"https://t.me/{BOT_USERNAME}?start={code}")],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
    ]), disable_web_page_preview=True)

async def premium_info(call: CallbackQuery):
    await call.message.edit_text(f"💎 Премиум\nБезлимит, избранное, уведомления, гайды.\n💰 {PREMIUM_PRICE}⭐ (~149 руб.)\nНавсегда.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💎 Купить ({PREMIUM_PRICE}⭐)", callback_data="buy_premium")],
        [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
    ]))

async def buy_premium(call: CallbackQuery):
    await bot.send_invoice(chat_id=call.from_user.id, title="Премиум", description="Безлимит навсегда", payload="prem", provider_token="", currency="XTR", prices=[LabeledPrice(label="Доступ", amount=PREMIUM_PRICE)], start_parameter="prem")

async def pre_checkout(pq: PreCheckoutQuery): await pq.answer(ok=True)

async def payment_success(message: Message):
    db.set_paid(message.from_user.id)
    for g in [SCAM_GUIDE, SAMOZANYATOST_GUIDE, TEMPLATES_GUIDE]: await message.answer(g)
    await message.answer("✅ Готово!", reply_markup=main_menu(True))

async def guides_cmd(message: Message):
    for g in [SCAM_GUIDE, SAMOZANYATOST_GUIDE, TEMPLATES_GUIDE]: await message.answer(g)

async def support_cmd(message: Message): await message.answer(f"📞 Поддержка: {SUPPORT_USERNAME}\nОтветим в течение 24 часов.")

async def change_city(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📍 Новый город:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Отмена", callback_data="main")]]))
    await state.set_state(Onboarding.city)

async def main_handler(call: CallbackQuery):
    u = db.get_user(call.from_user.id); prem = db.is_premium(call.from_user.id)
    v = "∞" if prem else str(max(0, FREE_LIMIT - u["daily_views"]))
    await call.message.edit_text(f"👋 Меню\n📍 {u.get('city','?')} | 👤 {u.get('age_group','?')}\n💎 {'Премиум' if prem else 'Бесплатно ('+v+' сегодня)'}", reply_markup=main_menu(prem))

async def stats_cmd(message: Message):
    if message.from_user.id == ADMIN_ID:
        t, p, v, cities = db.stats()
        resp = f"👥 {t} | 💎 {p} | 📋 {v}\n📍 " + "\n📍 ".join([f"{c}: {n}" for c,n in sorted(cities.items(), key=lambda x: -x[1])[:10]])
        await message.answer(resp)

async def reset_cmd(message: Message):
    if message.from_user.id == ADMIN_ID: db.reset_user(message.from_user.id); await message.answer("✅ Сброшено.")

async def main():
    log.info("БОТ ЗАПУСКАЕТСЯ")
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(stats_cmd, Command("stats"))
    dp.message.register(reset_cmd, Command("reset"))
    dp.message.register(guides_cmd, Command("guides"))
    dp.message.register(support_cmd, Command("support"))
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
    dp.callback_query.register(report_vacancy, F.data.startswith("report_"))
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
    asyncio.create_task(background_parsing())
    asyncio.create_task(daily_notifications(bot))
    asyncio.create_task(run_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
