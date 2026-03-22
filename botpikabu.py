import os
import time
import re
import threading
import telebot
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')
AI_TUNNEL = os.getenv('AI_TUNNEL_KEY')

bot = telebot.TeleBot(TOKEN)

# Хранилище в памяти: {user_id: {'topics': {topic: last_id}}}
users = {}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
}

PROXIES = {'http': AI_TUNNEL, 'https': AI_TUNNEL} if AI_TUNNEL else None


def get_new_posts(topic: str, last_seen_id: int = 0):
    """Парсит новые посты по тегу. Возвращает список новых (id > last_seen_id)."""
    url = f"https://pikabu.ru/tag/{topic}"
    try:
        r = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, 'html.parser')

        posts = []
        # Основные карточки постов (актуально на 2026 год)
        for story in soup.find_all('div', class_='story'):
            link_tag = story.find('a', class_='story__title-link')
            if not link_tag:
                continue

            href = link_tag.get('href', '')
            title = link_tag.get_text(strip=True)
            # Извлекаем ID поста из конца ссылки (всегда число)
            match = re.search(r'(\d{7,})$', href)
            if match:
                story_id = int(match.group(1))
                if story_id > last_seen_id:
                    full_url = 'https://pikabu.ru' + href
                    posts.append({'id': story_id, 'title': title, 'url': full_url})

        # Сортируем по новизне
        posts.sort(key=lambda x: x['id'], reverse=True)
        return posts

    except Exception as e:
        print(f"Ошибка при парсинге {topic}: {e}")
        return []


def monitoring_thread():
    """Фоновый мониторинг каждые 5 минут."""
    while True:
        try:
            for user_id in list(users.keys()):
                user_data = users[user_id]
                for topic in list(user_data['topics'].keys()):
                    last_id = user_data['topics'][topic]
                    new_posts = get_new_posts(topic, last_id)

                    if new_posts:
                        # Обновляем последний ID
                        max_id = max(p['id'] for p in new_posts)
                        user_data['topics'][topic] = max_id

                        # Отправляем новые посты (самые свежие сверху)
                        for post in new_posts:
                            bot.send_message(
                                user_id,
                                f"🆕 **Новый пост** по теме «{topic}»\n\n"
                                f"{post['title']}\n\n"
                                f"🔗 {post['url']}",
                                parse_mode='Markdown'
                            )
        except:
            pass  # не падаем при любой ошибке

        time.sleep(300)  # 5 минут


# ================== Команды бота ==================

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message,
        "👋 Привет! Я мониторю pikabu.ru по твоим тегам.\n\n"
        "Команды:\n"
        "/subscribe нейросети — подписаться\n"
        "/my_topics — список твоих тем\n"
        "/unsubscribe нейросети — отписаться\n\n"
        "Бот проверяет новые посты каждые 5 минут.")


@bot.message_handler(commands=['subscribe'])
def subscribe(message):
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Укажи тег после команды, например:\n/subscribe нейросети")
        return

    topic = message.text.split(maxsplit=1)[1].strip()
    user_id = message.chat.id

    if user_id not in users:
        users[user_id] = {'topics': {}}

    if topic in users[user_id]['topics']:
        bot.reply_to(message, f"✅ Уже подписан на «{topic}»")
        return

    # Инициализируем последний ID (чтобы не слать старые посты)
    new_posts = get_new_posts(topic, 0)
    last_id = max((p['id'] for p in new_posts), default=0)

    users[user_id]['topics'][topic] = last_id
    bot.reply_to(message, f"✅ Подписка на «{topic}» активирована!\nБуду присылать только новые посты.")


@bot.message_handler(commands=['unsubscribe'])
def unsubscribe(message):
    if len(message.text.split()) < 2:
        bot.reply_to(message, "Укажи тег после команды")
        return

    topic = message.text.split(maxsplit=1)[1].strip()
    user_id = message.chat.id

    if user_id in users and topic in users[user_id]['topics']:
        del users[user_id]['topics'][topic]
        if not users[user_id]['topics']:
            del users[user_id]
        bot.reply_to(message, f"❌ Отписан от «{topic}»")
    else:
        bot.reply_to(message, "Ты не подписан на этот тег")


@bot.message_handler(commands=['my_topics'])
def my_topics(message):
    user_id = message.chat.id
    if user_id not in users or not users[user_id]['topics']:
        bot.reply_to(message, "У тебя нет активных подписок")
        return

    topics = "\n".join(f"• {t}" for t in users[user_id]['topics'].keys())
    bot.reply_to(message, f"Твои темы:\n{topics}")


# Запускаем мониторинг в отдельном потоке
threading.Thread(target=monitoring_thread, daemon=True).start()

print("Бот запущен...")
bot.infinity_polling()