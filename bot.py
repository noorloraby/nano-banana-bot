from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters
import logging
import asyncio
import io
import config
from browser_client import NanoBananaClient, WebsiteError
import signal
import os
import uuid

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ... (imports)

# Global client
browser_client = NanoBananaClient()
pending_media_groups = {}
# Cache to store prompts for callbacks to avoid data limits
# Key: request_id, Value: prompt
generation_cache = {}
# Cache to store media group file_ids so replies to albums can get all images
# Key: media_group_id, Value: list of (file_id, file_type) tuples
media_group_cache = {}
# Map message_id to media_group_id for lookup when replying
message_to_media_group = {}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text="Hello! I am the Nano Banana Bot. Use /img <prompt> or send an image with a caption to generate.\n\nYou can also reply to any message with images to use them as input!"
    )

async def extract_images_from_message(message, bot=None) -> list:
    """Extract and download all images from a message (photos or image documents).
    If the message is part of a media group, extracts ALL images from that group.
    Returns a list of absolute file paths."""
    image_paths = []
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Check if this message is part of a cached media group
    msg_id = message.message_id
    media_group_id = message.media_group_id or message_to_media_group.get(msg_id)
    
    if media_group_id and media_group_id in media_group_cache:
        # Extract all images from the cached media group
        logger.info(f"Found media group {media_group_id} with {len(media_group_cache[media_group_id])} files")
        for file_id, file_type in media_group_cache[media_group_id]:
            try:
                if bot:
                    file_obj = await bot.get_file(file_id)
                else:
                    # Fallback: try to get file from message context
                    file_obj = await message._bot.get_file(file_id)
                
                ext = "jpg" if file_type == "photo" else file_type
                file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")
                await file_obj.download_to_drive(file_path)
                image_paths.append(os.path.abspath(file_path))
            except Exception as e:
                logger.error(f"Failed to download file {file_id}: {e}")
        return image_paths
    
    # Single message case - extract directly
    # Handle photos
    if message.photo:
        photo_file = await message.photo[-1].get_file()
        file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.jpg")
        await photo_file.download_to_drive(file_path)
        image_paths.append(os.path.abspath(file_path))
    
    # Handle documents (could be images sent as files)
    if message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("image/"):
            doc_file = await message.document.get_file()
            ext = mime.split("/")[-1] if "/" in mime else "jpg"
            file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")
            await doc_file.download_to_drive(file_path)
            image_paths.append(os.path.abspath(file_path))
    
    return image_paths

async def img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Please provide a prompt. Example: /img A retro futuristic city")
        return

    # Check if this is a reply to a message with images
    reply_images = []
    if update.message.reply_to_message:
        reply_images = await extract_images_from_message(update.message.reply_to_message, context.bot)
    
    try:
        await process_generation(update, context, prompt, reply_images if reply_images else None)
    finally:
        # Cleanup reply images
        for f in reply_images:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except: pass

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    media_group_id = update.message.media_group_id
    photo_file = await update.message.photo[-1].get_file()
    
    # Cache file_id for media group lookups (for reply-to-album support)
    if media_group_id:
        if media_group_id not in media_group_cache:
            media_group_cache[media_group_id] = []
        # Store the highest resolution photo's file_id
        file_id = update.message.photo[-1].file_id
        if (file_id, "photo") not in media_group_cache[media_group_id]:
            media_group_cache[media_group_id].append((file_id, "photo"))
        # Map this message_id to its media_group_id
        message_to_media_group[update.message.message_id] = media_group_id
        logger.info(f"Cached photo in media group {media_group_id}, total files: {len(media_group_cache[media_group_id])}")
    
    # Create temp directory
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.jpg")
    await photo_file.download_to_drive(file_path)
    abs_path = os.path.abspath(file_path)
    
    # Extract images from reply_to_message if present
    reply_images = []
    if update.message.reply_to_message:
        reply_images = await extract_images_from_message(update.message.reply_to_message, context.bot)

    # Single Photo Case
    if not media_group_id:
        if not update.message.caption:
            await update.message.reply_text("Please provide a prompt (caption) with your image.")
            # Cleanup immediately
            if os.path.exists(abs_path):
                os.remove(abs_path)
            for f in reply_images:
                if os.path.exists(f):
                    try: os.remove(f)
                    except: pass
            return

        prompt = update.message.caption
        # Combine reply images with the new image
        all_images = reply_images + [abs_path]
        try:
            await process_generation(update, context, prompt, all_images)
        finally:
            for f in all_images:
                if os.path.exists(f):
                    try: os.remove(f)
                    except: pass
        return

    # Media Group Case (Album)
    if media_group_id not in pending_media_groups:
        pending_media_groups[media_group_id] = {
            'files': [],
            'reply_images': reply_images,  # Store reply images from first message
            'prompt': None,
            'task': None,
            'chat_id': update.effective_chat.id,
            'message_id': update.message.message_id # Use the first message id for reply
        }

    group = pending_media_groups[media_group_id]
    group['files'].append(abs_path)
    
    # Capture caption from any message in the group
    if update.message.caption:
        group['prompt'] = update.message.caption

    # Reset/Start debounce timer
    if group['task']:
        group['task'].cancel()
    
    msg_id = update.message.message_id # Keep updating or use first? Using first is fine.
    
    async def process_group():
        await asyncio.sleep(2) # Wait 2 seconds for other photos
        if media_group_id in pending_media_groups:
            data = pending_media_groups.pop(media_group_id)
            # Combine reply images with album files
            all_files = data.get('reply_images', []) + data['files']
            try:
                if not data['prompt']:
                     await context.bot.send_message(chat_id=data['chat_id'], text="Please provide a caption for the album.", reply_to_message_id=data['message_id'])
                     return
                
                await process_generation_internal(context, data['chat_id'], data['prompt'], all_files, data['message_id'])

            finally:
                # Cleanup all files
                for f in all_files:
                    if os.path.exists(f):
                        try:
                            os.remove(f)
                        except: pass
    
    group['task'] = asyncio.create_task(process_group())

async def process_generation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str, image_paths: list = None):
    # Wrapper for standard calls
    await process_generation_internal(context, update.effective_chat.id, prompt, image_paths, update.message.message_id)

async def process_generation_internal(context, chat_id, prompt, image_paths, reply_to_msg_id):
    await context.bot.send_message(chat_id=chat_id, text=f"Generating image... (Images input: {len(image_paths) if image_paths else 0})", reply_to_message_id=reply_to_msg_id)

    try:
        # Generate (returns a list of io.BytesIO)
        images_data = await browser_client.generate_image(prompt, image_paths)
        
        if not images_data:
            await context.bot.send_message(chat_id=chat_id, text="No images were generated.", reply_to_message_id=reply_to_msg_id)
            return

        # Send each image
        for idx, img_stream in enumerate(images_data):
            try:
                # Reset stream pointer just in case
                img_stream.seek(0)
                # Create UPSCALE buttons
                req_id = str(uuid.uuid4())[:8]
                generation_cache[req_id] = prompt
                
                keyboard = [
                    [
                        InlineKeyboardButton("Upscale 1K", callback_data=f"up:{req_id}:{idx}:1K"),
                        InlineKeyboardButton("Upscale 2K", callback_data=f"up:{req_id}:{idx}:2K"),
                        InlineKeyboardButton("Upscale 4K", callback_data=f"up:{req_id}:{idx}:4K"),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await context.bot.send_photo(
                    chat_id=chat_id, 
                    photo=img_stream, 

                    reply_to_message_id=reply_to_msg_id,
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Failed to send image {idx}: {e}")
    
    except WebsiteError as e:
        logger.warning(f"Website rejected request: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Request rejected: {e}", reply_to_message_id=reply_to_msg_id)
                
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        await context.bot.send_message(chat_id=chat_id, text="Sorry, something went wrong with the generation.", reply_to_message_id=reply_to_msg_id)



async def upscale_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    # Format: up:{req_id}:{img_idx}:{scale}
    try:
        _, req_id, img_idx, scale = data.split(":")
        img_idx = int(img_idx)
    except ValueError:
        await query.edit_message_caption(caption="Invalid callback data.")
        return

    # Try to get prompt from cache first
    prompt = generation_cache.get(req_id)
    
    # Fallback: Get prompt from the replied message (Generic/Stateless)
    if not prompt:
        reply_msg = query.message.reply_to_message
        if reply_msg:
            if reply_msg.text:
                prompt = reply_msg.text
                # Remove '/img' command if present
                if prompt.startswith('/img'):
                    prompt = prompt.replace('/img', '', 1).strip()
            elif reply_msg.caption:
                prompt = reply_msg.caption
    
    if not prompt:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Could not determine prompt for upscaling (Session expired and original message lost).")
        return

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Upscaling image {img_idx+1} to {scale}...", reply_to_message_id=query.message.message_id)

    try:
        upscaled_stream = await browser_client.upscale_image(prompt, img_idx, scale)
        
        if not upscaled_stream:
             await context.bot.send_message(chat_id=update.effective_chat.id, text="Failed to retrieve upscaled image.")
             return

        upscaled_stream.seek(0)
        await context.bot.send_document(
            chat_id=update.effective_chat.id,
            document=upscaled_stream,
            filename=f"upscaled_{scale}_{req_id}.png",
            # caption=f"Upscaled to {scale}", # Optional: User seems to prefer minimal captions, but this is a file.
            reply_to_message_id=query.message.message_id
        )

    except WebsiteError as e:
        logger.warning(f"Website rejected upscale request: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"⚠️ Upscale rejected: {e}")

    except Exception as e:
        logger.error(f"Upscaling failed: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Upscaling failed: {e}")

async def handle_text_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text-only messages that are replies to messages containing images."""
    # Only process if this is a reply to another message
    if not update.message.reply_to_message:
        return
    
    reply_msg = update.message.reply_to_message
    
    # Check if the replied message has images (photo or image document)
    has_photo = reply_msg.photo is not None and len(reply_msg.photo) > 0
    has_image_doc = (reply_msg.document and 
                     reply_msg.document.mime_type and 
                     reply_msg.document.mime_type.startswith("image/"))
    
    # Also check if this message is part of a cached media group
    is_in_media_group = (
        reply_msg.media_group_id in media_group_cache or
        reply_msg.message_id in message_to_media_group
    )
    
    if not has_photo and not has_image_doc and not is_in_media_group:
        # Not a reply to an image, ignore
        return
    
    prompt = update.message.text
    if not prompt or not prompt.strip():
        return
    
    # Extract images from the replied message (will use cache for albums)
    reply_images = await extract_images_from_message(reply_msg, context.bot)
    
    if not reply_images:
        await update.message.reply_text("Could not extract images from the replied message.")
        return
    
    try:
        await process_generation(update, context, prompt.strip(), reply_images)
    finally:
        # Cleanup
        for f in reply_images:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle documents that are images (sent as files, not compressed)."""
    doc = update.message.document
    if not doc:
        return
    
    mime = doc.mime_type or ""
    if not mime.startswith("image/"):
        return  # Not an image, ignore
    
    media_group_id = update.message.media_group_id
    
    # Cache file_id for media group lookups (for reply-to-album support)
    if media_group_id:
        if media_group_id not in media_group_cache:
            media_group_cache[media_group_id] = []
        # Store the document's file_id
        file_id = doc.file_id
        ext = mime.split("/")[-1] if "/" in mime else "jpg"
        if (file_id, ext) not in media_group_cache[media_group_id]:
            media_group_cache[media_group_id].append((file_id, ext))
        # Map this message_id to its media_group_id
        message_to_media_group[update.message.message_id] = media_group_id
        logger.info(f"Cached document in media group {media_group_id}, total files: {len(media_group_cache[media_group_id])}")
    
    # Download the document
    temp_dir = "temp"
    os.makedirs(temp_dir, exist_ok=True)
    ext = mime.split("/")[-1] if "/" in mime else "jpg"
    file_path = os.path.join(temp_dir, f"{uuid.uuid4()}.{ext}")
    doc_file = await doc.get_file()
    await doc_file.download_to_drive(file_path)
    abs_path = os.path.abspath(file_path)
    
    # Extract images from reply_to_message if present
    reply_images = []
    if update.message.reply_to_message:
        reply_images = await extract_images_from_message(update.message.reply_to_message, context.bot)

    # Single Document Case
    if not media_group_id:
        if not update.message.caption:
            await update.message.reply_text("Please provide a prompt (caption) with your image file.")
            if os.path.exists(abs_path):
                os.remove(abs_path)
            for f in reply_images:
                if os.path.exists(f):
                    try: os.remove(f)
                    except: pass
            return

        prompt = update.message.caption
        all_images = reply_images + [abs_path]
        try:
            await process_generation(update, context, prompt, all_images)
        finally:
            for f in all_images:
                if os.path.exists(f):
                    try: os.remove(f)
                    except: pass
        return

    # Media Group Case (Album of documents)
    if media_group_id not in pending_media_groups:
        pending_media_groups[media_group_id] = {
            'files': [],
            'reply_images': reply_images,
            'prompt': None,
            'task': None,
            'chat_id': update.effective_chat.id,
            'message_id': update.message.message_id
        }

    group = pending_media_groups[media_group_id]
    group['files'].append(abs_path)
    
    if update.message.caption:
        group['prompt'] = update.message.caption

    if group['task']:
        group['task'].cancel()
    
    async def process_group():
        await asyncio.sleep(2)
        if media_group_id in pending_media_groups:
            data = pending_media_groups.pop(media_group_id)
            all_files = data.get('reply_images', []) + data['files']
            try:
                if not data['prompt']:
                    await context.bot.send_message(chat_id=data['chat_id'], text="Please prompt for the album.", reply_to_message_id=data['message_id'])
                    return
                
                await process_generation_internal(context, data['chat_id'], data['prompt'], all_files, data['message_id'])
            finally:
                for f in all_files:
                    if os.path.exists(f):
                        try: os.remove(f)
                        except: pass
    
    group['task'] = asyncio.create_task(process_group())

async def post_init(application):
    """Initializes the browser when the bot application starts."""
    await browser_client.start()

async def post_shutdown(application):
    """Cleans up browser resources when the bot application stops."""
    await browser_client.stop()

if __name__ == '__main__':
    if not config.TELEGRAM_TOKEN:
        print("Error: TELEGRAM_TOKEN not found in environment variables.")
        exit(1)

    application = ApplicationBuilder().token(config.TELEGRAM_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    
    # Handlers
    application.add_handler(CommandHandler('start', start_command))
    application.add_handler(CommandHandler('img', img_command))
    application.add_handler(CallbackQueryHandler(upscale_callback, pattern="^up:"))
    application.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, handle_photo))
    # Handle image documents (files sent as documents, not compressed)
    application.add_handler(MessageHandler(filters.Document.IMAGE & ~filters.COMMAND, handle_document))
    # Handle text-only replies to images (must be after PHOTO/DOCUMENT handlers to not conflict)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.REPLY, handle_text_reply))

    print("Bot is running... Press Ctrl+C to stop.")
    
    # Run the bot
    application.run_polling()
