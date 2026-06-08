#!/usr/bin/env python3
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
    jobs = [
        {"title": "Раздача листовок", "description": "Москва, ул. Тверская", "payment": "500 руб.", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "@job_msk_bot", "source": "Прямое", "date_added": datetime.now().isoformat()},
        {"title": "Курьер на велосипеде", "description": "Доставка еды, свободный график", "payment": "3000 руб./день", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "@courier_msk", "source": "Прямое", "date_added": datetime.now().isoformat()},
        {"title": "Написание отзывов", "description": "Удалённо, WB/Ozon", "payment": "100 руб./отзыв", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "online", "contact": "@reviews_bot", "source": "Прямое", "date_added": datetime.now().isoformat()},
        {"title": "Модератор чата", "description": "Удалённо, 2-3 часа в день", "payment": "8000 руб./мес", "city": "Москва", "age_groups": ["16-17", "18+"], "job_type": "online", "contact": "hr@shop.ru", "source": "Прямое", "date_added": datetime.now().isoformat()},
        {"title": "Промоутер в ТЦ", "description": "Раздача образцов в ТЦ", "payment": "1200 руб.", "city": "Санкт-Петербург", "age_groups": ["16-17", "18+"], "job_type": "active", "contact": "@spb_promo", "source": "Прямое", "date_added": datetime.now().isoformat()},
        {"title": "Выгул собак", "description": "2 раза в день, центр", "payment": "500 руб./выгул", "city": "Москва", "age_groups": ["14-15", "16-17", "18+"], "job_type": "active", "contact": "@dogwalker", "source": "Прямое", "date_added": datetime.now().isoformat()},
    ]
    for j in jobs:
        db.vacancies.append(j)
    db.save()
    log.info(f"Добавлено {len(jobs)} тестовых вакансий")

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
    for w in ["удалён", "онлайн", "отзыв", "модерат", "копирайт", "текст"]:
        if w in t:
            return "online"
    return "active"

async def parse_avito(city: str, pages: int = 2) -> List[Dict]:
    return []

async def parse_hh(city_name: str, city_code: int = 1) -> List[Dict]:
    return []

async def background_parsing():
    while True:
        await asyncio.sleep(3 * 60 * 60)

class Onboarding(StatesGroup):
    city = State()
    age = State()
    job_type = State()

def main_menu(is_paid: bool = False) -> InlineKeyboardMarkup:
    btns = [
        [InlineKeyboardButton(text="💰 Смотреть вакансии", callback_data="show_vacancies")],
        [InlineKeyboardButton(text="🔧 Выбрать тип работы", callback_data="change_job_type")],
        [InlineKeyboardButton(text="📍 Сменить город", callback_data="change_city")],
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

async def cmd_start(message: Message, state: FSMContext):
    u = db.get_user(message.from_user.id)
    if not u["city"]:
        await message.answer(
            "👋 *Привет!*\nВ каком городе ищешь работу?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Москва", callback_data="setcity_Москва")],
                [InlineKeyboardButton(text="СПб", callback_data="setcity_Санкт-Петербург")],
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
    db.get_user(call.from_user.id)["city"] = city
    db.save()
    await call.message.edit_text(
        f"📍 *{city}*\nУкажи возраст:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="14-15", callback_data="setage_14-15")],
            [InlineKeyboardButton(text="16-17", callback_data="setage_16-17")],
            [InlineKeyboardButton(text="18+", callback_data="setage_18+")],
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.age)

async def process_city(message: Message, state: FSMContext):
    db.get_user(message.from_user.id)["city"] = message.text.strip()
    db.save()
    await message.answer(
        f"📍 *{message.text}*\nУкажи возраст:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="14-15", callback_data="setage_14-15")],
            [InlineKeyboardButton(text="16-17", callback_data="setage_16-17")],
            [InlineKeyboardButton(text="18+", callback_data="setage_18+")],
        ]),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.age)

async def set_age(call: CallbackQuery, state: FSMContext):
    age = call.data.replace("setage_", "")
    db.get_user(call.from_user.id)["age_group"] = age
    db.save()
    await call.message.edit_text(
        f"✅ *Возраст: {age}*\nВыбери тип работы:",
        reply_markup=job_type_keyboard(),
        parse_mode="Markdown"
    )
    await state.set_state(Onboarding.job_type)

async def set_job_type(call: CallbackQuery, state: FSMContext):
    jt = call.data.replace("jobtype_", "")
    db.get_user(call.from_user.id)["job_type"] = jt
    db.save()
    names = {"any": "Любая", "online": "Удалёнка", "active": "Активная"}
    await call.message.edit_text(
        f"✅ *Готово!*\nТип: *{names.get(jt)}*\nЖми «Смотреть вакансии»",
        reply_markup=main_menu(False),
        parse_mode="Markdown"
    )
    await state.clear()

async def change_job_type(call: CallbackQuery):
    await call.message.edit_text(
        "🔧 *Тип работы:*",
        reply_markup=job_type_keyboard(),
        parse_mode="Markdown"
    )

async def show_vacancies(call: CallbackQuery):
    u = db.get_user(call.from_user.id)
    if not u["city"]:
        await call.message.edit_text(
            "Сначала /start",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]])
        )
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
            "😔 Нет вакансий. Попробуй позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Меню", callback_data="main")]]),
            parse_mode="Markdown"
        )
        return
    db.increment_views(call.from_user.id)
    random.shuffle(vacs)
    names = {"any": "Любая", "online": "Удалёнка", "active": "Активная"}
    resp = f"💰 *Вакансии ({names.get(u.get('job_type','any'))}) в {u.get('city')}:*\n\n"
    for i, v in enumerate(vacs[:3], 1):
        e = "💻" if v.get("job_type") == "online" else "🏃"
        resp += f"*{i}. {e} {v['title']}*\n💵 {v['payment']}\n📞 {v['contact']}\n\n"
    v_left = max(0, FREE_LIMIT - u["daily_views"])
    resp += f"📊 Осталось: *{v_left if not u['paid'] else '∞'}*\n"
    if not u["paid"]:
        resp += "💎 *Премиум* — безлимит."
    await call.message.edit_text(
        resp,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Ещё", callback_data="show_vacancies")],
            [InlineKeyboardButton(text="💎 Премиум", callback_data="premium_info")],
            [InlineKeyboardButton(text="⬅ Меню", callback_data="main")]
        ]),
        parse_mode="Markdown",
        disable_web_page_preview=True
    )

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
    await message.answer(
        "💎 *Готово!* Безлимит активен.",
        reply_markup=main_menu(True),
        parse_mode="Markdown"
    )

async def change_city(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text(
        "📍 Новый город:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Отмена", callback_data="main")]]),
        parse_mode="Markdown"
    )
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

async def main():
    log.info("БОТ ЗАПУСКАЕТСЯ")
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.register(cmd_start, Command("start"))
    dp.message.register(stats_cmd, Command("stats"))
    dp.callback_query.register(set_city, F.data.startswith("setcity_"))
    dp.message.register(process_city, Onboarding.city)
    dp.callback_query.register(set_age, F.data.startswith("setage_"))
    dp.callback_query.register(set_job_type, F.data.startswith("jobtype_"))
    dp.callback_query.register(change_job_type, F.data == "change_job_type")
    dp.callback_query.register(main_handler, F.data == "main")
    dp.callback_query.register(show_vacancies, F.data == "show_vacancies")
    dp.callback_query.register(change_city, F.data == "change_city")
    dp.callback_query.register(premium_info, F.data == "premium_info")
    dp.callback_query.register(buy_premium, F.data == "buy_premium")
    dp.pre_checkout_query.register(pre_checkout)
    dp.message.register(payment_success, F.successful_payment)
    global bot
    bot = Bot(token=BOT_TOKEN)
    seed_vacancies()
    asyncio.create_task(background_parsing())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
