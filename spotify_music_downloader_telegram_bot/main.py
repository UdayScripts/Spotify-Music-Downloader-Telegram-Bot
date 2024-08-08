from aiogram import Bot, Dispatcher, types
from settings import BASE_DIR, DATABASE_PATH, API_TOKEN, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
from spotdl import Spotdl, DownloaderOptions, Song
from asgiref.sync import sync_to_async
from pathlib import Path
import aiosqlite
import asyncio
import logging
import time
import os

logger: logging.Logger = logging.getLogger('root')
logger.setLevel(logging.NOTSET)

loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()

bot = Bot(token=API_TOKEN, loop=loop)
dispatcher = Dispatcher(bot=bot)

spotdl = Spotdl(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    downloader_settings=DownloaderOptions(output='spotify_tracks')
)

@dispatcher.message_handler(commands=['start'])
async def send_welcome_message(message: types.Message) -> None:
    logger.info(f'{message.from_user.id}: {message.text}')

    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(f"SELECT * FROM User WHERE id='{message.from_user.id}'") as cursor:
            if await cursor.fetchone() is None:
                await db.execute(f'INSERT INTO User VALUES ({message.from_user.id})')
                await db.commit()

    if message.from_user.language_code == 'ru':
        message_text = f"""\
            Привет, @{message.from_user.username}!
            Я являюсь Telegram ботом для скачивания музыки с Spotify.
            Отправьте мне ссылку на Spotify трек, альбом или плейлист, и я отправлю тебе этот трек, альбом или плейлист.
        """
    else:
        message_text = f"""\
            Hello, @{message.from_user.username}!
            I am a Telegram Bot for downloading music from Spotify.
            Send me a link to a Spotify track, album, or playlist and I'll send you that track, album, or playlist.
        """

    sent_message: types.Message = await bot.send_message(chat_id=message.chat.id, text=message_text.replace('\t', ''))
    logger.info(f'Spotify Music Downloader Telegram Bot:\n{sent_message.text}')

@dispatcher.message_handler()
async def send_spotify_media(message: types.Message) -> None:
    logger.info(f'{message.from_user.id}: {message.text}')

    link_type = None
    if message.text.find('https://open.spotify.com/track/') != -1:
        link_type = 'track'
    elif message.text.find('https://open.spotify.com/album/') != -1:
        link_type = 'album'
    elif message.text.find('https://open.spotify.com/playlist/') != -1:
        link_type = 'playlist'

    if link_type in ['track', 'album', 'playlist']:
        if link_type == 'track':
            spotify_track: Song = spotdl.search([message.text])[0]
            message_text = (f'Скачиваю Spotify трек: {spotify_track.display_name}...' 
                            if message.from_user.language_code == 'ru' 
                            else f'Downloading Spotify track: {spotify_track.display_name}...')
        elif link_type == 'album':
            spotify_album_tracks: list[Song] = spotdl.search([message.text])
            message_text = (f'Скачиваю Spotify альбом: {spotify_album_tracks[0].album}...' 
                            if message.from_user.language_code == 'ru' 
                            else f'Downloading Spotify album: {spotify_album_tracks[0].album}...')
        else:
            spotify_playlist_tracks: list[Song] = spotdl.search([message.text])
            message_text = (f'Скачиваю Spotify плейлист: {spotify_playlist_tracks[0].album}...' 
                            if message.from_user.language_code == 'ru' 
                            else f'Downloading Spotify playlist: {spotify_playlist_tracks[0].album}...')

        sent_message: types.Message = await bot.send_message(chat_id=message.chat.id, text=message_text)
        logger.info(f'Spotify Music Downloader Telegram Bot: {sent_message.text}')

        if link_type == 'track':
            _, spotify_track_path = await sync_to_async(spotdl.downloader.search_and_download)(song=spotify_track)

            await bot.delete_message(chat_id=message.chat.id, message_id=sent_message.message_id)
            await message.reply_audio(audio=types.InputFile(spotify_track_path))
            logger.info(f'Spotify Music Downloader Telegram Bot: Sent Spotify track "{spotify_track.display_name}".')

        elif link_type == 'album':
            for spotify_album_track in spotify_album_tracks:
                _, spotify_album_track_path = await sync_to_async(spotdl.downloader.search_and_download)(song=spotify_album_track)
                await message.reply_audio(audio=types.InputFile(spotify_album_track_path))
                logger.info(f'Spotify Music Downloader Telegram Bot: Sent Spotify album track "{spotify_album_track.display_name}".')

        else:  # playlist
            for spotify_playlist_track in spotify_playlist_tracks:
                _, spotify_playlist_track_path = await sync_to_async(spotdl.downloader.search_and_download)(song=spotify_playlist_track)
                await message.reply_audio(audio=types.InputFile(spotify_playlist_track_path))
                await message.reply(f'Track: {spotify_playlist_track.display_name}, Artist: {spotify_playlist_track.artist}, Album: {spotify_playlist_track.album}')
                logger.info(f'Spotify Music Downloader Telegram Bot: Sent Spotify playlist track "{spotify_playlist_track.display_name}".')

        await bot.delete_message(chat_id=message.chat.id, message_id=sent_message.message_id)
        
    else:
        message_text = ('Это не ссылка на Spotify трек, альбом или плейлист!' 
                        if message.from_user.language_code == 'ru' 
                        else "It's not a link to a Spotify track, album, or playlist!")
        sent_message: types.Message = await message.reply(message_text)
        logger.info(f'Spotify Music Downloader Telegram Bot: {sent_message.text}')

async def check_downloaded_spotify_tracks() -> None:
    logger.info('Started asynchronous function for checking downloaded Spotify tracks.')

    spotify_tracks_dir: Path = BASE_DIR / 'spotify_tracks'

    while True:
        for spotify_track in os.listdir(spotify_tracks_dir):
            spotify_track_path: Path = spotify_tracks_dir / spotify_track
            spotify_track_age: float = time.time() - os.path.getatime(spotify_track_path)

            if spotify_track_age > 7 * 24 * 60 * 60:
                logger.info(f'Removed Spotify track "{spotify_track}" age={spotify_track_age / 60 / 60 / 24} days.')
                os.remove(spotify_track_path)

        await asyncio.sleep(60 * 60)

async def start() -> None:
    await dispatcher.start_polling()

if __name__ == '__main__':
    logger.info('Starting asynchronous function for checking downloaded Spotify tracks...')
    loop.create_task(check_downloaded_spotify_tracks())
    logger.info('Starting Spotify Music Downloader Telegram Bot...')
    loop.run_until_complete(start())
