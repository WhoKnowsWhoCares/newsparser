import os
import httpx
import asyncio

from dotenv_vault import load_dotenv
from loguru import logger
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from redis import Redis, ConnectionError
from typing import List


class Storage():
    redis_client: Redis
    clients: set

    def __init__(self):
        pwd = os.getenv('DB_PASSWORD')
        dev_user_id = os.getenv('chat_id')
        try:
            self.redis_client = Redis(host='redis', password=pwd)
            self.redis_client.ping()
        except ConnectionError:
            self.redis_client = None
            logger.error('There is no redis!')

        if not self.redis_client:
            self.clients = set([dev_user_id])
        else:
            self.clients = self.redis_client.smembers('users')
            if len(self.clients) == 0:
                self.add_subscriber(dev_user_id)
        logger.info('Clients set initialized')

    def add_subscriber(self, user_id: int):
        if self.redis_client:
            self.redis_client.sadd('users', user_id)
        self.clients.add(user_id)

    def remove_subscriber(self, user_id: int):
        if self.redis_client:
            self.redis_client.srem('users', user_id)
        self.clients.remove(user_id)


class TGSubscriber():
    user_id: int
    user_preferences: List[int]

    def __init__(self, user_id):
        self.user_id = user_id
        self.user_preferences = []


storage = Storage()


async def init_bot(queue):
    bot_token = os.getenv('bot_token')

    application = ApplicationBuilder().token(bot_token).build()
    # application.bot_data['subscribers'] = storage.clients
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('stop', stop))

    logger.debug('Bot initialized successfully')
    try:
        await application.initialize()
        await application.start()
        await application.updater.start_polling()
        await process_queue(queue)
    except Exception as e:
        logger.error(f'Processing tg messages has broken \n {e}')
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


async def process_queue(queue):
    # if context:
    #     queue = context.bot_data.get('queue')
    while True and queue:
        message = await queue.get()
        await send_tg_message_to_all(message)
        queue.task_done()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    # subscribers = context.bot_data.get('subscribers', storage.clients)
    # if user_id in subscribers:
    #     logger.debug(f'User already in subscribers: {user_id}')
    #     return
    # subscribers.add(user_id)
    storage.add_subscriber(user_id)

    # with open(SUBSCRIBERS_FILE, 'w') as file:
    #     file.write(",".join(filter(None, [str(subs) for subs in
    #       list(set(subscribers))])))
    # logger.debug(f'New tg subscriber: {user_id}')
    await context.bot.send_message(
        user_id,
        'Hello! I am your news bot. I will inform you about news.\n\
        If you need me to stop, use /stop command'
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    # subscribers = context.bot_data.get('subscribers', storage.clients)
    # if user_id not in subscribers:
    #     logger.debug(f'User not in subscribers: {user_id}')
    #     return
    # subscribers.remove(user_id)
    storage.remove_subscriber(user_id)
    # with open(SUBSCRIBERS_FILE, 'w') as file:
    #     file.write(",".join(filter(None, [
    #             str(subs) for subs in list(set(subscribers))
    #         ])))
    logger.debug(f'Removed subscriber: {user_id}')
    await context.bot.send_message(
        user_id,
        'You were successfully removed from subscribers.\n\
            If you need me to return, use /start command'
    )


# def load_subscribers(redis: Redis) -> list:
    # try:
    # with open(SUBSCRIBERS_FILE, 'r') as file:
    #     subscribers = list(map(int, file.read().strip().split(',')))
    # except FileNotFoundError:
    #     logger.error('Could not get subscribers')
    #     subscribers = []
    # subscribers = redis.smembers('users')
    # logger.debug(f'Loaded subscribers: {subscribers}')
    # return subscribers


async def send_tg_message_to_all(message):
    # if context:
    #     subscribers = context.bot_data.get('subscribers', storage.clients)
    # else:
    #     subscribers = storage.clients
    for subscriber_id in storage.clients:
        await send_tg_message(subscriber_id, message)


async def send_tg_message(chat_id, message):
    '''Через бот отправляет сообщение напрямую в канал через telegram api'''
    logger.debug("Sending message to telegram")
    bot_token = os.getenv('bot_token')
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'

    text = "\n\n".join(filter(None, (message.get('title'),
                                     message.get('summary'),
                                     message.get('link'))))
    # if not (check_pattern_func is None):
    #     if not check_pattern_func(text):
    #         return
    params = {
        'text': text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": False,
        "reply_to_message_id": None,
        "chat_id": str(chat_id)
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

        # async with ClientSession() as session:
        #     async with session.get(url, params=params) as response:
        #         status = response.status
    except Exception as e:
        logger.error(e)
        return -1
    logger.debug(f"Sent successfully. Title: {message.get('title','')}")
    return response.status_code


if __name__ == '__main__':
    load_dotenv()
    queue = asyncio.Queue()
    asyncio.run(init_bot(queue))
