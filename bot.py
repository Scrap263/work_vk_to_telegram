import asyncio
import json
import logging
from telegram import Update, Bot, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from playwright.async_api import async_playwright
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

load_dotenv()  # Загрузка переменных окружения из файла .env

# Замените на свой токен
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN не задан. Проверьте файл .env или переменные окружения.")

# Список групп ВКонтакте для мониторинга
VK_GROUPS = ['public200950350', 'club194502663', 'moukozh', 'korkatovolicey', 'club215514849', 'public210898118', 'club187004169', 'public189834198', 'morkischool6', 'clubnshkool', 'nurumbal', 'public192381334', 'club194496531', 'public217194863', 'club203944442', 'public195099678', 'club202720566', 'club215532555', 'public215503041', 'public140370320', 'club203823278', 'public215503051', 'public217593673', 'public172035079', 'club186110559', 'public216901123', 'public215503740', 'public163915584']

# Словарь для отображения удобных названий групп
VK_GROUPS_NAMES = {
    "public200950350": "Моркинский ЦФКС",
    "club194502663": "Зеленогорская СОШ",
    "moukozh": "МОУ Кожлаерская основная общеобразовательная школа",
    "korkatovolicey": "Коркатовский лицей",
    "club215514849": "МОУ Кульбашинская школа",
    "public210898118": "Купсолинская школа",
    "club187004169": "Моркинская средняя общеобразовательная школа №1",
    "public189834198": "Моркинская средняя общеобразовательная школа №2",
    "morkischool6": "Моркинская средняя общеобразовательная школа №6",
    "clubnshkool": "Нужключинская средняя общеобразовательная школа",
    "nurumbal": "Нурумбальская средняя общеобразовательная школа",
    "public192381334": "Себеусадская средняя общеобразовательная школа",
    "club194496531": "МОУ Шерегановская ООШ",
    "public217194863": "МОУ  Шиньшинская СОШ",
    "club203944442": "Шордурская основная общеобразовательная школа",
    "public195099678": "МОУ Шоруньжинская СОШ | РМЭ",
    "club202720566": "Янситовская основная общеобразовательная школа",
    "club215532555": "Моркинский детский сад №1",
    "public215503041": "Моркинский детский сад №5",
    "public140370320": "МОУ ДО Центр детского творчества п.Морки",
    "club203823278": "МОЦ ДОД Моркинского муниципального  района",
    "public215503051": "МОУ Октябрьская СОШ",
    "public217593673": "МОУ Аринская средняя общеобразовательная школа",
    "public172035079": "Кужерская основная школа",
    "club186110559": "Моркинский детский сад №3 Светлячок",
    "public216901123": "МДОУ Моркинский детский сад №2",
    "public215503740": "Отдел образования  Моркинского района",
    "public163915584": "Моркинский детский сад №7  Сказка"
}

# Файл для хранения подписчиков (теперь в виде словаря: ключ — id пользователя, значение — список сообществ)
SUBSCRIBERS_FILE = 'subscribers.json'

# Файл для хранения отправленных постов
SENT_POSTS_FILE = 'sent_posts.json'

def load_subscribers():
    if os.path.exists(SUBSCRIBERS_FILE):
        with open(SUBSCRIBERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            else:
                logger.error("Неверный формат файла подписчиков. Ожидался словарь, а получен список.")
                return {}  # либо можно реализовать преобразование
    return {}

def save_subscribers(subscribers):
    with open(SUBSCRIBERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(subscribers, f, ensure_ascii=False, indent=4)
    logger.info(f"Сохранено {len(subscribers)} подписчиков")

def load_sent_posts():
    """
    Загружает из файла set отправленных постов (их ID) и возвращает набор.
    Если файл отсутствует или содержит некорректные данные, возвращается пустой set.
    """
    if os.path.exists(SENT_POSTS_FILE):
        try:
            with open(SENT_POSTS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
                else:
                    logger.error("Неверный формат файла. Ожидался список ID постов.")
                    return set()
        except json.JSONDecodeError:
            logger.error("Ошибка декодирования JSON в файле отправленных постов. Создаём пустой список.")
            return set()
    return set()

def save_sent_posts(sent_posts):
    """
    Сохраняет набор ID отправленных постов в файл SENT_POSTS_FILE в виде списка.
    """
    with open(SENT_POSTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(list(sent_posts), f, ensure_ascii=False, indent=2)

# Глобальные переменные
SUBSCRIBERS = load_subscribers()
sent_posts = load_sent_posts()

def should_process_post(post_id):
    return post_id not in sent_posts

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_key = str(user_id)
    if user_key not in SUBSCRIBERS:
        # Подписываем нового пользователя на все группы по умолчанию
        SUBSCRIBERS[user_key] = list(VK_GROUPS)
        save_subscribers(SUBSCRIBERS)
        logger.info(f"Новый подписчик: {user_id}")
        # Отправляем последний пост из каждой группы
        asyncio.create_task(send_latest_posts_to_subscriber(user_id))
    welcome_message = (
        "Привет! Добро пожаловать в бота уведомлений ВКонтакте!\n\n"
        "Теперь вы будете получать уведомления о новых постах из ваших любимых сообществ.\n"
        "По умолчанию вы подписаны на все сообщества образовательных организаций Моркинского района. Чтобы изменить настройки, введите /subscriptions.\n\n"
        "Если хотите прекратить получать уведомления, используйте /stop."
    )
    await update.message.reply_text(welcome_message)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_key = str(user_id)
    if user_key in SUBSCRIBERS:
        del SUBSCRIBERS[user_key]
        save_subscribers(SUBSCRIBERS)
        logger.info(f"Отписался подписчик: {user_id}")
    await update.message.reply_text('Вы отписались от уведомлений.')

async def monitor_vk_groups():
    global sent_posts
    logger.info("Начало мониторинга групп ВКонтакте")
    while True:
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                page = await browser.new_page()

                for group in VK_GROUPS:
                    try:
                        logger.info(f"Проверка группы: {group}")
                        await page.goto(f'https://vk.com/{group}', timeout=60000, waitUntil="load")
                        await page.wait_for_load_state('load')

                        posts = await page.query_selector_all('.post')
                        logger.info(f"Найдено {len(posts)} постов в группе {group}")
                        for post in posts:
                            post_id = await post.get_attribute('data-post-id')
                            logger.info(f"Обработка поста с ID: {post_id}")
                            if should_process_post(post_id):
                                # Пытаемся получить текст поста несколькими способами
                                text_element = await post.query_selector('.wall_post_text')
                                if not text_element:
                                    text_element = await post.query_selector(
                                        '[data-testid="showmoretext-in-expanded"] .vkitShowMoreText__text--ULCyL'
                                    )
                                if not text_element:
                                    text_element = await post.query_selector('div.vkitShowMoreText__text--ULCyL')
                                post_text = await text_element.inner_text() if text_element else ''
                                logger.info(f"Длина текста поста: {len(post_text)}")
                                logger.info(f"Текст поста: {post_text[:100]}...")

                                # Извлекаем изображения
                                images = await post.query_selector_all(
                                    'img.attachment__link, img.vkitImageSingle__image--wgSJ5, img.vkitMediaGridImage__image--EA3Qm'
                                )
                                image_urls = [await img.get_attribute('src') for img in images]
                                logger.info(f"Найдено {len(image_urls)} изображений")
                                
                                # Получаем дату публикации поста
                                date_element = await post.query_selector('[data-testid="post_date_block_preview"]')
                                post_date = await date_element.inner_text() if date_element else ''

                                group_name = VK_GROUPS_NAMES.get(group, group)
                                message_text = f"{group_name}\n\n{post_text}\n\n{post_date}"
                                
                                # Отправляем уведомление только подписчикам, выбравшим данное сообщество
                                recipients = [int(uid) for uid, groups in SUBSCRIBERS.items() if group in groups]
                                if recipients:
                                    logger.info("Отправка уведомления о новом посте")
                                    await send_notification(message_text, image_urls, subscribers=recipients)
                                else:
                                    logger.info(f"Нет подписчиков для группы {group}")
                                    
                                sent_posts.add(post_id)
                                save_sent_posts(sent_posts)
                            else:
                                logger.info(f"Пост {post_id} уже был отправлен ранее")
                    except Exception as e:
                        logger.error(f"Ошибка при проверке группы {group}: {e}")

                await browser.close()
        except Exception as e:
            logger.error(f"Ошибка в мониторинге ВК: {e}")

        logger.info("Ожидание 5 минут перед следующей проверкой")
        await asyncio.sleep(300)

async def send_notification(text, image_urls, subscribers=None):
    bot = Bot(TELEGRAM_BOT_TOKEN)
    if subscribers is None:
        recipients = [int(uid) for uid in SUBSCRIBERS.keys()]
    else:
        recipients = subscribers
    for subscriber in recipients:
        try:
            if image_urls:
                if len(image_urls) == 1:
                    # Отправляем одно изображение с подписью
                    await bot.send_photo(chat_id=subscriber, photo=image_urls[0], caption=text)
                else:
                    # Формируем список объектов InputMediaPhoto для отправки альбома
                    media_group = []
                    media_group.append(InputMediaPhoto(media=image_urls[0], caption=text))
                    for url in image_urls[1:]:
                        media_group.append(InputMediaPhoto(media=url))
                    await bot.send_media_group(chat_id=subscriber, media=media_group)
            else:
                await bot.send_message(chat_id=subscriber, text=text)
            logger.info(f"Уведомление отправлено подписчику {subscriber}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления подписчику {subscriber}: {e}")

def is_recent_post(post_time):
    current_time = datetime.now()
    logger.info(f"Проверка времени поста: {post_time}")

    # Обработка различных форматов времени ВКонтакте
    if 'сегодня' in post_time.lower():
        post_time = post_time.lower().replace('сегодня в ', '')
        post_datetime = datetime.strptime(post_time, "%H:%M").replace(year=current_time.year, month=current_time.month, day=current_time.day)
    elif 'вчера' in post_time.lower():
        post_time = post_time.lower().replace('вчера в ', '')
        post_datetime = datetime.strptime(post_time, "%H:%M").replace(year=current_time.year, month=current_time.month, day=current_time.day) - timedelta(days=1)
    else:
        # Предполагаем формат "день месяц в час:минута"
        post_datetime = datetime.strptime(post_time, "%d %b в %H:%M")
        post_datetime = post_datetime.replace(year=current_time.year)

    # Считаем пост новым, если он опубликован менее часа назад
    is_recent = current_time - post_datetime < timedelta(hours=1)
    logger.info(f"Пост от {post_datetime} считается {'недавним' if is_recent else 'старым'}")
    return is_recent

async def send_latest_posts_to_subscriber(chat_id):
    logger.info(f"Отправка последнего поста каждой группы новому подписчику: {chat_id}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            for group in VK_GROUPS:
                try:
                    logger.info(f"Получение последнего поста из группы: {group}")
                    await page.goto(f'https://vk.com/{group}')
                    await page.wait_for_load_state('networkidle')
                    posts = await page.query_selector_all('.post')
                    if posts:
                        latest_post = posts[0]  # Берём первый пост
                        # Пытаемся получить текст поста несколькими способами
                        text_element = await latest_post.query_selector('.wall_post_text')
                        if not text_element:
                            text_element = await latest_post.query_selector(
                                '[data-testid="showmoretext-in-expanded"] .vkitShowMoreText__text--ULCyL'
                            )
                        if not text_element:
                            text_element = await latest_post.query_selector('div.vkitShowMoreText__text--ULCyL')
                        post_text = await text_element.inner_text() if text_element else ''
                        
                        images = await latest_post.query_selector_all(
                            'img.attachment__link, img.vkitImageSingle__image--wgSJ5, img.vkitMediaGridImage__image--EA3Qm'
                        )
                        image_urls = [await img.get_attribute('src') for img in images]
                        
                        date_element = await latest_post.query_selector('[data-testid="post_date_block_preview"]')
                        post_date = await date_element.inner_text() if date_element else ''

                        group_name = VK_GROUPS_NAMES.get(group, group)
                        message_text = f"{group_name}\n\n{post_text}\n\n{post_date}"
                        # Отправляем уведомление, если пользователь подписан на данную группу
                        if group in SUBSCRIBERS.get(str(chat_id), []):
                            await send_notification(message_text, image_urls, subscribers=[chat_id])
                            logger.info(f"Отправлено уведомление с последним постом из группы {group_name} для подписчика {chat_id}")
                        else:
                            logger.info(f"Пользователь {chat_id} не подписан на группу {group_name}")
                    else:
                        logger.warning(f"Посты не найдены в группе {group}")
                except Exception as e:
                    logger.error(f"Ошибка при получении поста из группы {group} для подписчика {chat_id}: {e}")
            await browser.close()
    except Exception as e:
        logger.error(f"Ошибка во время отправки последних постов подписчику {chat_id}: {e}")

# Новая функция для показа inline-клавиатуры настройки подписок
async def subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    user_key = str(user_id)
    current_subs = SUBSCRIBERS.get(user_key, [])
    keyboard = []
    row = []
    for group in VK_GROUPS:
        group_name = VK_GROUPS_NAMES.get(group, group)
        button_text = f"✅ {group_name}" if group in current_subs else f"❌ {group_name}"
        row.append(InlineKeyboardButton(button_text, callback_data=f"toggle:{group}"))
        if len(row) == 2:  # 2 кнопки в строке
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Настройте подписки, нажимая на кнопки:", reply_markup=reply_markup)

# Обработчик нажатия кнопок для переключения подписки
async def toggle_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_key = str(user_id)
    if query.data.startswith("toggle:"):
        group = query.data.split("toggle:")[1]
        if user_key not in SUBSCRIBERS:
            SUBSCRIBERS[user_key] = list(VK_GROUPS)
        current_subs = SUBSCRIBERS[user_key]
        if group in current_subs:
            current_subs.remove(group)
        else:
            current_subs.append(group)
        SUBSCRIBERS[user_key] = current_subs
        save_subscribers(SUBSCRIBERS)
        # Перестраиваем клавиатуру с обновлённым состоянием кнопок
        keyboard = []
        row = []
        for g in VK_GROUPS:
            g_name = VK_GROUPS_NAMES.get(g, g)
            button_text = f"✅ {g_name}" if g in current_subs else f"❌ {g_name}"
            row.append(InlineKeyboardButton(button_text, callback_data=f"toggle:{g}"))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_reply_markup(reply_markup=reply_markup)

async def run_bot(application):
    await application.initialize()
    await application.start()
    await application.updater.start_polling()

async def main():
    logger.info("Запуск бота")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    # Добавляем обработчик команды для настройки подписок
    application.add_handler(CommandHandler("subscriptions", subscriptions))
    # Обработчик для inline-кнопок (callback query) с данными, начинающимися с "toggle:"
    application.add_handler(CallbackQueryHandler(toggle_subscription, pattern="^toggle:"))

    bot_task = asyncio.create_task(run_bot(application))
    monitor_task = asyncio.create_task(monitor_vk_groups())

    logger.info("Бот запущен и ожидает команды")

    try:
        await asyncio.gather(bot_task, monitor_task)
    except asyncio.CancelledError:
        logger.info("Задачи отменены")
    except Exception as e:
        logger.error(f"Ошибка при выполнении задач: {e}")
    finally:
        logger.info("Завершение работы бота")
        await application.stop()
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
    finally:
        logger.info("Программа завершена")
