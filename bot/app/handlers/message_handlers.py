"""
Telegram Bot Message Handlers.
Handles user messages, inline keyboards, and conversation state.
"""
import logging
from typing import Dict, Any
from aiogram import types, Router, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from httpx import HTTPError, ConnectError, TimeoutException

from bot.app.client.api_client import BackendClient

logger = logging.getLogger(__name__)

router = Router()


# Region and category options for inline keyboards
ALJAZEERA_CATEGORIES = {
    "أخبار": ["عربي", "دولي", "سياسة", "مراسلو الجزيرة", "صحافة", "تحقق", "وسم", "موسوعة", "حريات", "بالصور"],
    "اقتصاد": ["اقتصاد", "عربي", "دولي", "أسواق", "شخصي", "ريادة"],
    "رأي": ["مقالات", "مدونات"],
    "ميدان": ["إعلام", "دراسات", "تراث", "سلاح", "صراع", "فكر ونفس", "وجوه", "ملفات"],
    "متخصصة": ["رياضة", "علوم وبيئة", "صحة", "تقنية", "أسلوب حياة", "أسرة", "سفر", "ثقافة", "فن", "منوعات"],
    "محليات": ["فلسطين", "اليمن", "سوريا", "السودان", "مصر", "العراق", "لبنان", "المغرب", "ليبيا"]
}

class QueryState(StatesGroup):
    """Conversation states for query flow."""
    waiting_for_question = State()
    selecting_main_category = State()
    selecting_subcategory = State()


import html

def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return html.escape(text)

def format_response(response: dict) -> str:
    """
    Format the API response into HTML for Telegram.
    """
    answer = response.get("answer", "لا توجد إجابة")
    entities = response.get("entities_found", [])
    sources = response.get("sources", [])
    latency = response.get("latency_ms", 0)

    # Check if the AI returned a "no information" response
    no_info_phrases = ["لا أملك معلومات كافية", "لا توجد معلومات", "عذراً، لا يمكنني", "لا يتوفر في السياق"]
    is_no_info = False
    if any(phrase in answer for phrase in no_info_phrases):
        # If the phrase is present, check if the entire answer is short, meaning it didn't provide partial info
        if len(answer) < 100:
            is_no_info = True

    # Build message with HTML
    message = f"{escape_html(answer)}\n\n"

    # Add entities as hashtags if available (and it's not a no-info response)
    if entities and not is_no_info:
        entities_str = " ".join([f"#{escape_html(entity.replace(' ', '_'))}" for entity in entities[:5]])
        message += f"\n<b>الكيانات:</b> {entities_str}\n"

    # Add sources if available
    if sources:
        if is_no_info:
            message += "\n<i>المصادر التي تم فحصها (ولكن لم تحتوِ على إجابة محددة):</i>\n"
        else:
            message += "\n<b>المصادر:</b>\n"
            
        # De-duplicate by URL to avoid showing multiple chunks from the same article
        seen_urls = set()
        unique_sources = []
        for s in sources:
            url = s.get("url")
            if url and url not in seen_urls and url != "#":
                seen_urls.add(url)
                unique_sources.append(s)
        
        for i, source in enumerate(unique_sources[:5], 1):
            title = source.get("title", "مصدر الأخبار")
            url = source.get("url")
            author = source.get("author")
            date = source.get("date")
            
            # Format: 1. <a href="URL">Title</a> - Author (Date)
            source_line = f"{i}. <a href=\"{url}\">{escape_html(title)}</a>"
            if author and author != "الجزيرة نت":
                source_line += f" - <i>{escape_html(author)}</i>"
            if date:
                display_date = date.split('T')[0] if 'T' in date else date
                source_line += f" ({escape_html(display_date)})"
            
            message += f"{source_line}\n"

    # Add latency
    message += f"\n<code>وقت الاستجابة: {latency}ms</code>"

    return message


def create_main_category_keyboard() -> types.InlineKeyboardMarkup:
    """Create inline keyboard for main category selection."""
    keyboard = []
    row = []
    for category in ALJAZEERA_CATEGORIES.keys():
        row.append(types.InlineKeyboardButton(text=category, callback_data=f"main_{category}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([types.InlineKeyboardButton(text="الكل (بدون فلتر)", callback_data="main_all")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_subcategory_keyboard(main_category: str) -> types.InlineKeyboardMarkup:
    """Create inline keyboard for subcategory selection."""
    keyboard = []
    row = []
    subcategories = ALJAZEERA_CATEGORIES.get(main_category, [])
    for sub in subcategories:
        row.append(types.InlineKeyboardButton(text=sub, callback_data=f"sub_{main_category}_{sub}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([types.InlineKeyboardButton(text=f"كل {main_category}", callback_data=f"sub_{main_category}_all")])
    keyboard.append([types.InlineKeyboardButton(text="🔙 رجوع", callback_data="select_category")])
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_cancel_keyboard() -> types.InlineKeyboardMarkup:
    """Create cancel button."""
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❌ إلغاء", callback_data="cancel_query")]
    ])


async def query_backend_with_filters(
    message: Message,
    question: str,
    main_category: str,
    subcategory: str
) -> None:
    """
    Query backend with specified filters and send response.
    
    Args:
        message: Original message
        question: User's question
        main_category: Selected main category
        subcategory: Selected subcategory
    """
    # Send typing action
    await message.bot.send_chat_action(
        chat_id=message.chat.id,
        action="typing"
    )

    try:
        client = BackendClient()
        response = await client.query(
            question=question,
            main_category=main_category,
            subcategory=subcategory
        )

        # Add filter info to response
        main_label = main_category if main_category else "الكل"
        sub_label = subcategory if subcategory else "الكل"
        filter_info = f"🔹 <b>التصنيف الرئيسي:</b> {main_label}\n"
        filter_info += f"🔹 <b>التصنيف الفرعي:</b> {sub_label}\n\n"
        
        formatted_response = filter_info + format_response(response)
        
        await message.answer(
            formatted_response,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )

    except ConnectError:
        logger.error("Backend connection failed")
        await message.answer(
            "النظام غير متاح حالياً، يرجى المحاولة لاحقاً.",
            parse_mode=ParseMode.HTML
        )

    except TimeoutException:
        logger.error("Backend request timed out")
        await message.answer(
            "استغرق الطلب وقتاً طويلاً، يرجى المحاولة مرة أخرى.",
            parse_mode=ParseMode.HTML
        )

    except HTTPError as e:
        logger.error(f"HTTP error: {e}")
        await message.answer(
            "حدث خطأ أثناء معالجة السؤال، يرجى المحاولة مرة أخرى.",
            parse_mode=ParseMode.HTML
        )

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        await message.answer(
            "حدث خطأ غير متوقع، يرجى المحاولة مرة أخرى.",
            parse_mode=ParseMode.HTML
        )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command."""
    await state.set_state(None)

    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="❓ طرح سؤال", callback_data="ask_question")],
        [types.InlineKeyboardButton(text="📰 تغيير التصنيف", callback_data="select_category")],
    ])

    await message.answer(
        "مرحباً بك في مساعد أخبار الجزيرة الذكي! 🟢\n\n"
        "أنا مساعد ذكي أستمد معلوماتي من **الجزيرة نت**.\n\n"
        "*اختر ما تريد فعله:*\n"
        "• طرح سؤال للبحث في الأخبار والمقالات\n"
        "• تغيير التصنيف (أخبار، اقتصاد، رياضة...)\n\n"
        "أو أرسل سؤالك مباشرة.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@router.message(F.text.lower().in_({
    "hi", "hello", "hey", "مرحبا", "مرحباً", "السلام عليكم", 
    "هلا", "اهلين", "أهلاً", "اهلا", "صباح الخير", "مساء الخير",
    "يا هلا", "هلو", "كيف الحال", "كيفك", "شلونك", "ازيك",
    "واتساب", "سلام", "هاي"
}))
async def handle_greeting(message: Message, state: FSMContext):
    """Handle common greetings by showing the start menu."""
    await cmd_start(message, state)


@router.message(Command("help"))
async def cmd_help(message: Message, state: FSMContext):
    """Handle /help command."""
    await state.set_state(None)

    await message.answer(
        "*كيفية الاستخدام:*\n\n"
        "1. أرسل أي سؤال باللغة العربية\n"
        "2. سأبحث في مقالات وأخبار الجزيرة نت\n"
        "3. سأجيبك مع ذكر المصادر\n\n"
        "*الميزات المتقدمة:*\n"
        "• تغيير التصنيف: البحث داخل أقسام محددة (سياسة، اقتصاد، محليات فلسطين...)\n\n"
        "*الأوامر المتاحة:*\n"
        "/start - بدء المحادثة\n"
        "/help - عرض هذه المساعدة\n"
        "/status - حالة النظام\n"
        "/ask - طرح سؤال مع تحديد الفلاتر",
        parse_mode=ParseMode.HTML
    )

@router.message(Command("ask"))
async def cmd_ask(message: Message, state: FSMContext):
    """Handle /ask command - start guided question flow."""
    await state.set_state(None)
    
    keyboard = create_cancel_keyboard()
    
    await message.answer(
        "📝 *اطرح سؤالك:*\n\n"
        "أرسل سؤالك الآن وسأبحث عن الإجابة في المصادر.\n"
        "سيتم استخدام التصنيف الافتراضي أو ما اخترته مسبقاً.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    
    await state.set_state(QueryState.waiting_for_question)


@router.message(Command("status"))
async def cmd_status(message: Message, state: FSMContext):
    """Handle /status command."""
    await state.set_state(None)
    
    try:
        client = BackendClient()
        health = await client.health_check()

        status_text = "*حالة النظام:*\n\n"
        for service, status in health.get("services", {}).items():
            icon = "✅" if status == "healthy" else "❌"
            status_text += f"{icon} {service}: {status}\n"

        await message.answer(status_text, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"Status check failed: {e}")
        await message.answer("تعذر التحقق من حالة النظام حالياً.")


# ============================================
# Callback Query Handlers (Inline Keyboards)
# ============================================

@router.callback_query(F.data == "cancel_query")
async def callback_cancel(callback: CallbackQuery, state: FSMContext):
    """Handle cancel button."""
    await state.set_state(None)
    await callback.message.edit_text("تم إلغاء العملية.")


@router.callback_query(F.data == "ask_question")
async def callback_ask(callback: CallbackQuery, state: FSMContext):
    """Handle ask question button."""
    await state.set_state(None)
    
    keyboard = create_cancel_keyboard()
    
    await callback.message.answer(
        "📝 *اطرح سؤالك:*\n\n"
        "أرسل سؤالك الآن وسأبحث عن الإجابة في المصادر.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await state.set_state(QueryState.waiting_for_question)
    await callback.answer()


@router.callback_query(F.data == "select_category")
async def callback_select_category(callback: CallbackQuery, state: FSMContext):
    """Handle category selection button."""
    await state.set_state(None)
    
    keyboard = create_main_category_keyboard()
    
    await callback.message.answer(
        "📰 *اختر التصنيف الرئيسي:*\n\n"
        "سيتم استخدام هذا التصنيف للبحث في الأسئلة التالية.",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )
    await state.set_state(QueryState.selecting_main_category)
    await callback.answer()


@router.callback_query(F.data.startswith("main_"))
async def callback_main_category_selected(callback: CallbackQuery, state: FSMContext):
    """Handle main category selected from keyboard."""
    category = callback.data.replace("main_", "")
    
    if category == "all":
        await state.update_data(selected_main_category=None, selected_subcategory=None)
        await state.set_state(None)
        await callback.message.answer(
            "✅ تم اختيار البحث في *كل التصنيفات*\n\n"
            "يمكنك الآن طرح سؤالك.",
            parse_mode=ParseMode.HTML
        )
    else:
        # Store in user data
        await state.update_data(selected_main_category=category)
        
        keyboard = create_subcategory_keyboard(category)
        await callback.message.answer(
            f"📰 *اختر التصنيف الفرعي لـ {category}:*",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
        await state.set_state(QueryState.selecting_subcategory)
    await callback.answer()


@router.callback_query(F.data.startswith("sub_"))
async def callback_subcategory_selected(callback: CallbackQuery, state: FSMContext):
    """Handle subcategory selected from keyboard."""
    # Data is like sub_أخبار_سياسة
    data = callback.data.replace("sub_", "").split("_")
    if len(data) >= 2:
        main_category = data[0]
        subcategory = "_".join(data[1:])
        
        if subcategory == "all":
            await state.update_data(selected_subcategory=None)
            sub_display = "الكل"
        else:
            await state.update_data(selected_subcategory=subcategory)
            sub_display = subcategory
        
        await state.set_state(None)
        await callback.message.answer(
            f"✅ تم اختيار التصنيف: *{main_category}* ➔ *{sub_display}*\n\n"
            "يمكنك الآن طرح سؤالك.",
            parse_mode=ParseMode.HTML
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
            parse_mode=ParseMode.HTML
        )
        return
    
    # Get stored filters
    user_data = await state.get_data()
    
    main_category = user_data.get("selected_main_category")
    subcategory = user_data.get("selected_subcategory")
    
    await state.set_state(None)
    
    # Query backend
    await query_backend_with_filters(message, question, main_category, subcategory)


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
    user_data = await state.get_data()
    
    main_category = user_data.get("selected_main_category")
    subcategory = user_data.get("selected_subcategory")

    # Query backend with filters
    await query_backend_with_filters(message, question, main_category, subcategory)
