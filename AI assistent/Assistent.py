import os
import logging
import telebot
from telebot import types
import requests
import io
from PyPDF2 import PdfReader
import docx2txt
import time
import json
import base64
import re
from threading import Thread

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# API ключи
TELEGRAM_TOKEN = '8155922543:AAHd7BVP8629coKuY9e7MqWdu10DG36yZdg'
YANDEX_API_KEY = 'AQVN3AcguggqzJkhUpU3KxoNfHa097XkZGDgHXHB'
FOLDER_ID = 'b1gujvjsajattd5kam45'
CHANNEL_ID = '@Smart_Mind_News'
BOT_USERNAME = 'SmartMindBot'

# URL для YandexGPT API
YANDEX_API_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
# URL для Yandex Vision API
YANDEX_VISION_URL = "https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze"
# URL для Yandex SpeechKit API
YANDEX_SPEECH_URL = "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize"

# URL изображения для приветственного сообщения
IMAGE_URL = "https://t.me/ddg3450/2"  # Ссылка на картинку из открытого Telegram-канала

# Инициализация бота
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Хранилище истории сообщений для каждого пользователя
conversation_history = {}

# Максимальная длина текста для отправки в YandexGPT (в символах)
MAX_TEXT_LENGTH = 2000

# Файлы для хранения данных
TOKENS_FILE = 'user_tokens.json'
REFERRAL_TOKENS_FILE = 'referral_tokens.json'
INVITED_COUNTS_FILE = 'invited_counts.json'

# Максимальное количество токенов в день
MAX_TOKENS_PER_DAY = 30000

# Максимальная длина истории сообщений
MAX_HISTORY_LENGTH = 100

# Функция для загрузки данных о основных токенах
def load_user_tokens():
    if os.path.exists(TOKENS_FILE):
        try:
            with open(TOKENS_FILE, 'r') as f:
                data = json.load(f)
                # Convert tokens to int for all users
                for user_id in data:
                    if isinstance(data[user_id]["tokens"], str):
                        data[user_id]["tokens"] = int(data[user_id]["tokens"])
                return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Ошибка чтения {TOKENS_FILE}: {str(e)}. Создаём новый файл.")
            return {}
    else:
        logger.info(f"Файл {TOKENS_FILE} не найден. Создаём новый.")
        return {}

# Функция для сохранения данных о основных токенах
def save_user_tokens(data):
    try:
        with open(TOKENS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Ошибка записи в {TOKENS_FILE}: {str(e)}")

# Функция для получения оставшихся основных токенов (с проверкой сброса)
def get_user_tokens(user_id):
    data = load_user_tokens()
    now = time.time()
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = {"tokens": MAX_TOKENS_PER_DAY, "last_reset": now}
        save_user_tokens(data)
    else:
        last_reset = data[user_id_str]["last_reset"]
        if now - last_reset >= 86400:  # 24 часа в секундах
            data[user_id_str]["tokens"] = MAX_TOKENS_PER_DAY
            data[user_id_str]["last_reset"] = now
            save_user_tokens(data)
    return data[user_id_str]["tokens"]

# Функция для вычета основных токенов
def deduct_tokens(user_id, amount):
    data = load_user_tokens()
    user_id_str = str(user_id)
    if user_id_str in data:
        try:
            data[user_id_str]["tokens"] = int(data[user_id_str]["tokens"]) - int(amount)
            if data[user_id_str]["tokens"] < 0:
                data[user_id_str]["tokens"] = 0
            save_user_tokens(data)
        except (TypeError, ValueError) as e:
            logger.error(f"Ошибка при вычете токенов для пользователя {user_id}: {str(e)}")
    else:
        logger.error(f"Пользователь {user_id} не найден в {TOKENS_FILE}")

# Функция для загрузки реферальных токенов
def load_referral_tokens():
    if os.path.exists(REFERRAL_TOKENS_FILE):
        try:
            with open(REFERRAL_TOKENS_FILE, 'r') as f:
                data = json.load(f)
                # Convert to int
                for user_id in data:
                    if isinstance(data[user_id], str):
                        data[user_id] = int(data[user_id])
                return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Ошибка чтения {REFERRAL_TOKENS_FILE}: {str(e)}. Создаём новый файл.")
            return {}
    else:
        logger.info(f"Файл {REFERRAL_TOKENS_FILE} не найден. Создаём новый.")
        return {}

# Функция для сохранения реферальных токенов
def save_referral_tokens(data):
    try:
        with open(REFERRAL_TOKENS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Ошибка записи в {REFERRAL_TOKENS_FILE}: {str(e)}")

# Функция для получения реферальных токенов
def get_referral_tokens(user_id):
    data = load_referral_tokens()
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = 0
        save_referral_tokens(data)
    return int(data[user_id_str])

# Функция для добавления реферальных токенов
def add_referral_tokens(user_id, amount):
    data = load_referral_tokens()
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = 0
    data[user_id_str] += int(amount)
    save_referral_tokens(data)

# Функция для вычета реферальных токенов
def deduct_referral_tokens(user_id, amount):
    data = load_referral_tokens()
    user_id_str = str(user_id)
    if user_id_str in data:
        data[user_id_str] -= int(amount)
        if data[user_id_str] < 0:
            data[user_id_str] = 0
        save_referral_tokens(data)

# Функция для загрузки количества приглашенных
def load_invited_counts():
    if os.path.exists(INVITED_COUNTS_FILE):
        try:
            with open(INVITED_COUNTS_FILE, 'r') as f:
                data = json.load(f)
                # Convert to int
                for user_id in data:
                    if isinstance(data[user_id], str):
                        data[user_id] = int(data[user_id])
                return data
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Ошибка чтения {INVITED_COUNTS_FILE}: {str(e)}. Создаём новый файл.")
            return {}
    else:
        logger.info(f"Файл {INVITED_COUNTS_FILE} не найден. Создаём новый.")
        return {}

# Функция для сохранения количества приглашенных
def save_invited_counts(data):
    try:
        with open(INVITED_COUNTS_FILE, 'w') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Ошибка записи в {INVITED_COUNTS_FILE}: {str(e)}")

# Функция для получения количества приглашенных
def get_invited_count(user_id):
    data = load_invited_counts()
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = 0
        save_invited_counts(data)
    return int(data[user_id_str])

# Функция для инкремента количества приглашенных
def increment_invited_count(user_id):
    data = load_invited_counts()
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = 0
    data[user_id_str] += 1
    save_invited_counts(data)

# Функция для преобразования Markdown в HTML
def markdown_to_html(text):
    html_tags = []
    def store_html_tag(match):
        html_tags.append(match.group(0))
        return f"__HTML_TAG_{len(html_tags)-1}__"
    
    text = re.sub(r'<[^>]+>', store_html_tag, text)
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<b>\1</b>', text)
    text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
    text = re.sub(r'_(.*?)_', r'<i>\1</i>', text)
    text = re.sub(r'`([^`\n]+)`', r'<code>\1</code>', text)
    text = re.sub(r'```(?:\w*\n)?(.*?)```', r'<pre>\1</pre>', text, flags=re.DOTALL)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2">\1</a>', text)
    
    def restore_html_tag(match):
        index = int(match.group(1))
        return html_tags[index]
    
    text = re.sub(r'__HTML_TAG_(\d+)__', restore_html_tag, text)
    return text

# Функция проверки подписки
def check_subscription(user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL_ID, user_id)
        logger.info(f"Статус подписки пользователя {user_id}: {chat_member.status}")
        return chat_member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки для пользователя {user_id}: {str(e)}")
        return False

# Создание главного меню
def create_main_menu():
    return types.ReplyKeyboardRemove()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return

    # Проверяем реферальный код
    referrer_id = None
    if message.text.startswith('/start ') and len(message.text.split()) > 1:
        try:
            referrer_id = int(message.text.split()[1])
            if referrer_id == user_id:
                referrer_id = None  # Не награждать самого себя
        except ValueError:
            referrer_id = None

    # Проверяем, новый ли пользователь
    data = load_user_tokens()
    user_id_str = str(user_id)
    is_new = user_id_str not in data

    if is_new and referrer_id is not None:
        # Начисляем реферальные токены и увеличиваем счетчик
        add_referral_tokens(referrer_id, 10000)
        increment_invited_count(referrer_id)

    # Инициализируем токены, если новый
    if is_new:
        now = time.time()
        data[user_id_str] = {"tokens": MAX_TOKENS_PER_DAY, "last_reset": now}
        save_user_tokens(data)

    if user_id not in conversation_history:
        conversation_history[user_id] = []

    main_tokens = get_user_tokens(user_id)
    ref_tokens = get_referral_tokens(user_id)
    total_tokens = main_tokens + ref_tokens

    # Формируем приветственное сообщение
    welcome_message = (
        '<b>👋 Привет! Я @SmartMindBot — твой AI-ассистент!</b>\n\n'
        'Я могу:\n'
        '📝 <i>Отвечать на любые вопросы</i>\n'
        '📎 <i>Читать TXT, PDF и DOCX файлы</i>\n'
        '📸 <i>Отвечать на вопросы, извлеченные из изображений</i>\n'
        '🗣️ <i>Распознавать и отвечать на голосовые сообщения</i>\n\n'
        f'<blockquote>У вас <code>{total_tokens}</code> токенов (<code>{main_tokens}</code> основных + <code>{ref_tokens}</code> реферальных)</blockquote>\n'
        f'<blockquote>Основные токены обновляются каждые 24 часа до <code>{MAX_TOKENS_PER_DAY}</code>.</blockquote>\n'
        '<blockquote>Реферальная система: /ref</blockquote>\n\n'
        '<b>Введите свой запрос или отправьте файл/фото/голосовое сообщение</b> 👇'
    )

    # Создаём inline-кнопку "Поддержать проект"
    markup = types.InlineKeyboardMarkup()
    support_button = types.InlineKeyboardButton("🙏 Поддержать проект", callback_data="support_project")
    markup.add(support_button)

    # Отправляем изображение с приветственным сообщением и inline-кнопкой
    try:
        bot.send_photo(
            user_id,
            IMAGE_URL,
            caption=welcome_message,
            parse_mode='HTML',
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Ошибка отправки изображения: {str(e)}")
        # В случае ошибки отправляем только текст с inline-кнопкой
        bot.reply_to(
            message,
            f'<b>❌ Ошибка:</b> Не удалось отправить приветственное изображение. {str(e)}\n\n{welcome_message}',
            parse_mode='HTML',
            reply_markup=markup
        )

# Обработчик нажатия на inline-кнопку "Поддержать проект"
@bot.callback_query_handler(func=lambda call: call.data == "support_project")
def handle_support_button(call):
    user_id = call.from_user.id
    # Проверяем подписку
    if not check_subscription(user_id):
        bot.answer_callback_query(
            call.id,
            "⚠️ Вы не подписаны на наш канал! Подпишитесь, чтобы продолжить.",
            show_alert=True
        )
        bot.send_message(
            call.message.chat.id,
            f'<b>⚠️ Вы не подписаны на наш канал!</b>\n\n'
            f'<blockquote>Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.</blockquote>',
            parse_mode='HTML'
        )
        return

    # Реквизиты карты (замените на реальные)
    card_details = (
        '<b>🙏 Поддержите проект!</b>\n\n'
        '💸 Вы можете перевести любую сумму по реквизитам:\n'
        '<code>2204320957546460</code>\n\n'
        'Спасибо за вашу поддержку! ❤️'
    )
    
    try:
        bot.send_message(
            call.message.chat.id,
            card_details,
            parse_mode='HTML'
        )
        bot.answer_callback_query(call.id, "Реквизиты отправлены!")
    except Exception as e:
        logger.error(f"Ошибка отправки реквизитов: {str(e)}")
        bot.answer_callback_query(
            call.id,
            f"Ошибка при отправке реквизитов: {str(e)}",
            show_alert=True
        )

@bot.message_handler(commands=['clear'])
def clear_history(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return
    conversation_history[user_id] = []
    bot.reply_to(
        message,
        '<b>🧹 История диалога очищена.</b> Теперь я начну с чистого листа!',
        parse_mode='HTML',
        reply_markup=create_main_menu()
    )

@bot.message_handler(commands=['check'])
def check_tokens_handler(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return
    main_tokens = get_user_tokens(user_id)
    ref_tokens = get_referral_tokens(user_id)
    total_tokens = main_tokens + ref_tokens
    bot.reply_to(
        message,
        f'<b>📊 У вас осталось:</b>\n'
        f'• <code>{main_tokens}</code> основных токенов\n'
        f'• <code>{ref_tokens}</code> реферальных токенов\n'
        f'• Всего: <code>{total_tokens}</code> токенов\n\n'
        '<i>Основные токены обновляются каждые 24 часа.</i>',
        parse_mode='HTML'
    )

@bot.message_handler(commands=['ref'])
def ref_handler(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return
    invited = get_invited_count(user_id)
    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.reply_to(
        message,
        f'<b>🔗 Ваша реферальная ссылка:</b> <a href="{link}">{link}</a>\n\n'
        f'<b>👤 Приглашено пользователей:</b> <code>{invited}</code>\n\n'
        '<blockquote><i>Поделитесь ссылкой с друзьями! За каждого приглашенного пользователя вы получите <code>10000</code> реферальных токенов.</i></blockquote>',
        parse_mode='HTML'
    )

@bot.message_handler(content_types=['text'])
def handle_message(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return

    main_tokens = get_user_tokens(user_id)
    ref_tokens = get_referral_tokens(user_id)
    total_tokens = main_tokens + ref_tokens
    if total_tokens <= 0:
        bot.reply_to(
            message,
            '<b>❌ Токены закончились!</b> Вы использовали все токены на сегодня. Основные токены обновятся через 24 часа.',
            parse_mode='HTML'
        )
        return

    if message.text.startswith('/generate ') or message.text == "🖼️ Создать картинку":
        bot.reply_to(
            message,
            '<b>🖼️ Генерация изображений через YandexGPT недоступна.</b> Используйте GigaChat/Kandinsky для изображений.',
            parse_mode='HTML'
        )
        return

    try:
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        conversation_history[user_id].append({
            "role": "user",
            "text": message.text
        })
        
        if not conversation_history[user_id]:
            bot.reply_to(message, '<b>❌ Ошибка:</b> История диалога пуста. Задайте вопрос.', parse_mode='HTML')
            return
        for msg in conversation_history[user_id]:
            if not isinstance(msg, dict) or 'role' not in msg or 'text' not in msg or not isinstance(msg['text'], str) or not msg['text'].strip():
                logger.error(f"Некорректное сообщение в истории: {msg}")
                bot.reply_to(message, '<b>❌ Ошибка:</b> Некорректный формат истории диалога.', parse_mode='HTML')
                return
        
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY_LENGTH:]
        
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
            "completionOptions": {
                "stream": False,
                "temperature": 0.7,
                "maxTokens": 1000
            },
            "messages": conversation_history[user_id]
        }
        logger.info(f"Отправляем запрос к YandexGPT: {json.dumps(payload, ensure_ascii=False)}")
        response = requests.post(YANDEX_API_URL, headers=headers, json=payload)
        response_text = response.text if response.text else 'No response body'
        logger.info(f"Ответ от YandexGPT (status {response.status_code}): {response_text}")
        response.raise_for_status()
        response_data = response.json()
        
        if 'result' not in response_data or 'alternatives' not in response_data['result']:
            raise ValueError(f"Неверный формат ответа от YandexGPT: {response_data}")
        
        content = response_data['result']['alternatives'][0]['message']['text']
        if not content:
            raise ValueError("Пустой ответ от модели")
        
        # Вычитаем использованные токены
        used_tokens = 0
        if 'usage' in response_data['result'] and 'totalTokens' in response_data['result']['usage']:
            used_tokens = int(response_data['result']['usage']['totalTokens'])
            # Сначала вычитаем из основных токенов
            main_tokens = get_user_tokens(user_id)
            if main_tokens >= used_tokens:
                deduct_tokens(user_id, used_tokens)
            else:
                deduct_tokens(user_id, main_tokens)
                remaining = used_tokens - main_tokens
                deduct_referral_tokens(user_id, remaining)
        
        content = markdown_to_html(content)
        
        conversation_history[user_id].append({
            "role": "assistant",
            "text": content
        })
        
        bot.reply_to(message, content, parse_mode='HTML')
    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        response_text = e.response.text if e.response and e.response.text else 'No response body'
        logger.error(f"Ошибка API YandexGPT (HTTP): {error_msg}, Response: {response_text}")
        bot.reply_to(
            message,
            f'<b>❌ Ошибка:</b> {error_msg}. Ответ сервера: {response_text}. Проверьте настройки YandexGPT.',
            parse_mode='HTML'
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка API YandexGPT: {error_msg}")
        bot.reply_to(
            message,
            f'<b>❌ Ошибка:</b> {error_msg}. Попробуйте переформулировать запрос или проверьте настройки YandexGPT.',
            parse_mode='HTML'
        )

@bot.message_handler(content_types=['document'])
def handle_document(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return

    main_tokens = get_user_tokens(user_id)
    ref_tokens = get_referral_tokens(user_id)
    total_tokens = main_tokens + ref_tokens
    if total_tokens <= 0:
        bot.reply_to(
            message,
            '<b>❌ Токены закончились!</b> Вы использовали все токены на сегодня. Основные токены обновятся через 24 часа.',
            parse_mode='HTML'
        )
        return

    try:
        file_info = bot.get_file(message.document.file_id)
        file = bot.download_file(file_info.file_path)
        
        file_name = message.document.file_name.lower()
        content = ''
        
        if file_name.endswith('.txt'):
            content = file.decode('utf-8')
        elif file_name.endswith('.pdf'):
            pdf_reader = PdfReader(io.BytesIO(file))
            content = '\n'.join(page.extract_text() for page in pdf_reader.pages if page.extract_text())
        elif file_name.endswith('.docx'):
            try:
                content = docx2txt.process(io.BytesIO(file))
                if not content.strip():
                    content = 'Файл DOCX пуст или не содержит читаемого текста.'
            except Exception as docx_error:
                logger.error(f"Ошибка обработки DOCX: {str(docx_error)}")
                content = f'Ошибка обработки DOCX-файла: {str(docx_error)}'
        else:
            content = 'Поддерживаю только TXT, PDF и DOCX файлы.'
        
        if content and content.strip() and not content.startswith('Ошибка обработки DOCX'):
            if len(content) > MAX_TEXT_LENGTH:
                content = content[:MAX_TEXT_LENGTH]
                logger.info(f"Текст файла обрезан до {MAX_TEXT_LENGTH} символов")
                bot.reply_to(
                    message,
                    f'<b>⚠️ Внимание:</b> Файл слишком большой. Обработана только часть текста (до {MAX_TEXT_LENGTH} символов).',
                    parse_mode='HTML'
                )
            
            content = re.sub(r'[^\x00-\x7Fа-яА-ЯёЁ0-9\s.,!?]', '', content)
            
            if user_id not in conversation_history:
                conversation_history[user_id] = []
            
            conversation_history[user_id].append({
                "role": "user",
                "text": content.strip()
            })
            
            conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY_LENGTH:]
            
            try:
                headers = {
                    "Authorization": f"Api-Key {YANDEX_API_KEY}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
                    "completionOptions": {
                        "stream": False,
                        "temperature": 0.7,
                        "maxTokens": 1000
                    },
                    "messages": conversation_history[user_id]
                }
                logger.info(f"Отправляем запрос к YandexGPT: {json.dumps(payload, ensure_ascii=False)}")
                response = requests.post(YANDEX_API_URL, headers=headers, json=payload)
                response_text = response.text if response.text else 'No response body'
                logger.info(f"Ответ от YandexGPT (status {response.status_code}): {response_text}")
                response.raise_for_status()
                response_data = response.json()
                
                if 'result' not in response_data or 'alternatives' not in response_data['result']:
                    raise ValueError(f"Неверный формат ответа от YandexGPT: {response_data}")
                
                response_content = response_data['result']['alternatives'][0]['message']['text']
                if not response_content:
                    raise ValueError("Пустой ответ от модели")
                
                # Вычитаем использованные токены
                used_tokens = 0
                if 'usage' in response_data['result'] and 'totalTokens' in response_data['result']['usage']:
                    used_tokens = int(response_data['result']['usage']['totalTokens'])
                    # Сначала вычитаем из основных токенов
                    main_tokens = get_user_tokens(user_id)
                    if main_tokens >= used_tokens:
                        deduct_tokens(user_id, used_tokens)
                    else:
                        deduct_tokens(user_id, main_tokens)
                        remaining = used_tokens - main_tokens
                        deduct_referral_tokens(user_id, remaining)
                
                response_content = markdown_to_html(response_content)
                
                conversation_history[user_id].append({
                    "role": "assistant",
                    "text": response_content
                })
                
                bot.reply_to(message, response_content, parse_mode='HTML')
            except requests.exceptions.HTTPError as e:
                error_msg = str(e)
                response_text = e.response.text if e.response and e.response.text else 'No response body'
                logger.error(f"Ошибка API YandexGPT (HTTP): {error_msg}, Response: {response_text}")
                bot.reply_to(
                    message,
                    f'<b>❌ Ошибка:</b> {error_msg}. Ответ сервера: {response_text}. Проверьте настройки YandexGPT.',
                    parse_mode='HTML'
                )
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Ошибка API YandexGPT: {error_msg}")
                bot.reply_to(
                    message,
                    f'<b>❌ Ошибка:</b> {error_msg}. Попробуйте отправить другой файл или проверьте настройки YandexGPT.',
                    parse_mode='HTML'
                )
        else:
            bot.reply_to(
                message,
                f'<b>❌ Ошибка:</b> {content}',
                parse_mode='HTML'
            )
    except Exception as e:
        logger.error(f"Ошибка чтения файла: {str(e)}")
        bot.reply_to(
            message,
            f'<b>❌ Ошибка чтения файла:</b> {str(e)}',
            parse_mode='HTML'
        )

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return

    main_tokens = get_user_tokens(user_id)
    ref_tokens = get_referral_tokens(user_id)
    total_tokens = main_tokens + ref_tokens
    if total_tokens <= 0:
        bot.reply_to(
            message,
            '<b>❌ Токены закончились!</b> Вы использовали все токены на сегодня. Основные токены обновятся через 24 часа.',
            parse_mode='HTML'
        )
        return

    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        file = bot.download_file(file_info.file_path)
        
        encoded_image = base64.b64encode(file).decode('utf-8')
        
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "folderId": FOLDER_ID,
            "analyze_specs": [
                {
                    "content": encoded_image,
                    "features": [
                        {
                            "type": "TEXT_DETECTION",
                            "text_detection_config": {
                                "language_codes": ["ru", "en"]
                            }
                        }
                    ]
                }
            ]
        }
        
        logger.info(f"Отправляем запрос к Yandex Vision API: {json.dumps(payload, ensure_ascii=False)}")
        response = requests.post(YANDEX_VISION_URL, headers=headers, json=payload)
        response_text = response.text if response.text else 'No response body'
        logger.info(f"Ответ от Yandex Vision API (status {response.status_code}): {response_text}")
        response.raise_for_status()
        
        response_data = response.json()
        
        text = ""
        try:
            results = response_data.get('results', [{}])[0].get('results', [{}])[0].get('textDetection', {}).get('pages', [])
            for page in results:
                for block in page.get('blocks', []):
                    for line in block.get('lines', []):
                        for word in line.get('words', []):
                            text += word.get('text', '') + " "
                        text += "\n"
        except Exception as e:
            logger.error(f"Ошибка разбора ответа Yandex Vision: {str(e)}")
            bot.reply_to(
                message,
                '<b>❌ Ошибка:</b> Не удалось извлечь текст из изображения.',
                parse_mode='HTML'
            )
            return
        
        if not text.strip():
            bot.reply_to(
                message,
                '<b>❌ Ошибка:</b> Текст на изображении не обнаружен.',
                parse_mode='HTML'
            )
            return
        
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        conversation_history[user_id].append({
            "role": "user",
            "text": text.strip()
        })
        
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY_LENGTH:]
        
        try:
            headers = {
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": 1000
                },
                "messages": conversation_history[user_id]
            }
            logger.info(f"Отправляем запрос к YandexGPT с текстом из изображения: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(YANDEX_API_URL, headers=headers, json=payload)
            response_text = response.text if response.text else 'No response body'
            logger.info(f"Ответ от YandexGPT (status {response.status_code}): {response_text}")
            response.raise_for_status()
            response_data = response.json()
            
            if 'result' not in response_data or 'alternatives' not in response_data['result']:
                raise ValueError(f"Неверный формат ответа от YandexGPT: {response_data}")
            
            content = response_data['result']['alternatives'][0]['message']['text']
            if not content:
                raise ValueError("Пустой ответ от модели")
            
            # Вычитаем использованные токены
            used_tokens = 0
            if 'usage' in response_data['result'] and 'totalTokens' in response_data['result']['usage']:
                used_tokens = int(response_data['result']['usage']['totalTokens'])
                # Сначала вычитаем из основных токенов
                main_tokens = get_user_tokens(user_id)
                if main_tokens >= used_tokens:
                    deduct_tokens(user_id, used_tokens)
                else:
                    deduct_tokens(user_id, main_tokens)
                    remaining = used_tokens - main_tokens
                    deduct_referral_tokens(user_id, remaining)
            
            content = markdown_to_html(content)
            
            conversation_history[user_id].append({
                "role": "assistant",
                "text": content
            })
            
            bot.reply_to(message, content, parse_mode='HTML')
        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            response_text = e.response.text if e.response and e.response.text else 'No response body'
            logger.error(f"Ошибка API YandexGPT (HTTP): {error_msg}, Response: {response_text}")
            bot.reply_to(
                message,
                f'<b>❌ Ошибка:</b> {error_msg}. Ответ сервера: {response_text}. Проверьте настройки YandexGPT.',
                parse_mode='HTML'
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка API YandexGPT: {error_msg}")
            bot.reply_to(
                message,
                f'<b>❌ Ошибка:</b> {error_msg}. Попробуйте отправить другое изображение или проверьте настройки YandexGPT.',
                parse_mode='HTML'
            )
    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        response_text = e.response.text if e.response and e.response.text else 'No response body'
        logger.error(f"Ошибка API Yandex Vision (HTTP): {error_msg}, Response: {response_text}")
        bot.reply_to(
            message,
            f'<b>❌ Ошибка:</b> {error_msg}. Ответ сервера: {response_text}. Проверьте настройки Yandex Vision.',
            parse_mode='HTML'
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка обработки изображения: {error_msg}")
        bot.reply_to(
            message,
            f'<b>❌ Ошибка OCR:</b> {error_msg}',
            parse_mode='HTML'
        )

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.from_user.id
    if not check_subscription(user_id):
        bot.reply_to(
            message,
            '<b>⚠️ Вы не подписаны на наш канал!</b>\n'
            f'Подпишитесь на <a href="t.me/{CHANNEL_ID[1:]}">{CHANNEL_ID}</a>, чтобы использовать бота.',
            parse_mode='HTML'
        )
        return

    main_tokens = get_user_tokens(user_id)
    ref_tokens = get_referral_tokens(user_id)
    total_tokens = main_tokens + ref_tokens
    if total_tokens <= 0:
        bot.reply_to(
            message,
            '<b>❌ Токены закончились!</b> Вы использовали все токены на сегодня. Основные токены обновятся через 24 часа.',
            parse_mode='HTML'
        )
        return

    try:
        file_info = bot.get_file(message.voice.file_id)
        file = bot.download_file(file_info.file_path)
        
        headers = {
            "Authorization": f"Api-Key {YANDEX_API_KEY}"
        }
        params = {
            "folderId": FOLDER_ID,
            "lang": "ru-RU",  # Можно изменить на "en-US" или сделать динамичным
            "format": "oggopus",
            "sampleRateHertz": 48000
        }
        
        logger.info(f"Отправляем запрос к Yandex SpeechKit API")
        response = requests.post(YANDEX_SPEECH_URL, headers=headers, params=params, data=file)
        response_text = response.text if response.text else 'No response body'
        logger.info(f"Ответ от Yandex SpeechKit API (status {response.status_code}): {response_text}")
        response.raise_for_status()
        
        response_data = response.json()
        text = response_data.get('result', '')
        
        if not text.strip():
            bot.reply_to(
                message,
                '<b>❌ Ошибка:</b> Речь в голосовом сообщении не распознана.',
                parse_mode='HTML'
            )
            return
        
        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]
            logger.info(f"Распознанный текст обрезан до {MAX_TEXT_LENGTH} символов")
            bot.reply_to(
                message,
                f'<b>⚠️ Внимание:</b> Голосовое сообщение слишком длинное. Обработана только часть текста (до {MAX_TEXT_LENGTH} символов).',
                parse_mode='HTML'
            )
        
        text = re.sub(r'[^\x00-\x7Fа-яА-ЯёЁ0-9\s.,!?]', '', text)
        
        if user_id not in conversation_history:
            conversation_history[user_id] = []
        
        conversation_history[user_id].append({
            "role": "user",
            "text": text.strip()
        })
        
        conversation_history[user_id] = conversation_history[user_id][-MAX_HISTORY_LENGTH:]
        
        try:
            headers = {
                "Authorization": f"Api-Key {YANDEX_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "modelUri": f"gpt://{FOLDER_ID}/yandexgpt-lite",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.7,
                    "maxTokens": 1000
                },
                "messages": conversation_history[user_id]
            }
            logger.info(f"Отправляем запрос к YandexGPT с распознанным текстом: {json.dumps(payload, ensure_ascii=False)}")
            response = requests.post(YANDEX_API_URL, headers=headers, json=payload)
            response_text = response.text if response.text else 'No response body'
            logger.info(f"Ответ от YandexGPT (status {response.status_code}): {response_text}")
            response.raise_for_status()
            response_data = response.json()
            
            if 'result' not in response_data or 'alternatives' not in response_data['result']:
                raise ValueError(f"Неверный формат ответа от YandexGPT: {response_data}")
            
            content = response_data['result']['alternatives'][0]['message']['text']
            if not content:
                raise ValueError("Пустой ответ от модели")
            
            # Вычитаем использованные токены
            used_tokens = 0
            if 'usage' in response_data['result'] and 'totalTokens' in response_data['result']['usage']:
                used_tokens = int(response_data['result']['usage']['totalTokens'])
                # Сначала вычитаем из основных токенов
                main_tokens = get_user_tokens(user_id)
                if main_tokens >= used_tokens:
                    deduct_tokens(user_id, used_tokens)
                else:
                    deduct_tokens(user_id, main_tokens)
                    remaining = used_tokens - main_tokens
                    deduct_referral_tokens(user_id, remaining)
            
            content = markdown_to_html(content)
            
            conversation_history[user_id].append({
                "role": "assistant",
                "text": content
            })
            
            bot.reply_to(message, content, parse_mode='HTML')
        except requests.exceptions.HTTPError as e:
            error_msg = str(e)
            response_text = e.response.text if e.response and e.response.text else 'No response body'
            logger.error(f"Ошибка API YandexGPT (HTTP): {error_msg}, Response: {response_text}")
            bot.reply_to(
                message,
                f'<b>❌ Ошибка:</b> {error_msg}. Ответ сервера: {response_text}. Проверьте настройки YandexGPT.',
                parse_mode='HTML'
            )
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Ошибка API YandexGPT: {error_msg}")
            bot.reply_to(
                message,
                f'<b>❌ Ошибка:</b> {error_msg}. Попробуйте отправить другое голосовое сообщение или проверьте настройки YandexGPT.',
                parse_mode='HTML'
            )
    except requests.exceptions.HTTPError as e:
        error_msg = str(e)
        response_text = e.response.text if e.response and e.response.text else 'No response body'
        logger.error(f"Ошибка API Yandex SpeechKit (HTTP): {error_msg}, Response: {response_text}")
        bot.reply_to(
            message,
            f'<b>❌ Ошибка:</b> {error_msg}. Ответ сервера: {response_text}. Проверьте настройки Yandex SpeechKit.',
            parse_mode='HTML'
        )
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Ошибка обработки голосового сообщения: {error_msg}")
        bot.reply_to(
            message,
            f'<b>❌ Ошибка распознавания речи:</b> {error_msg}',
            parse_mode='HTML'
        )

# Функция для отправки keep-alive пинга
def keep_alive():
    ping_url = "https://api.telegram.org/bot{}/getMe".format(TELEGRAM_TOKEN)
    while True:
        try:
            response = requests.get(ping_url)
            if response.status_code == 200:
                logger.info("Keep-alive ping successful")
            else:
                logger.error(f"Keep-alive ping failed: {response.status_code}, {response.text}")
        except Exception as e:
            logger.error(f"Keep-alive ping error: {str(e)}")
        # Пинг каждые 5 минут (300 секунд), чтобы предотвратить спящий режим сервера
        time.sleep(300)

def main():
    # Запускаем keep-alive в отдельном потоке
    keep_alive_thread = Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()
    
    # Параметры polling с оптимизированными значениями
    polling_timeout = 60  # Увеличенный таймаут для long polling
    polling_interval = 0   # Интервал между запросами
    max_retries = 5       # Максимальное количество попыток переподключения
    retry_delay = 5       # Начальная задержка между попытками (секунды)

    retry_count = 0
    while True:
        try:
            logger.info("Starting bot polling...")
            bot.polling(none_stop=True, interval=polling_interval, timeout=polling_timeout, long_polling_timeout=polling_timeout)
            # Если polling завершился без ошибки, сбрасываем счетчик попыток
            retry_count = 0
        except telebot.apihelper.ApiException as e:
            logger.error(f"Telegram API error: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                logger.critical(f"Max retries ({max_retries}) reached. Stopping bot.")
                break
            # Экспоненциальная задержка перед повторной попыткой
            sleep_time = retry_delay * (2 ** retry_count)
            logger.info(f"Retrying in {sleep_time} seconds... (Attempt {retry_count}/{max_retries})")
            time.sleep(sleep_time)
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                logger.critical(f"Max retries ({max_retries}) reached. Stopping bot.")
                break
            sleep_time = retry_delay * (2 ** retry_count)
            logger.info(f"Retrying in {sleep_time} seconds... (Attempt {retry_count}/{max_retries})")
            time.sleep(sleep_time)
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            retry_count += 1
            if retry_count >= max_retries:
                logger.critical(f"Max retries ({max_retries}) reached. Stopping bot.")
                break
            sleep_time = retry_delay * (2 ** retry_count)
            logger.info(f"Retrying in {sleep_time} seconds... (Attempt {retry_count}/{max_retries})")
            time.sleep(sleep_time)
        finally:
            bot.stop_polling()  # Явно останавливаем polling перед повторной попыткой

if __name__ == '__main__':
    main()