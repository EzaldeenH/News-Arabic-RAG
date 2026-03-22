"""
Telegram Bot Message Handlers.
Handles user messages, inline keyboards, and conversation state.
"""
import logging
from typing import Dict, Any
from aiogram import types, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from httpx import HTTPError, ConnectError, TimeoutException

from bot.app.client.api_client import BackendClient

logger = logging.getLogger(__name__)

router = Router()


# Region and category options for inline keyboards
REGION_OPTIONS = {
    "Middle East": "🌍 الشرق الأوسط",
    "North Africa": "🌍 شمال أفريقيا",
    "Gulf": "🌍 الخليج",
    "Global": "🌍 عالمي"
}

CATEGORY_OPTIONS = {
    "News": "📰 أخبار",
    "Economy": "💰 اقتصاد",
    "Sports": "⚽ رياضة",
    "Technology": "💻 تقنية"
}


class QueryState(StatesGroup):
    """Conversation states for query flow."""
    waiting_for_question = State()
    selecting_region = State()
    selecting_category = State()


def format_response(response: dict) -> str:
    """
    Format the API response into Markdown for Telegram.

    Args:
        response: API response dictionary

    Returns:
        Formatted Markdown string
    """
    answer = response.get("answer", "لا توجد إجابة")
    entities = response.get("entities_found", [])
    sources = response.get("sources", [])
    latency = response.get("latency_ms", 0)

    # Build message
    message = f"{answer}\n\n"

    # Add entities as hashtags if available
    if entities:
        entities_str = " ".join([f"#{entity.replace(' ', '_')}" for entity in entities[:5]])
        message += f"\n*الكيانات:* {entities_str}\n"

    # Add sources if available
    if sources:
        message += "\n*المصادر:*\n"
        for i, source in enumerate(sources[:3], 1):
            title = source.get("title", "مصدر غير معروف")
            url = source.get("url", "#")
            message += f"{i}. [{title}]({url})\n"

    # Add latency
    message += f"\n_وقت الاستجابة: {latency}ms_"

    return message


def create_region_keyboard() -> types.InlineKeyboardMarkup:
    """Create inline keyboard for region selection."""
    keyboard = []
    for region, label in REGION_OPTIONS.items():
        keyboard.append([types.InlineKeyboardButton(text=label, callback_data=f"region_{region}")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_category_keyboard() -> types.InlineKeyboardMarkup:
    """Create inline keyboard for category selection."""
    keyboard = []
    for category, label in CATEGORY_OPTIONS.items():
        keyboard.append([types.InlineKeyboardButton(text=label, callback_data=f"category_{category}")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_cancel_keyboard() -> types.InlineKeyboardMarkup:
    """Create cancel button."""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_query")]
    ])


async def query_backend_with_filters(
    message: Message,
    question: str,
    region: str,
    category: str
) -> None:
    """
    Query backend with specified filters and send response.
    
    Args:
        message: Original message
        question: User's question
        region: Selected region
        category: Selected category
    """
    # Send typing action
    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action="typing"
    )

    try:
        client = await BackendClient.get_client()
        response = await client.query(
            question=question,
            top_k=3
        )

        # Add filter info to response
        filter_info = f"🔹 *المنطقة:* {REGION_OPTIONS.get(region, region)}\n"
        filter_info += f"🔹 *التصنيف:* {CATEGORY_OPTIONS.get(category, category)}\n\n"
        
        formatted_response = filter_info + format_response(response)
        
        await message.answer(
            formatted_response,
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )

    except ConnectError:
        logger.error("Backend connection failed")
        await message.answer(
            "النظام غير متاح حالياً، يرجى المحاولة لاحقاً.",
            parse_mode=ParseMode.MARKDOWN
        )

    except TimeoutException:
        logger.error("Backend request timed out")
        await message.answer(
            "استغرق الطلب وقتاً طويلاً، يرجى المحاولة مرة أخرى.",
            parse_mode=ParseMode.MARKDOWN
        )

    except HTTPError as e:
        logger.error(f"HTTP error: {e}")
        await message.answer(
            "حدث خطأ أثناء معالجة السؤال، يرجى المحاولة مرة أخرى.",
            parse_mode=ParseMode.MARKDOWN
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.answer(
            "حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى.",
            parse_mode=ParseMode.MARKDOWN
        )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.clear()
    
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❓ طرح سؤال", callback_data="ask_question")],
        [types.InlineKeyboardButton(text="🌍 تغيير المنطقة", callback_data="select_region")],
        [types.InlineKeyboardButton(text="📰 تغيير التصنيف", callback_data="select_category")],
    ])
    
    await message.answer(
        "مرحباً بك في نظام الأسئلة والأجوبة العربي! 🇸🇦\n\n"
        "أنا مساعد ذكي متخصص في أخبار **الشرق الأوسط**.\n\n"
        "*اختر ما تريد فعله:*\n"
        "• طرح سؤال للبحث في المصادر\n"
        "• تغيير المنطقة الجغرافية\n"
        "• تغيير تصنيف الأخبار\n\n"
        "أو أرسل سؤالك مباشرة.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    """Handle /help command."""
    await state.clear()
    
    await message.answer(
        "*كيفية الاستخدام:*\n\n"
        "1. أرسل أي سؤال باللغة العربية\n"
        "2. سأبحث في المصادر الموثوقة\n"
        "3. سأجيبك مع ذكر المصادر\n\n"
        "*الميزات المتقدمة:*\n"
        "• تغيير المنطقة: الشرق الأوسط، شمال أفريقيا، الخليج، عالمي\n"
        "• تغيير التصنيف: أخبار، اقتصاد، رياضة، تقنية\n\n"
        "*الأوامر المتاحة:*\n"
        "/start - بدء المحادثة\n"
        "/help - عرض هذه المساعدة\n"
        "/status - حالة النظام\n"
        "/ask - طرح سؤال مع تحديد الفلاتر",
        parse_mode=ParseMode.MARKDOWN
    )


@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    """Handle /ask command - start guided question flow."""
    await state.clear()
    
    keyboard = create_cancel_keyboard()
    
    await message.answer(
        "📝 *اطرح سؤالك:*\n\n"
        "أرسل سؤالك الآن وسأبحث عن الإجابة في المصادر.\n"
        "سيتم استخدام المنطقة والتصنيف الافتراضيين.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    
    await state.set_state(QueryState.waiting_for_question)


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext):
    """Handle /status command."""
    await state.clear()
    
    try:
        client = await BackendClient.get_client()
        health = await client.health_check()

        status_text = "*حالة النظام:*\n\n"
        for service, status in health.get("services", {}).items():
            icon = "✅" if status == "healthy" else "❌"
            status_text += f"{icon} {service}: {status}\n"

        await message.answer(status_text, parse_mode=ParseMode.MARKDOWN)

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        await message.answer("تعذر التحقق من حالة النظام حالياً.")


# ============================================
# Callback Query Handlers (Inline Keyboards)
# ============================================

@router.callback_query(F.data == "cancel_query")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Handle cancel button."""
    await state.clear()
    await callback.message.edit_text("تم إلغاء العملية.")


@router.callback_query(F.data == "ask_question")
async def callback_ask(callback: CallbackQuery, state: FSMContext):
    """Handle ask question button."""
    await state.clear()
    
    keyboard = create_cancel_keyboard()
    
    await callback.message.answer(
        "📝 *اطرح سؤالك:*\n\n"
        "أرسل سؤالك الآن وسأبحث عن الإجابة في المصادر.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await state.set_state(QueryState.waiting_for_question)
    await callback.answer()


@router.callback_query(F.data == "select_region")
async def callback_select_region(callback: CallbackQuery, state: FSMContext):
    """Handle region selection button."""
    await state.clear()
    
    keyboard = create_region_keyboard()
    
    await callback.message.answer(
        "🌍 *اختر المنطقة:*\n\n"
        "سيتم استخدام هذه المنطقة للبحث في الأسئلة التالية.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await state.set_state(QueryState.selecting_region)
    await callback.answer()


@router.callback_query(F.data.startswith("region_"))
async def callback_region_selected(callback: CallbackQuery, state: FSMContext):
    """Handle region selected from keyboard."""
    region = callback.data.replace("region_", "")
    
    # Store in user data (in production, use Redis or database)
    async with state.storage.data as data:
        key = (callback.from_user.id, callback.message.chat.id)
        if key not in data:
            data[key] = {}
        data[key]["selected_region"] = region
    
    await state.clear()
    
    await callback.message.answer(
        f"✅ تم اختيار المنطقة: *{REGION_OPTIONS.get(region, region)}*\n\n"
        "يمكنك الآن طرح سؤالك.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


@router.callback_query(F.data == "select_category")
async def callback_select_category(callback: CallbackQuery, state: FSMContext):
    """Handle category selection button."""
    await state.clear()
    
    keyboard = create_category_keyboard()
    
    await callback.message.answer(
        "📰 *اختر التصنيف:*\n\n"
        "سيتم استخدام هذا التصنيف للبحث في الأسئلة التالية.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await state.set_state(QueryState.selecting_category)
    await callback.answer()


@router.callback_query(F.data.startswith("category_"))
async def callback_category_selected(callback: CallbackQuery, state: FSMContext):
    """Handle category selected from keyboard."""
    category = callback.data.replace("category_", "")
    
    # Store in user data
    async with state.storage.data as data:
        key = (callback.from_user.id, callback.message.chat.id)
        if key not in data:
            data[key] = {}
        data[key]["selected_category"] = category
    
    await state.clear()
    
    await callback.message.answer(
        f"✅ تم اختيار التصنيف: *{CATEGORY_OPTIONS.get(category, category)}*\n\n"
        "يمكنك الآن طرح سؤالك.",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()


# ============================================
# State Handlers (Conversation Flow)
# ============================================

@router.message(QueryState.waiting_for_question)
async def handle_question_input(message: Message, state: FSMContext):
    """Handle user question in guided flow."""
    question = message.text
    
    if not question or len(question) < 3:
        await message.answer(
            "الرجاء إرسال سؤال أطول (3 أحرف على الأقل).",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    # Get stored filters
    async with state.storage.data as data:
        key = (message.from_user.id, message.chat.id)
        user_data = data.get(key, {})
    
    region = user_data.get("selected_region", "Middle East")
    category = user_data.get("selected_category", "News")
    
    await state.clear()
    
    # Query backend
    await query_backend_with_filters(message, question, region, category)


@router.message()
async def handle_message(message: Message, state: FSMContext):
    """
    Handle user questions (direct input without guided flow).
    Sends typing action, queries backend, and formats response.
    """
    # Check if we're in a state - if so, let the state handler deal with it
    current_state = await state.get_state()
    if current_state:
        return
    
    question = message.text

    if not question:
        return

    # Get stored filters
    async with state.storage.data as data:
        key = (message.from_user.id, message.chat.id)
        user_data = data.get(key, {})
    
    region = user_data.get("selected_region", "Middle East")
    category = user_data.get("selected_category", "News")

    # Query backend with filters
    await query_backend_with_filters(message, question, region, category)
