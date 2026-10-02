import regex as re
import os
import logging
from typos import fix_typos
from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters
)

TOKEN = os.getenv("TELEGRAM_TOKEN", "")


async def start(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):
    if update.message:
        await update.message.reply_text(
            """Для использования отправьте сообщение в формате:
UnDumb: текст
Пример: UnDumb: Это тестовое сообщение... оно написано "неправильно", а внутри "кавычек есть "ещё одни кавычки" для проверки". здесь предложение начинается с маленькой буквы после точки. а здесь тоже.
Запятые ,тоже ,расставлены неправильно ,а здесь,запятая,вообще,без пробелов. Тест , тест , тест.
Температура -5 °C, диапазон 10-20 °C, размер 5x10 см, вероятность 1/2, 1/4 и 3/4, а погрешность +-5%.
Это (c) 2026, (r) Example, (tm) TypoTherapy. Приблизительно ~= 66.
"""
        )


logging.basicConfig(
    level=logging.ERROR,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(name)s | "
        "%(message)s"
    ),
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TypoTherapy")

logging.getLogger("telegram").setLevel(logging.ERROR)
logging.getLogger("telegram.ext").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)


def protect(text):
    protected = []

    def save(match):
        protected.append(match.group(0))
        return f"\x00{len(protected) - 1}\x00"

    text = re.sub(r"```[\s\S]*?```", save, text)
    text = re.sub(r"`[^`\n]*`", save, text)
    text = re.sub(r"https?://[^\s<>]+|www\.[^\s<>]+", save, text)
    text = re.sub(r"\[[^\]\n]+\]\([^)]+\)", save, text)

    return text, protected


def restore(text, protected):
    def restore_item(match):
        index = int(match.group(1))
        return protected[index]

    return re.sub(r"\x00(\d+)\x00", restore_item, text)


ABBREVIATION_PATTERNS = [
    r"и.\s т.\s д. ", r"и.\s т.\s п. ", r"т.\s е. ", r"т.\s к. ",
    r"в\s+т.\s ч. ", r"с.\s ш. ", r"ю.\s ш. ", r"в.\s и. ", r"в. ",
    r"вв. ", r"г. ", r"гг. ", r"до\s+н.\s э. ", r"н.\s э. ", r"тыс. ",
    r"род. ", r"р. ", r"сокр. ", r"чел. ", r"к.\s т.\s н. ", r"к.\s г.\s н. ",
    r"д.\s т.\s н. ", r"д.\s г.\s н. ", r"и\s+пр. ", r"см. ", r"ср. ",
    r"и.\s*о. ", r"стр. ", r"рис. ", r"табл. ", r"илл. ", r"им. ", r"др. ",
    r"напр. ", r"ок. ",
]

ABBREVIATION_RE = re.compile(
    r"(?<!\w)(?:" + "|".join(ABBREVIATION_PATTERNS) + r")",
    re.IGNORECASE
)


def protect_abbreviations(text):
    protected = []

    def save(match):
        protected.append(match.group(0))
        return f"\x03{len(protected) - 1}\x04"

    text = ABBREVIATION_RE.sub(save, text)
    return text, protected


def restore_abbreviations(text, protected):
    def restore(match):
        return protected[int(match.group(1))]

    return re.sub(r"\x03(\d+)\x04", restore, text)


SENTENCE_END_RE = re.compile(
    r"(?P<punc>[.!?…]+)"
    r"(?P<spaces>[ \t]+)"
    r"(?P<lower>[а-яё])"
)

ABBREVIATION_AT_END_RE = re.compile(
    r"(?:" + "|".join(ABBREVIATION_PATTERNS) + r")"
                                               r"[ \t]*$",
    re.IGNORECASE
)


def is_abbreviation_before(text, position):
    start = max(0, position - 50)
    fragment = text[start:position]
    return bool(ABBREVIATION_AT_END_RE.search(fragment))


def capitalise_sentences(text):
    def replace(match):
        punctuation = match.group("punc")
        if is_abbreviation_before(text, match.start("punc")):
            return match.group(0)
        return (
                punctuation
                + match.group("spaces")
                + match.group("lower").upper()
        )

    return SENTENCE_END_RE.sub(replace, text)


RULES = [
    (r"\.{3,}", "…"),
    (r"\(c\)", "©"),
    (r"\(r\)", "®"),
    (r"\(tm\)", "™"),
    (r"\+-", "±"),
    (r"~=", "≈"),
    (r"№№", "№"),
    (r"\b1/2\b", "½"),
    (r"\b1/4\b", "¼"),
    (r"\b3/4\b", "¾"),
    (r"(?<=\d)\s*[xх]\s*(?=\d)", " × "),
    (r"(?<=[A-Za-zА-Яа-яЁё])'(?=[A-Za-zА-Яа-яЁё])", "’"),
    (r"[ \t]{2,}", " "),
]


def fix_commas(text):
    text = re.sub(r"[ \t]+,", ",", text)
    text = re.sub(r",[ \t]+", ", ", text)
    text = re.sub(r",(?=[А-ЯЁа-яёA-Za-z])", ", ", text)
    text = re.sub(r"[ \t]+([!?;:])", r"\1", text)
    text = re.sub(r"([!?;:])(?=[А-ЯЁа-яёA-Za-z])", r"\1 ", text)
    return text


def replace_quotes(text):
    chars = list(text)
    stack = []
    for i, char in enumerate(chars):
        if char != '"':
            continue
        prev = chars[i - 1] if i > 0 else ""
        next_char = chars[i + 1] if i + 1 < len(chars) else ""

        opening = (i == 0 or prev.isspace() or prev in "([{—–-:;,.!?")
        closing = (i == len(chars) - 1 or next_char.isspace() or next_char in ".,!?;:)]}»")

        if opening and not closing:
            if "outer_existing" in stack or stack:
                chars[i] = "„"
                stack.append("inner")
            else:
                chars[i] = "«"
                stack.append("outer")
        elif closing:
            if stack:
                level = stack[-1]
                chars[i] = "»" if level == "outer" else "“"
                stack.pop()
            else:
                chars[i] = "»"
        else:
            if stack:
                level = stack[-1]
                chars[i] = "»" if level == "outer" else "“"
                stack.pop()
            else:
                chars[i] = "«"
                stack.append("outer")
    return "".join(chars)


def replace_dashes(text):
    text = re.sub(r"(?<=\d)[ \t]+-[ \t]+(?=\d)", " − ", text)
    text = re.sub(r"--+", "—", text)
    text = re.sub(r"(?<=\S)[ \t]*—[ \t]*(?=\S)", " — ", text)
    text = re.sub(r"([,;:])\s+-{1,2}\s+", r"\1 — ", text)
    text = re.sub(r"(?<=\d)[ \t]*-[ \t]*(?=\d)", "—", text)
    text = re.sub(r"(?<![\w−])-(?=\d)", "−", text)
    return text


def split_telegram_text(text, limit=4096):
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < 1:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n ")
    if text:
        chunks.append(text)
    return chunks


ABBREVIATION_SPACES = [
    (r"\bи.\s т.\s д. ", "и.\u00A0т.\u00A0д. "),
    (r"\bи.\s т.\s п. ", "и.\u00A0т.\u00A0п. "),
    (r"\bт.\s е. ", "т.\u00A0е. "),
    (r"\bт.\s к. ", "т.\u00A0к. "),
    (r"\bв\s+т.\s ч. ", "в\u00A0т.\u00A0ч. "),
    (r"\bдо\s+н.\s э. ", "до\u00A0н.\u00A0э. "),
    (r"\bн.\s э. ", "н.\u00A0э. "),
    (r"\bк.\s т.\s н. ", "к.\u00A0т.\u00A0н. "),
    (r"\bк.\s г.\s н. ", "к.\u00A0г.\u00A0н. "),
    (r"\bд.\s т.\s н. ", "д.\u00A0т.\u00A0н. "),
    (r"\bд.\s г.\s н. ", "д.\u00A0г.\u00A0н. "),
    (r"\bи.\s о. ", "и.\u00A0о. "),
    (r"\bс.\s ш. ", "с.\u00A0ш. "),
    (r"\bю.\s ш. ", "ю.\u00A0ш. "),
]

SIMPLE_ABBREVIATIONS = re.compile(
    r"\b("
    r"г|гг|стр|рис|табл|илл|им|тыс|род|р|"
    r"сокр|чел|см|ср|др|напр|ок"
    r").",
    re.IGNORECASE
)


def replace_nonbreaking_spaces(text):
    for pattern, replacement in ABBREVIATION_SPACES:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = SIMPLE_ABBREVIATIONS.sub(lambda m: m.group(0), text)
    text = re.sub(r"([№§])[ \t]+(\d)", r"\1\u00A0\2", text)
    text = re.sub(r"(\d)[ \t]+(гг?\.)", r"\1\u00A0\2", text, flags=re.IGNORECASE)
    text = re.sub(r"(\d)[ \t]+(тыс\.)", r"\1\u00A0\2", text, flags=re.IGNORECASE)
    return text


def typography(text):
    for pattern, replacement in RULES:
        text = re.sub(pattern, replacement, text)
    text = fix_mathematics(text)
    text = fix_commas(text)
    text = replace_dashes(text)
    text = replace_quotes(text)
    text = fix_typos(text)
    text = replace_nonbreaking_spaces(text)
    text, abbreviation_blocks = protect_abbreviations(text)
    text = capitalise_sentences(text)
    text = restore_abbreviations(text, abbreviation_blocks)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([,.;!?])", r"\1", text)
    text = re.sub(r",(?=[А-ЯЁа-яёA-Za-z])", ", ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    return text.strip()


MATH_REPLACEMENTS = [
    (r"<>", "≠"), (r"!=", "≠"), (r"<=", "≤"), (r">=", "≥"),
    (r"\+\-", "±"), (r"-\+", "∓"), (r"~=", "≈"),
    (r"\\forall\b", "∀"), (r"\\exists\b", "∃"), (r"\\nexists\b", "∄"),
    (r"\\emptyset\b", "∅"), (r"\\in\b", "∈"), (r"\\notin\b", "∉"),
    (r"\\sqrt\b", "√"), (r"\\infty\b", "∞"), (r"\\cap\b", "∩"),
    (r"\\cup\b", "∪"), (r"\\subset\b", "⊂"), (r"\\supset\b", "⊃"),
    (r"\\le\b", "≤"), (r"\\ge\b", "≥"), (r"\\neq\b", "≠"),
    (r"\\equiv\b", "≡"), (r"\\approx\b", "≈"), (r"\\sim\b", "∼"),
    (r"\\partial\b", "∂"), (r"\\nabla\b", "∇"), (r"\\Delta\b", "∆"),
    (r"\\sum\b", "∑"), (r"\\prod\b", "∏"), (r"\\int\b", "∫"),
    (r"\\iint\b", "∬"), (r"\\iiint\b", "∭"), (r"\\oint\b", "∮"),
    (r"\\therefore\b", "∴"), (r"\\because\b", "∵"),
]


def fix_mathematics(text):
    for pattern, replacement in MATH_REPLACEMENTS:
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"(?<=\d)\s*[xх]\s*(?=\d)", " × ", text)
    text = re.sub(r"(?<=\d)\s*\+\s*(?=\d)", " + ", text)
    text = re.sub(r"(?<=\d)\s*\*\s*(?=\d)", " ∗ ", text)

    comparison_ops = r"≠=≤≥≡≈≃≅≠∼∽"
    text = re.sub(
        rf"(?<=[\wА-Яа-яЁё0-9)\]])\s*([{comparison_ops}])\s*(?=[\wА-Яа-яЁё0-9(\[])",
        r" \1 ", text
    )

    membership_ops = r"∈∉∊∋∌∍"
    text = re.sub(
        rf"(?<=[\wА-Яа-яЁё0-9)\]])\s*([{membership_ops}])\s*(?=[\wА-Яа-яЁё0-9(\[])",
        r" \1 ", text
    )

    logical_ops = r"∧∨"
    text = re.sub(
        rf"(?<=[\wА-Яа-яЁё0-9)\]])\s*([{logical_ops}])\s*(?=[\wА-Яа-яЁё0-9(\[])",
        r" \1 ", text
    )
    return text


async def handle_message(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    text = update.message.text
    if not text:
        return

    match = re.match(r"^undumb:\s*(.*)", text, flags=re.DOTALL | re.IGNORECASE)
    if not match:
        return

    original = match.group(1)
    if not original:
        return

    protected_text, blocks = protect(original)
    result = typography(protected_text)
    result = restore(result, blocks)

    prefix = "〘Исправленный текст〙\n\n"
    max_chunk_length = 4096 - len(prefix)

    for chunk in split_telegram_text(result, limit=max_chunk_length):
        await update.message.reply_text(prefix + chunk)


def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        logger.exception("Unhandled exception. Update=%r", update, exc_info=context.error)

    app.add_error_handler(error_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Typography bot started")
    app.run_polling()


if __name__ == "__main__":
    main()