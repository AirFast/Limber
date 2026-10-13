"""Переклади Limber: рядки інтерфейсу, поради про воду та форматування чисел (uk, en)."""

LANGUAGES = {"uk": "Українська", "en": "English"}
DEFAULT_LANGUAGE = "uk"

_current = DEFAULT_LANGUAGE


def set_language(code):
    global _current
    _current = code if code in LANGUAGES else "en"


def get_language():
    return _current


def t(key, **values):
    text = STRINGS[_current].get(key, STRINGS[DEFAULT_LANGUAGE][key])
    return text.format(**values) if values else text


def content(name):
    return CONTENT[_current][name]


def _plural_uk(n, one, few, many):
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def fmt_minutes(v):
    h, m = divmod(v, 60)
    if not h:
        return t("u_min", n=m)
    return t("u_h_min", h=h, m=m) if m else t("u_h", h=h)


def fmt_seconds(v):
    m, s = divmod(v, 60)
    if not m:
        return t("u_sec", n=s)
    return t("u_min_sec", m=m, s=s) if s else t("u_min", n=m)


def fmt_times(v):
    if v == 0:
        return t("times_none")
    if _current == "uk":
        return f"{v} {_plural_uk(v, 'раз', 'рази', 'разів')}"
    return f"{v} {'time' if v == 1 else 'times'}"


def fmt_warn(v):
    return t("off") if v == 0 else fmt_seconds(v)


def fmt_glasses(v):
    liters = f"{v * 0.25:g}"
    if _current == "uk":
        return f"{v} {_plural_uk(v, 'склянка', 'склянки', 'склянок')} (≈{liters.replace('.', ',')} л)"
    return f"{v} {'glass' if v == 1 else 'glasses'} (≈{liters} L)"


def fmt_intensity(v):
    return t(f"intensity_{v}")


STRINGS = {
    "uk": {
        "tagline": "час розім'ятися",
        "language": "Мова",
        # трей
        "open": "Відкрити",
        "break_now": "Перерва зараз",
        "reset": "Скинути таймер",
        "pause": "Пауза",
        "pause_30": "30 хвилин",
        "pause_60": "1 година",
        "pause_120": "2 години",
        "pause_morning": "До ранку",
        "resume": "Продовжити",
        "quit": "Вихід",
        "tip_paused": "{app}: пауза до {time}",
        "tip_break": "{app}: перерва",
        "tip_next_mini": "{app}: міні-перерва через {time}",
        "tip_next_long": "{app}: довга перерва через {time}",
        "tip_water": "Вода через {time}",
        "warn_mini": "Міні-перерва через {sec} с",
        "warn_long": "Довга перерва через {sec} с",
        # екран перерви
        "demo_banner": "ДЕМО-ПЕРЕГЛЯД  ·  Esc — закрити",
        "break_other_screen": "Перерва",
        "postpone_btn": "Відкласти на {min} хв (ще {left})",
        "next_exercise": "Наступна вправа →",
        "skip": "Пропустити",
        "body_note": "Слухайте своє тіло: якщо вправа викликає біль — пропустіть її.",
        "group_any": "Будь-які",
        "group_eyes": "Очі",
        "group_neck": "Шия й плечі",
        "group_back": "Спина",
        "group_arms": "Руки",
        "group_legs": "Ноги",
        "group_body": "Усе тіло",
        "step_info": "Крок {n} з {total}  ·  усього залишилось {time}",
        "up_next": "  ·  далі: {title}",
        "phase_mini": "МІНІ-ПЕРЕРВА",
        "phase_long": "ДОВГА ПЕРЕРВА",
        "phase_warmup": "РОЗМИНКА",
        "phase_work": "ВПРАВА {n} / {count}",
        "phase_rest": "ВІДПОЧИНОК",
        "phase_cooldown": "ЗАМИНКА",
        "rest_title": "Відпочинок",
        "rest_next": "Далі: {title}",
        # вода
        "water_title": "Час випити води",
        "x_of_y": "{a} з {b}",
        "demo_tag": "демо",
        "water_goal_done": "Денну мету виконано! Пити можна й далі — особливо в спеку чи після руху.",
        "later": "Пізніше",
        "drank": "Випив",
        # головне вікно
        "tab_status": "Стан",
        "tab_stats": "Статистика",
        "tab_settings": "Налаштування",
        "saved": "Збережено ",
        "pause_30_btn": "Пауза 30 хв",
        "card_water": "Вода",
        "card_today": "Сьогодні",
        "m_mini": "міні-перерв",
        "m_long": "довгих перерв",
        "m_skipped": "пропущено",
        "m_water": "склянок води",
        "ring_paused": "пауза до {time}",
        "ring_break": "зараз перерва",
        "ring_mini": "до міні-перерви",
        "ring_long": "до довгої перерви",
        "water_off": "нагадування вимкнено",
        "water_now": "Час пити!",
        "water_today": "сьогодні {n} з {goal}",
        "water_next": "до наступної склянки  ·  {progress}",
        # статистика
        "sum_done": "перерв за 7 днів",
        "card_last7": "Останні 7 днів",
        "lg_mini": "міні",
        "lg_long": "довгі",
        "lg_skipped": "пропущені",
        "lg_water": "вода",
        "today": "сьогодні",
        "weekdays": "пн вт ср чт пт сб нд",
        # налаштування
        "card_breaks": "Перерви",
        "card_long": "Довгі перерви",
        "card_other": "Інше",
        "card_postpone": "Відкладання",
        "card_preview": "Перегляд",
        "workout_toggle": "Інтервальне тренування",
        "sound_toggle": "Звук на початку й наприкінці",
        "autostart_toggle": "Запускати разом з Windows",
        "autostart_toggle_mac": "Запускати під час входу в систему",
        "water_toggle": "Нагадувати пити воду",
        "preview_hint": "Спробуйте з поточними налаштуваннями:",
        "preview_mini": "Міні",
        "preview_long": "Довга",
        "preview_water": "Вода",
        "s_mini_interval_min": "Перерва кожні",
        "s_mini_duration_sec": "Тривалість міні-перерви",
        "s_long_every": "Кожна N-та перерва — довга",
        "s_long_duration_min": "Тривалість довгої перерви",
        "s_postpone_min": "Відкласти на",
        "s_postpone_limit": "Можна відкласти",
        "s_warn_before_sec": "Попередження перед перервою",
        "s_water_interval_min": "Нагадувати кожні",
        "s_water_goal": "Мета на день",
        "s_intensity": "Інтенсивність вправ",
        "intensity_1": "легко",
        "intensity_2": "середньо",
        "intensity_3": "енергійно",
        "autostart_error": "Не вдалося змінити автозапуск: {e}",
        # одиниці
        "u_min": "{n} хв",
        "u_h": "{h} год",
        "u_h_min": "{h} год {m} хв",
        "u_sec": "{n} с",
        "u_min_sec": "{m} хв {s} с",
        "times_none": "не можна",
        "off": "вимкнено",
    },
    "en": {
        "tagline": "time to limber up",
        "language": "Language",
        "open": "Open",
        "break_now": "Break now",
        "reset": "Reset timer",
        "pause": "Pause",
        "pause_30": "30 minutes",
        "pause_60": "1 hour",
        "pause_120": "2 hours",
        "pause_morning": "Until morning",
        "resume": "Resume",
        "quit": "Quit",
        "tip_paused": "{app}: paused until {time}",
        "tip_break": "{app}: on a break",
        "tip_next_mini": "{app}: mini break in {time}",
        "tip_next_long": "{app}: long break in {time}",
        "tip_water": "Water in {time}",
        "warn_mini": "Mini break in {sec} s",
        "warn_long": "Long break in {sec} s",
        "demo_banner": "DEMO PREVIEW  ·  Esc to close",
        "break_other_screen": "Break",
        "postpone_btn": "Postpone {min} min ({left} left)",
        "next_exercise": "Next exercise →",
        "skip": "Skip",
        "body_note": "Listen to your body: if an exercise hurts, skip it.",
        "group_any": "Any",
        "group_eyes": "Eyes",
        "group_neck": "Neck & shoulders",
        "group_back": "Back",
        "group_arms": "Arms",
        "group_legs": "Legs",
        "group_body": "Full body",
        "step_info": "Step {n} of {total}  ·  {time} left in total",
        "up_next": "  ·  next: {title}",
        "phase_mini": "MINI BREAK",
        "phase_long": "LONG BREAK",
        "phase_warmup": "WARM-UP",
        "phase_work": "EXERCISE {n} / {count}",
        "phase_rest": "REST",
        "phase_cooldown": "COOL-DOWN",
        "rest_title": "Rest",
        "rest_next": "Next: {title}",
        "water_title": "Time for some water",
        "x_of_y": "{a} of {b}",
        "demo_tag": "demo",
        "water_goal_done": "Daily goal reached! Feel free to keep drinking — especially in the heat or after exercise.",
        "later": "Later",
        "drank": "Done",
        "tab_status": "Status",
        "tab_stats": "Statistics",
        "tab_settings": "Settings",
        "saved": "Saved ",
        "pause_30_btn": "Pause 30 min",
        "card_water": "Water",
        "card_today": "Today",
        "m_mini": "mini breaks",
        "m_long": "long breaks",
        "m_skipped": "skipped",
        "m_water": "glasses of water",
        "ring_paused": "paused until {time}",
        "ring_break": "break in progress",
        "ring_mini": "until mini break",
        "ring_long": "until long break",
        "water_off": "reminders off",
        "water_now": "Time to drink!",
        "water_today": "today {n} of {goal}",
        "water_next": "until next glass  ·  {progress}",
        "sum_done": "breaks in 7 days",
        "card_last7": "Last 7 days",
        "lg_mini": "mini",
        "lg_long": "long",
        "lg_skipped": "skipped",
        "lg_water": "water",
        "today": "today",
        "weekdays": "Mon Tue Wed Thu Fri Sat Sun",
        "card_breaks": "Breaks",
        "card_long": "Long breaks",
        "card_other": "Other",
        "card_postpone": "Postponing",
        "card_preview": "Preview",
        "workout_toggle": "Interval workout",
        "sound_toggle": "Sound at start and end",
        "autostart_toggle": "Start with Windows",
        "autostart_toggle_mac": "Open at login",
        "water_toggle": "Remind me to drink water",
        "preview_hint": "Try it with the current settings:",
        "preview_mini": "Mini",
        "preview_long": "Long",
        "preview_water": "Water",
        "s_mini_interval_min": "Break every",
        "s_mini_duration_sec": "Mini break length",
        "s_long_every": "Every Nth break is long",
        "s_long_duration_min": "Long break length",
        "s_postpone_min": "Postpone for",
        "s_postpone_limit": "Postpones allowed",
        "s_warn_before_sec": "Warning before a break",
        "s_water_interval_min": "Remind every",
        "s_water_goal": "Daily goal",
        "s_intensity": "Exercise intensity",
        "intensity_1": "light",
        "intensity_2": "moderate",
        "intensity_3": "vigorous",
        "autostart_error": "Could not change autostart: {e}",
        "u_min": "{n} min",
        "u_h": "{h} h",
        "u_h_min": "{h} h {m} min",
        "u_sec": "{n} s",
        "u_min_sec": "{m} min {s} s",
        "times_none": "not allowed",
        "off": "off",
    },
}

CONTENT = {
    "uk": {
        "warmup": ("Розминка", "Крокуйте на місці, високо піднімаючи коліна, і робіть кола руками."),
        "cooldown": ("Заминка", "Повільно потягніться вгору, потім нахиліться до носків. Дихайте глибоко й спокійно."),
        "water_tips": [
            "Пийте невеликими ковтками — так вода засвоюється краще, ніж пів літра за раз.",
            "Тримайте пляшку чи графин на столі: що ближче вода, то частіше її п'єш.",
            "Колір сечі — найпростіший орієнтир: світло-солом'яний означає, що води досить.",
            "Здається, що хочеться перекусити? Іноді це насправді спрага — спершу випийте води.",
            "Кава й солодкі напої воду не замінюють. Краще — звичайна вода або трав'яний чай.",
            "Склянка води за пів години до їжі допомагає травленню і не дає переїсти.",
            "Втома й головний біль наприкінці дня часто бувають від нестачі води.",
            "Сходіть по воду пішки — це ще й маленька розминка для ніг.",
            "Якщо проста вода набридла, додайте скибочку лимона, огірка чи листок м'яти.",
            "У спеку, під час спорту чи хвороби води потрібно більше, ніж зазвичай.",
            "Почніть ранок зі склянки води — після сну організму її бракує.",
            "Сухість в очах і губах — теж сигнал, що час попити.",
        ],
    },
    "en": {
        "warmup": ("Warm-up", "March on the spot with high knees and make circles with your arms."),
        "cooldown": ("Cool-down", "Slowly reach up, then bend down towards your toes. Breathe deeply and calmly."),
        "water_tips": [
            "Drink in small sips — your body absorbs water better than half a litre at once.",
            "Keep a bottle or jug on your desk: the closer the water, the more often you drink.",
            "Urine colour is the simplest guide: pale straw means you're drinking enough.",
            "Feeling peckish? Sometimes it's really thirst — try a glass of water first.",
            "Coffee and sugary drinks don't replace water. Plain water or herbal tea is better.",
            "A glass of water half an hour before a meal helps digestion and keeps you from overeating.",
            "Tiredness and headaches late in the day are often caused by not drinking enough.",
            "Walk to get your water — it doubles as a little leg workout.",
            "Bored of plain water? Add a slice of lemon, cucumber or a mint leaf.",
            "You need more water than usual in the heat, during exercise or when ill.",
            "Start your morning with a glass of water — your body needs it after sleep.",
            "Dry eyes and lips are also a sign that it's time to drink.",
        ],
    },
}
