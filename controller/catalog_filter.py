# category_words.py
import re

SLUG_TO_WORDS = {
    # Женская одежда - Верхний одяг
    "verhnyaya-odezhda/palto": [
        "пальто",          # RU
        "пальто",          # UA
        "coat",            # EN
        "пальтишко",       # RU, уменьш.
        "кейп"             # RU, разг.
    ],
    "verhnyaya-odezhda/plashi": [
        "плащ",            # RU
        "плащ",            # UA
        "raincoat",        # EN
        "тренч",           # RU, модное
        "макинтош"         # RU, устар.
    ],
    "verhnyaya-odezhda/kurtki": [
        "куртка",          # RU
        "куртка",          # UA
        "jacket",          # EN
        "бомбер",          # RU, модное
        "косуха"           # RU, разг.
    ],
    "verhnyaya-odezhda/shuby": [
        "шуба",            # RU
        "шуба",            # UA
        "fur coat",        # EN
        "шубка",           # RU, уменьш.
        "манто"            # RU, разг.
    ],
    "verhnyaya-odezhda/zhiletki": [
        "жилет",           # RU
        "жилетка",         # UA
        "vest",            # EN
        "безрукавка",      # RU, разг.
        "жилеточка"        # RU, уменьш.
    ],
    "verhnyaya-odezhda/pidzhaki-i-zhakety": [
        "пиджак",          # RU
        "піджак",          # UA
        "blazer",          # EN
        "жакет",           # RU, син.
        "фрак"             # RU, разг.
    ],
    "verhnyaya-odezhda/puhoviki": [
        "пуховик",         # RU
        "пуховик",         # UA
        "puffer jacket",   # EN
        "зимник",          # RU, разг.
        "пуховичок"        # RU, уменьш.
    ],
    "verhnyaya-odezhda/parki": [
        "парка",           # RU
        "парка",           # UA
        "parka",           # EN
        "аляска",          # RU, разг.
        "куртка-парка"     # RU
    ],
    "verhnyaya-odezhda/dublenki": [
        "дубленка",        # RU
        "дублянка",        # UA
        "shearling coat",  # EN
        "полушубок",       # RU
        "дубленочка"       # RU, уменьш.
    ],
    "verhnyaya-odezhda/dozhdeviki": [
        "дождевик",        # RU
        "дощовик",         # UA
        "rain jacket",     # EN
        "дождик",          # RU, разг.
        "непромокайка"     # RU, разг.
    ],
    "verhnyaya-odezhda/vetrovki": [
        "ветровка",        # RU
        "вітровка",        # UA
        "windbreaker",     # EN
        "штормовка",       # RU
        "ветровичок"       # RU, уменьш.
    ],

    # Женская одежда - Платья
    "platya/mini": [
        "мини",            # RU
        "міні",            # UA
        "mini dress",      # EN
        "короткое",        # RU, разг.
        "платье-мини",
        "cпідниця"     # RU
    ],
    "platya/midi": [
        "миди",            # RU
        "міді",            # UA
        "midi dress",      # EN
        "платье-миди",     # RU
        "среднее"          # RU, разг.
    ],
    "platya/maksi": [
        "макси",           # RU
        "максі",           # UA
        "maxi dress",      # EN
        "длинное",         # RU, разг.
        "в пол", 
        "сукня"          # RU, разг.
    ],
    "platya/vechernie": [
        "вечернее",        # RU
        "вечірнє",         # UA
        "evening dress",   # EN
        "бальное",         # RU
        "выходное"         # RU, разг.
    ],
    "platya/svadebnye": [
        "свадебное",       # RU
        "весільне",        # UA
        "wedding dress",   # EN
        "подвенечное",     # RU, устар.
        "фата"             # RU, ассоц.
    ],
    "platya/sarafany": [
        "сарафан",         # RU
        "сарафан",         # UA
        "sundress",        # EN
        "летник",          # RU, разг.
        "сарафанчик"       # RU, уменьш.
    ],
    "platya/tuniki": [
        "туника",          # RU
        "туніка",          # UA
        "tunic",           # EN
        "длинный топ",     # RU
        "туничка"          # RU, уменьш.
    ],

    # Женская одежда - Юбки
    "yubki/mini": [
        "мини",            # RU
        "міні",            # UA
        "mini skirt",      # EN
        "короткая",        # RU
        "юбка-мини"        # RU
    ],
    "yubki/midi": [
        "миди",            # RU
        "міді",            # UA
        "midi skirt",      # EN
        "юбка-миди",       # RU
        "средняя"          # RU, разг.
    ],
    "yubki/maksi": [
        "макси",           # RU
        "максі",           # UA
        "maxi skirt",      # EN
        "длинная",         # RU
        "в пол"            # RU, разг.
    ],

    # Женская одежда - Майки и футболки
    "mayki-i-futbolki/futbolki": [
        "футболка",        # RU
        "футболка",        # UA
        "t-shirt",         # EN
        "майка",           # RU, син.
        "футболочка"       # RU, уменьш.
    ],
    "mayki-i-futbolki/mayki": [
        "майка",           # RU
        "майка",           # UA
        "tank top",        # EN
        "безрукавка",      # RU
        "маечка"           # RU, уменьш.
    ],
    "mayki-i-futbolki/polo": [
        "поло",            # RU
        "поло",            # UA
        "polo shirt",      # EN
        "тенниска",        # RU, разг.
        "рубашка-поло"     # RU
    ],
    "mayki-i-futbolki/topy": [
        "топ",             # RU
        "топ",             # UA
        "top",             # EN
        "топик",           # RU
        "кроп-топ"         # RU, модное
    ],

    # Женская одежда - Сорочки и блузы
    "rubashki-i-bluzy/rubashki": [
        "рубашка",         # RU
        "сорочка",         # UA
        "shirt",           # EN
        "рубашечка",       # RU
        "ковбойка"         # RU, разг.
    ],
    "rubashki-i-bluzy/bluzy": [
        "блуза",           # RU
        "блуза",           # UA
        "blouse",          # EN
        "блузка",          # RU, уменьш.
        "кофточка"         # RU, разг.
    ],
    "rubashki-i-bluzy/vyshivanki": [
        "вышиванка",       # RU
        "вишиванка",       # UA
        "embroidered shirt", # EN
        "вышитая",         # RU
        "этнорубашка"      # RU
    ],

    # Женская одежда - Кофты
    "kofty/dzhempery": [
        "джемпер",         # RU
        "джемпер",         # UA
        "jumper",          # EN
        "пуловер",         # RU, син.
        "джемперок",
        "баска"       # RU, уменьш.
    ],
    "kofty/svitery": [
        "свитер",          # RU
        "светр",           # UA
        "sweater",         # EN
        "свитерок",        # RU
        "вязанка"          # RU, разг.
    ],
    "kofty/kardigany": [
        "кардиган",        # RU
        "кардиган",        # UA
        "cardigan",        # EN
        "кофта",           # RU, син.
        "кардиганчик"      # RU
    ],
    "kofty/vodolazki": [
        "водолазка",       # RU
        "водолазка",       # UA
        "turtleneck",      # EN
        "гольф",           # RU, син.
        "бадлон"           # RU, разг.
    ],
    "kofty/svitshoty": [
        "свитшот",         # RU
        "світшот",         # UA
        "sweatshirt",      # EN
        "толстовка",       # RU, син.
        "свит"             # RU, сленг
    ],
    "kofty/hudi": [
        "худи",            # RU
        "худі",            # UA
        "hoodie",          # EN
        "толстовка",       # RU
        "худик"            # RU, сленг
    ],
    "kofty/pulovery": [
        "пуловер",         # RU
        "пуловер",         # UA
        "pullover",        # EN
        "джемпер",         # RU, син.
        "пуловерок"        # RU
    ],
    "kofty/tolstovky": [
        "толстовка",       # RU
        "толстовка",       # UA
        "sweatshirt",      # EN
        "олимпийка",       # RU
        "толстик"          # RU, сленг
    ],
    "kofty/reglan": [
        "реглан",          # RU
        "реглан",          # UA
        "raglan",          # EN
        "рукав-реглан",    # RU
        "регланчик"        # RU
    ],
    "kofty/longslivy": [
        "лонгслив",        # RU
        "лонгслів",        # UA
        "longsleeve",      # EN
        "футболка",        # RU
        "лонг"             # RU, сленг
    ],

    # Женская одежда - Спідня білизна
    "nizhnee-bele-i-kupalniki/lifchiki": [
        "бюстгальтер",     # RU
        "бюстгальтер",     # UA
        "bra",             # EN
        "лифчик",          # RU, разг.
        "бюстик"           # RU, уменьш.
    ],
    "nizhnee-bele-i-kupalniki/trusiki": [
        "трусы",           # RU
        "трусики",         # UA
        "panties",         # EN
        "стринги",         # RU
        "шортики"          # RU
    ],
    "dlya-beremennyh/bele/komplekty": [
        "комплект",        # RU
        "комплект",        # UA
        "lingerie set",    # EN
        "бельевой",        # RU
        "сет"              # RU, сленг
    ],
    "nizhnee-bele-i-kupalniki/komplekty": [
        "купальник",       # RU
        "купальник",       # UA
        "swimsuit",        # EN
        "бикини",          # RU
        "слитный"          # RU
    ],
    "nizhnee-bele-i-kupalniki/noski": [
        "носки",           # RU
        "шкарпетки",       # UA
        "socks",           # EN
        "гольфы",          # RU
        "носочки"          # RU
    ],
    "nizhnee-bele-i-kupalniki/bodi": [
        "боди",            # RU
        "боді",            # UA
        "bodysuit",        # EN
        "комбидресс",      # RU
        "бодик"            # RU
    ],
    "nizhnee-bele-i-kupalniki/kolgotki": [
        "колготки",        # RU
        "колготи",         # UA
        "tights",          # EN
        "чулки",           # RU
        "капронки"         #
        "лоcіни"           # RU, разг.
    ],

    # Женская одежда - Спортивный одяг
    "sport-otdyh/sportivnyye-kostyumy": [
        "костюм",          # RU
        "костюм",
        "костюмчик",          # UA
        "tracksuit",       # EN
        "спортивка",       # RU, разг.
        "треники"          # RU, разг.
    ],
    "sport-otdyh/sportivnyye-shtany": [
        "штаны",           # RU
        "штани",           # UA
        "sweatpants",      # EN
        "треники",         # RU
        "лосины"           # RU
    ],
    "sport-otdyh/losiny": [
        "лосины",          # RU
        "лосини",          # UA
        "leggings",        # EN
        "леггинсы",        # RU
        "стретч"           # RU
    ],
    "sport-otdyh/shorty": [
        "шорты",           # RU
        "шорти",           # UA
        "shorts",          # EN
        "бермуды",         # RU
        "шортики"          # RU
    ],

    # Женская одежда - Костюмы
    "zhenskie-kostyumy/kostyumy-s-platem": [
        "suit",            # EN
        "двойка",          # RU
        "платье-костюм"    # RU
    ],
    "zhenskie-kostyumy/bryuchnye-kostyumy": [
        "брючный",         # RU
        "брючний",         # UA
        "pantsuit",        # EN
        "двойка",          # RU
        "костюм-двойка"    # RU
    ],

    # Женская одежда - Комбинезоны
    "zhenskie-kombinezony/dzhinsovye-kombinezony": [
        "комбинезон",      # RU
        "комбінезон",      # UA
        "jumpsuit",        # EN
        "джинсовый",       # RU
        "комбез"           # RU, сленг
    ],

    # Женская одежда - Домашний одяг
    "odezhda-dlya-doma-i-sna/pizhamy": [
        "пижама",          # RU
        "піжама",          # UA
        "pajamas",         # EN
        "спальный",        # RU
        "пижамка"          # RU
    ],
    "odezhda-dlya-doma-i-sna/halaty": [
        "халат",           # RU
        "халат",           # UA
        "robe",            # EN
        "кимоно",          # RU
        "халатик"          # RU
    ],

    # Женская одежда - Для вагітних
    "dlya-beremennyh/verhnyaya-odezhda": [
        "для беременных",  # RU
        "для вагітних",    # UA
        "maternity",       # EN
        "беременность",    # RU
        "для будущих"      # RU
    ],
    
    # Женская одежда - Штани та шорти
    "shtany/bryuki": [
        "брюки",           # RU
        "брюки",           # UA
        "trousers",        # EN
        "штаны",           # RU
        "слаксы"           # RU
    ],

    "shtany/dzhinsy": [
        "джинсы",          # RU
        "джинси",          # UA
        "jeans",           # EN
        "джинсовка",       # RU
        "стрейч"           # RU
    ],

    "shtany/losiny-i-legginsy": [
        "лосины",          # RU
        "лосини",          # UA
        "leggings",        # EN
        "леггинсы",        # RU
        "стретч"           # RU
    ],

}

def find_slug_by_word(name: str) -> str | None:
    # Очистка текста
    text = name.strip(" \t-–—|:;")
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(
        r"«><\s*[-–—:]?\s*\d{2,6}\s*(?:грн|uah|₴)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text_lower = text.lower()

    for slug, words in SLUG_TO_WORDS.items():
        for word in words:
            if word.lower() in re.findall(r"\w+", text_lower):  # ищем вхождение слова
                return slug
    return None

def find_word(name: str) -> str | None:
    # Очистка текста
    text = name.strip(" \t-–—|:;")
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(
        r"«><\s*[-–—:]?\s*\d{2,6}\s*(?:грн|uah|₴)\b.*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text_lower = text.lower()

    for slug, words in SLUG_TO_WORDS.items():
        for word in words:
            if word.lower() in text_lower:  # ищем вхождение слова
                return word
    return None