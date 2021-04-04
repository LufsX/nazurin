# -*- coding: utf-8 -*-
import shutil
import traceback
import config
from utils import typing, logger, sendDocuments, NazurinError
from sites import SiteManager
from storage import Storage
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, Defaults

sites = SiteManager()
storage = Storage()

def start(update, context):
    update.message.reply_text('嗨!')
@typing
def ping(update, context):
    update.message.reply_text('pong!')
@typing
def get_help(update, context):
    update.message.reply_text('''
    小さな小さな賢将，能够帮助您从各个站点收集图像。
    命令列表:
    /ping - pong
    /pixiv <id> - 查看 Pixiv 作品
    /pixiv_download <id> - 下载 Pixiv 作品
    /danbooru <id> - 查看 danbooru 帖图
    /danbooru_download <id> - 下载 danbooru 帖图
    /yandere <id> - 查看 yandere 帖图
    /yandere_download <id> - 下载 yandere 帖图
    /konachan <id> - 查看 konachan 帖图
    /konachan_download <id> - 下载 konachan 帖图
    /bookmark <id> - bookmark pixiv artwork
    /clear_downloads - 清除下载缓存
    /help - 获取帮助文本
    PS: 给我发 Pixiv/Danbooru/Yandere/Konachan/Twitter URL 来下载图片 😆
    ''')
def collection_update(update, context):
    message = update.message
    message_id = message.message_id
    chat_id = message.chat_id
    bot = context.bot

    # Match URL
    if message.entities:
        entities = message.entities
        text = message.text
    elif message.caption_entities:
        entities = message.caption_entities
        text = message.caption
    else:
        message.reply_text('Error: URL not found')
        return
    # Telegram counts entity offset and length in UTF-16 code units
    text = text.encode('utf-16-le')
    urls = list()
    for item in entities:
        if item.type == 'text_link':
            urls.append(item.url)
        elif item.type == 'url':
            offset = item.offset
            length = item.length
            urls.append(text[offset * 2:(offset + length) * 2].decode('utf-16-le'))

    result = sites.match(urls)
    if not result:
        message.reply_text('Error: No source matched')
        return
    logger.info('Collection update: site=%s, match=%s', result['site'], result['match'].groups())
    # Forward to gallery & Save to album
    bot.forwardMessage(config.GALLERY_ID, chat_id, message_id)
    chat_id = config.ALBUM_ID
    message_id = None # No need to reply to message

    try:
        imgs = sites.handle_update(result)
        sendDocuments(update, context, imgs, chat_id=chat_id)
        storage.store(imgs)
        message.reply_text('Done!')
    except NazurinError as error:
        message.reply_text(error.msg)
def clear_downloads(update, context):
    message = update.message
    try:
        shutil.rmtree('./downloads')
        message.reply_text("downloads directory cleared successfully.")
    except PermissionError:
        message.reply_text("Permission denied.")
    except OSError as error:
        message.reply_text(error.strerror)

def handle_error(update, context):
    logger.error('Update "%s" caused error "%s"', update, context.error)
    traceback.print_exc()

def main():
    global sites, storage
    defaults = Defaults(quote=True)
    urlFilter = Filters.entity('url') | Filters.entity('text_link') | Filters.caption_entity('url') | Filters.caption_entity('text_link')
    sites.load()

    # Set up the Updater
    updater = Updater(config.TOKEN, workers=32, use_context=True, defaults=defaults)
    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    dp.add_handler(CommandHandler('start', start, config.adminFilter, run_async=True))
    dp.add_handler(CommandHandler('ping', ping, config.adminFilter, run_async=True))
    dp.add_handler(CommandHandler('help', get_help, config.adminFilter, run_async=True))
    sites.register_commands(dp)
    dp.add_handler(CommandHandler('clear_downloads', clear_downloads, config.adminFilter, pass_args=True))
    dp.add_handler(MessageHandler(config.adminFilter & urlFilter & (~ Filters.update.channel_posts), collection_update, pass_chat_data=True, run_async=True))

    # log all errors
    dp.add_error_handler(handle_error)

    if config.ENV == 'production':
        # Webhook mode
        updater.start_webhook(listen="0.0.0.0", port=config.PORT, url_path=config.TOKEN, webhook_url=config.WEBHOOK_URL + config.TOKEN, allowed_updates=["message"])
        logger.info('Set webhook')
    else:
        # Polling mode
        updater.start_polling()
        logger.info('Started polling')

    storage.load()
    updater.idle()

if __name__ == '__main__':
    main()
