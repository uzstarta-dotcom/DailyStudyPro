import os
import sqlite3
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InputFile
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler

BOT_TOKEN = "7801099090:AAEtKoIfva3E-woANtinFJvmVROJFpEGioY"
ADMIN_ID = [5693207803,5605878894]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler()
# ======================================
#   DATABASE
# ======================================

db = sqlite3.connect("database.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    name TEXT,
    subjects TEXT
)
""")

# done jadvaliga "duration" ustuni (daqiqada) qo'shildi
cursor.execute("""
CREATE TABLE IF NOT EXISTS done (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    photo_path TEXT,
    timestamp TEXT,
    duration INTEGER DEFAULT 0
)
""")

db.commit()

def get_all_user_ids():
    cursor.execute("SELECT DISTINCT user_id FROM users")  # users - foydalanuvchilar saqlangan jadval
    return [row[0] for row in cursor.fetchall()]
# ======================================
#   STATES
# ======================================

class Form(StatesGroup):
    waiting_name = State()
    waiting_subjects = State()
    adding_subject = State()
    removing_subject = State()
    waiting_done_photo = State()
    waiting_done_duration = State()   # yangi holat: dars davomiyligi so‘rash uchun

# ======================================
#   MAIN MENU
# ======================================

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📅 Reja")],[KeyboardButton(text="✔️ Done")],
        [KeyboardButton(text="📊 Statistika")],[KeyboardButton(text="📆 Haftalik hisobot")],
        [KeyboardButton(text="📝 Fan qo‘shish")],[KeyboardButton(text="❌ Fan o‘chirish")],
        [KeyboardButton(text="📩 Adminga xabar")]
    ],
    resize_keyboard=True
)
# Yangi holat: adminga xabar yozish uchun
class AdminMessage(StatesGroup):
    waiting_for_message = State()

# Foydalanuvchi "Adminga xabar" tugmasini bosganda
@dp.message(F.text == "📩 Adminga xabar")
async def ask_admin_message(message: Message, state: FSMContext):
    if not await check_user(message):
        return
    await message.answer("Iltimos, adminga yuboriladigan xabarni yozing.\n\nBekor qilish uchun ‘Bekor qilish’ deb yozing.", reply_markup=None)
    await state.set_state(AdminMessage.waiting_for_message)

# Foydalanuvchi xabar yozganda
@dp.message(AdminMessage.waiting_for_message)
async def send_message_to_admin(message: Message, state: FSMContext):
    if message.text.lower() == "bekor qilish":
        await message.answer("Xabar yuborish bekor qilindi.", reply_markup=main_menu)
        await state.clear()
        return

    user = message.from_user
    text_to_admin = (
        f"📩 *Foydalanuvchidan yangi xabar:*\n\n"
        f"{message.text}\n\n"
        f"👤 Foydalanuvchi: {user.full_name} (ID: {user.id})"
    )
    try:
        await bot.send_message(ADMIN_ID, text_to_admin, parse_mode="Markdown")
        await message.answer("Xabaringiz adminga yuborildi.", reply_markup=main_menu)
    except Exception as e:
        await message.answer(f"Xatolik yuz berdi: {e}", reply_markup=main_menu)

    await state.clear()

# ======================================
#   TOOLS
# ======================================

def user_exists(uid):
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (uid,))
    return cursor.fetchone() is not None

def set_user(uid, name, subjects):
    cursor.execute(
        "INSERT OR REPLACE INTO users (user_id, name, subjects) VALUES (?, ?, ?)",
        (uid, name, subjects)
    )
    db.commit()

def get_user(uid):
    cursor.execute("SELECT name, subjects FROM users WHERE user_id = ?", (uid,))
    return cursor.fetchone()

def update_subjects(uid, subjects):
    cursor.execute("UPDATE users SET subjects = ? WHERE user_id = ?", (subjects, uid))
    db.commit()

async def check_user(message: Message):
    if not user_exists(message.from_user.id):
        await message.answer("Iltimos, /start buyrug‘ini bering.")
        return False
    return True

# ======================================
#   START
# ======================================

@dp.message(Command("start"))
async def start_handler(message: Message, state: FSMContext):
    await message.answer(
        "Assalomu alaykum!\nIsmingizni kiriting:",
        reply_markup=ReplyKeyboardRemove()
    )
    await state.set_state(Form.waiting_name)


@dp.message(Form.waiting_name)
async def get_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Fanlaringizni vergul bilan yozing:")
    await state.set_state(Form.waiting_subjects)


@dp.message(Form.waiting_subjects)
async def get_subjects(message: Message, state: FSMContext):
    data = await state.get_data()
    name = data["name"]
    subjects = message.text

    set_user(message.from_user.id, name, subjects)
    await message.answer(
        f"Ma'lumotlar saqlandi!\n\nIsm: {name}\nFanlar: {subjects}\n\nMenyudan tanlang:",
        reply_markup=main_menu
    )
    await state.clear()

# ======================================
#   REJA
# ======================================

@dp.message(F.text == "📅 Reja")
async def plan_handler(message: Message):
    if not await check_user(message): return
    name, subjects = get_user(message.from_user.id)
    subjects_list = subjects.split(",")

    txt = "📅 Sizning fanlaringiz:\n"
    txt += "\n".join(f"— {s.strip()}" for s in subjects_list)

    await message.answer(txt)

# ======================================
#   STATISTIKA
# ======================================

@dp.message(F.text == "📊 Statistika")
async def stats_handler(message: Message):
    if not await check_user(message): return

    cursor.execute("SELECT COUNT(*), COALESCE(SUM(duration), 0) FROM done WHERE user_id = ?", (message.from_user.id,))
    done_count, total_duration = cursor.fetchone()

    await message.answer(
        f"📊 Statistika:\nBajarilgan darslar soni: {done_count}\nUmumiy o‘qilgan vaqt: {total_duration} daqiqa"
    )

# ======================================
#   FAN QO‘SHISH
# ======================================

@dp.message(F.text == "📝 Fan qo‘shish")
async def add_subject_btn(message: Message, state: FSMContext):
    if not await check_user(message): return
    await message.answer("Yangi fan nomini yozing:")
    await state.set_state(Form.adding_subject)

@dp.message(Form.adding_subject)
async def add_subject(message: Message, state: FSMContext):
    uid = message.from_user.id
    name, subjects = get_user(uid)
    subjects_list = [s.strip() for s in subjects.split(",")]

    subjects_list.append(message.text)
    update_subjects(uid, ", ".join(subjects_list))

    await message.answer("Fan qo‘shildi!", reply_markup=main_menu)
    await state.clear()

# ======================================
#   FAN O‘CHIRISH
# ======================================

@dp.message(F.text == "❌ Fan o‘chirish")
async def remove_subject_btn(message: Message, state: FSMContext):
    if not await check_user(message): return
    name, subjects = get_user(message.from_user.id)

    txt = "Qaysi fanni o‘chiramiz?\n\n"
    txt += "\n".join(f"- {s.strip()}" for s in subjects.split(","))

    await message.answer(txt)
    await state.set_state(Form.removing_subject)

@dp.message(Form.removing_subject)
async def remove_subject(message: Message, state: FSMContext):
    uid = message.from_user.id
    name, subjects = get_user(uid)
    subjects_list = [s.strip() for s in subjects.split(",")]

    if message.text not in subjects_list:
        await message.answer("Bunday fan yo‘q. Qayta yozing.")
        return

    subjects_list.remove(message.text)
    update_subjects(uid, ", ".join(subjects_list))

    await message.answer("Fan o‘chirildi!", reply_markup=main_menu)
    await state.clear()

# ======================================
#   DONE (RASM QABUL QILISH VA DAVOMIYLIK SO‘RASH)
# ======================================

@dp.message(F.text == "✔️ Done")
async def done_start(message: Message, state: FSMContext):
    if not await check_user(message): return
    await message.answer("Bugun qilgan ishingiz rasmini yuboring 📸")
    await state.set_state(Form.waiting_done_photo)


@dp.message(Form.waiting_done_photo, F.photo)
async def done_photo(message: Message, state: FSMContext):
    uid = message.from_user.id

    if not os.path.exists("photos"):
        os.makedirs("photos")

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{uid}_{timestamp}.jpg"
    path = f"photos/{filename}"

    await bot.download(message.photo[-1].file_id, destination=path)

    # Rasm va vaqt hali saqlanmaydi, vaqt keyin so‘raladi
    # Vaqt saqlash uchun vaqtga tegishli ma’lumotni holatda saqlaymiz
    await state.update_data(done_photo_path=path, done_timestamp=timestamp)

    await message.answer("⏳ Necha daqiqa dars qildingiz? Iltimos, faqat son kiriting.")
    await state.set_state(Form.waiting_done_duration)

@dp.message(Form.waiting_done_duration)
async def done_duration(message: Message, state: FSMContext):
    uid = message.from_user.id
    data = await state.get_data()
    path = data.get("done_photo_path")
    timestamp = data.get("done_timestamp")

    try:
        duration = int(message.text)
        if duration <= 0:
            raise ValueError
    except:
        await message.answer("Iltimos, dars davomiyligini faqat musbat son ko‘rinishida kiriting.")
        return

    cursor.execute(
        "INSERT INTO done (user_id, photo_path, timestamp, duration) VALUES (?, ?, ?, ?)",
        (uid, path, timestamp, duration)
    )
    db.commit()

    # Darslar sonini hisoblash
    cursor.execute("SELECT COUNT(*) FROM done WHERE user_id = ?", (uid,))
    done_count = cursor.fetchone()[0]

    await message.answer(
        f"✔️ Bugungi o‘qish saqlandi! Siz jami {done_count} dars bajardingiz.",
        reply_markup=main_menu
    )
    await state.clear()

@dp.message(Form.waiting_done_photo)
async def wrong_done(message: Message):
    await message.answer("Faqat rasm yuboring 📸")

# ======================================
#   📆 HAFTALIK HISOBOT
# ======================================


@dp.message(F.text == "📆 Haftalik hisobot")
async def weekly_report(message: Message):
    if not await check_user(message): return

    uid = message.from_user.id
    seven_days_ago = datetime.now() - timedelta(days=7)

    cursor.execute("""
        SELECT photo_path, timestamp, duration FROM done 
        WHERE user_id = ? ORDER BY timestamp DESC
    """, (uid,))
    
    rows = cursor.fetchall()

    photos = []
    total_duration = 0
    total_days = set()

    for path, ts, duration in rows:
        ts_dt = datetime.strptime(ts, "%Y-%m-%d_%H-%M-%S")
        if ts_dt >= seven_days_ago:
            photos.append((path, ts, duration))
            total_duration += duration
            total_days.add(ts_dt.date())

    if not photos:
        await message.answer("Oxirgi 7 kunda hech qanday done qo‘shilmagan.")
        return

    total_days_count = len(total_days)
    avg_duration = total_duration // total_days_count if total_days_count else 0

    await message.answer(
        f"📊 Haftalik hisobot:\n"
        f"– Jami kun: {total_days_count}\n"
        f"– Jami o‘qigan vaqt: {total_duration} daqiqa\n"
        f"– O‘rtacha kunlik: {avg_duration} daqiqa"
    )

    # await message.answer("📆 *Oxirgi 7 kunlik hisobot:*", parse_mode="Markdown")

    # for path, ts, duration in photos:
    #     full_path = os.path.abspath(path)
    #     caption = f"📸 Sana: {ts.replace('_', ' ')} – ⏳ {duration} daqiqa"

    #     if not os.path.exists(full_path):
    #         await message.answer(f"❗ Rasm topilmadi: {full_path}")
    #         continue

    #     try:
    #         photo = InputFile(full_path)
    #         await message.answer_photo(photo=photo, caption=caption)
    #     except Exception as e:
    #         await message.answer(f"❗ Rasmni ochib bo‘lmadi: {full_path}\nXato: {e}")

# ======================================
#   DAILY SCHEDULE
# ======================================

async def send_daily_plan():
    while True:
        now = datetime.now().time()

        if now.hour == 7 and now.minute == 0:
            cursor.execute("SELECT user_id, subjects FROM users")
            users = cursor.fetchall()

            for uid, subjects in users:
                subjects_list = subjects.split(",")

                txt = "📅 *Bugungi reja:*\n"
                txt += "\n".join(f"— {s.strip()}" for s in subjects_list)

                try:
                    await bot.send_message(uid, txt, parse_mode="Markdown")
                except:
                    pass

            await asyncio.sleep(60)

        await asyncio.sleep(1)

async def send_daily_reminder():
    users = get_all_user_ids()
    for user_id in users:
        try:
            await bot.send_message(user_id, "🔔 Bugun darsni bajarishga ulgurmadizmi? Done bosib rasm tashlang!")
        except Exception as e:
            print(f"Xato yuborishda user {user_id}: {e}")

async def on_startup(_):
    scheduler.add_job(send_daily_reminder, 'cron', hour=21, minute=0)  # Soat 21:00 da ishga tushadi
    scheduler.start()

# ======================================
#   RUN
# ======================================

async def main():
    print("BOT ISHGA TUSHDI...")
    asyncio.create_task(send_daily_plan())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
