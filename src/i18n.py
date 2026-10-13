"""Переклади Limber: рядки інтерфейсу, вправи, поради та форматування чисел (uk, en)."""
import ctypes

LANGUAGES = {"uk": "Українська", "en": "English"}
DEFAULT_LANGUAGE = "uk"

_current = DEFAULT_LANGUAGE


def set_language(code):
    global _current
    _current = code if code in LANGUAGES else "en"


def get_language():
    return _current


def system_language():
    """Мова інтерфейсу Windows: українська → uk, будь-яка інша → en."""
    try:
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return DEFAULT_LANGUAGE
    return "uk" if primary == 0x22 else "en"


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
        "mini": [
            ("Правило 20-20-20", "Знайдіть предмет щонайменше за 6 метрів і дивіться на нього 20 секунд."),
            ("Кліпання", "Часто покліпайте 10 секунд, потім заплющіть очі й розслабтеся."),
            ("Очі вгору-вниз", "Не повертаючи голови, повільно подивіться вгору, потім униз. Повторіть 5 разів."),
            ("Очі вліво-вправо", "Не повертаючи голови, повільно переведіть погляд уліво, потім управо. 5 разів."),
            ("Вісімка очима", "Повільно «намалюйте» очима велику вісімку: тричі в один бік і тричі в інший."),
            ("Ближче — далі", "Подивіться на палець перед носом, потім удалину за вікно. Повторіть 5 разів."),
            ("Пальмінг", "Розітріть долоні до тепла й накрийте ними заплющені очі. Посидьте в темряві."),
            ("Нахили голови", "Нахиліть голову до правого плеча, затримайтеся на 10 секунд. Потім до лівого."),
            ("Плечі", "Покрутіть плечима 10 разів назад, потім 10 разів уперед."),
            ("Кисті", "Стисніть кулаки, потім широко розчепірте пальці. Повторіть 10 разів."),
            ("Постава", "Сядьте рівно: стопи на підлозі, спина на спинці крісла, плечі опущені й розслаблені."),
            ("Дихання 4-4-6", "Вдих на 4 рахунки, затримка на 4, повільний видих на 6. Повторіть 3 рази."),
        ],
        "mini_active": [
            ("10 присідань", "Встаньте й зробіть 10 спокійних присідань. Спина рівна, п'яти на підлозі."),
            ("Підйоми на носки", "Встаньте й 20 разів підніміться на носки, повільно опускаючись."),
            ("Віджимання від столу", "Зробіть 10 віджимань від краю стійкого столу."),
            ("Потягніться", "Встаньте на носки, потягніться руками вгору й затримайтеся на 10 секунд."),
            ("Пройдіться", "Встаньте й пройдіться кімнатою — сидіння теж треба перебивати."),
        ],
        "long": [
            ("Розтяжка спини", ["Встаньте, зчепіть руки в замок над головою.", "Потягніться вгору на 10 секунд.",
                                "Нахиліться вліво, потім управо — по 10 секунд.", "Повторіть 3 рази."]),
            ("Шия та плечі", ["Повільно покрутіть головою по 5 разів у кожен бік.",
                              "Зведіть лопатки й потримайте 5 секунд — 10 разів.",
                              "Потягніть руку через груди іншою рукою — по 15 секунд."]),
            ("Ноги", ["Встаньте й зробіть 10 присідань.", "Нахиліться й потягніться до пальців ніг — 15 секунд.",
                      "Підніміться на носки 15 разів."]),
            ("Прогулянка", ["Встаньте з-за столу.", "Пройдіться кімнатою чи коридором.",
                            "Подивіться у вікно вдалину.", "Випийте склянку води."]),
            ("Віджимання від стіни", ["Встаньте на відстані витягнутих рук від стіни.", "Зробіть 10–15 віджимань.",
                                      "Покрутіть кистями й розімніть зап'ястя."]),
            ("Розкриття грудей", ["Станьте в дверному отворі, долоні на одвірках.",
                                  "Подайтеся вперед до легкого натягу в грудях — 20 секунд.",
                                  "Повторіть 3 рази, глибоко дихаючи."]),
            ("Повороти корпусу", ["Сядьте на край стільця, спина рівна.",
                                  "Поверніть корпус ліворуч і затримайтеся на 15 секунд.",
                                  "Те саме праворуч.", "Зробіть 3 підходи."]),
        ],
        "warmup": ("Розминка", "Крокуйте на місці, високо піднімаючи коліна, і робіть кола руками."),
        "cooldown": ("Заминка", "Повільно потягніться вгору, потім нахиліться до носків. Дихайте глибоко й спокійно."),
        "workout": {
            1: [
                ("Кола плечима", "Великі повільні кола плечима: половину часу вперед, половину — назад."),
                ("Нахили в боки", "Руки на поясі, повільно нахиляйтеся вліво й управо."),
                ("Повороти корпусу", "Стоячи, руки перед грудьми, плавно повертайте корпус уліво-вправо."),
                ("Підйоми на носки", "Тримаючись за стіл, піднімайтеся на носки й повільно опускайтеся."),
                ("Ходьба на місці", "Крокуйте на місці в спокійному темпі, розмахуючи руками."),
                ("Розкриття грудей", "Зчепіть руки за спиною, розправте плечі й потягніть руки назад і вниз."),
                ("Котик біля столу", "Руки на край столу, по черзі округлюйте й прогинайте спину."),
                ("Кола тазом", "Руки на поясі, повільні кола тазом в обидва боки."),
            ],
            2: [
                ("Присідання", "Ноги на ширині плечей, сідайте назад, ніби на стілець. Спина рівна."),
                ("Віджимання від столу", "Руки на край стійкого столу, тіло рівне, згинайте лікті."),
                ("Випади на місці", "Крок уперед, обидва коліна під кутом 90°. Чергуйте ноги."),
                ("Стільчик біля стіни", "Спиною до стіни, сповзіть до кута в колінах 90° і тримайте."),
                ("Планка на столі", "Передпліччя на стіл, тіло рівною лінією від голови до п'ят. Тримайте."),
                ("Махи ногою в бік", "Тримаючись за стіл, відводьте пряму ногу в бік. Половину часу — кожною."),
                ("Високі коліна", "Крокуйте на місці, піднімаючи коліна до рівня стегна."),
                ("Зворотні віджимання", "Руки на край стійкого стільця за спиною, згинайте лікті до 90°."),
            ],
            3: [
                ("Джампінг-джек", "Стрибок — ноги ширше, руки над головою; стрибок назад. У швидкому темпі."),
                ("Присідання зі стрибком", "Присід і вибуховий стрибок угору. Приземляйтеся м'яко, на зігнуті ноги."),
                ("Віджимання", "Від підлоги або з колін. Тіло рівне, опускайтеся грудьми до підлоги."),
                ("Біг на місці", "Швидко, коліна до рівня пояса, активно працюйте руками."),
                ("Альпініст", "Упор лежачи, по черзі швидко підтягуйте коліна до грудей."),
                ("Випади з чергуванням", "Глибокі випади вперед, по черзі кожною ногою."),
                ("Планка", "Упор на передпліччя, тіло рівне, живіт підтягнутий. Тримайте."),
                ("Берпі без стрибка", "Присід, руки на підлогу, ноги назад у планку, назад у присід і встати."),
                ("Присідання сумо", "Широко ноги, носки назовні, глибокий присід."),
            ],
        },
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
        "mini": [
            ("The 20-20-20 rule", "Find something at least 6 metres away and look at it for 20 seconds."),
            ("Blinking", "Blink rapidly for 10 seconds, then close your eyes and relax."),
            ("Eyes up and down", "Without moving your head, slowly look up, then down. Repeat 5 times."),
            ("Eyes left and right", "Without moving your head, slowly look left, then right. Repeat 5 times."),
            ("Figure eight", "Slowly trace a large figure eight with your eyes: three times each way."),
            ("Near and far", "Focus on a finger in front of your nose, then on something out the window. Repeat 5 times."),
            ("Palming", "Rub your palms until warm and cup them over your closed eyes. Rest in the dark."),
            ("Head tilts", "Tilt your head towards your right shoulder and hold for 10 seconds. Then the left."),
            ("Shoulders", "Roll your shoulders backwards 10 times, then forwards 10 times."),
            ("Hands", "Make tight fists, then spread your fingers wide. Repeat 10 times."),
            ("Posture", "Sit up straight: feet flat, back against the chair, shoulders down and relaxed."),
            ("4-4-6 breathing", "Breathe in for 4 counts, hold for 4, breathe out slowly for 6. Repeat 3 times."),
        ],
        "mini_active": [
            ("10 squats", "Stand up and do 10 easy squats. Keep your back straight and heels down."),
            ("Calf raises", "Stand up and rise onto your toes 20 times, lowering slowly."),
            ("Desk push-ups", "Do 10 push-ups against the edge of a sturdy desk."),
            ("Stretch up", "Stand on your toes, reach up high and hold for 10 seconds."),
            ("Take a walk", "Get up and walk around the room — long sitting needs breaking up too."),
        ],
        "long": [
            ("Back stretch", ["Stand up and interlace your fingers above your head.", "Reach up for 10 seconds.",
                              "Lean left, then right — 10 seconds each.", "Repeat 3 times."]),
            ("Neck and shoulders", ["Slowly roll your head 5 times in each direction.",
                                    "Squeeze your shoulder blades together for 5 seconds — 10 times.",
                                    "Pull one arm across your chest with the other — 15 seconds each."]),
            ("Legs", ["Stand up and do 10 squats.", "Bend forward and reach for your toes — 15 seconds.",
                      "Rise onto your toes 15 times."]),
            ("A short walk", ["Get up from your desk.", "Walk around the room or down the hallway.",
                              "Look out of the window into the distance.", "Drink a glass of water."]),
            ("Wall push-ups", ["Stand an arm's length from a wall.", "Do 10–15 push-ups.",
                               "Circle your hands and loosen your wrists."]),
            ("Chest opener", ["Stand in a doorway with your palms on the frame.",
                              "Lean forward until you feel a gentle stretch in your chest — 20 seconds.",
                              "Repeat 3 times, breathing deeply."]),
            ("Seated twists", ["Sit on the edge of your chair with a straight back.",
                               "Twist your torso to the left and hold for 15 seconds.",
                               "Same to the right.", "Do 3 rounds."]),
        ],
        "warmup": ("Warm-up", "March on the spot with high knees and make circles with your arms."),
        "cooldown": ("Cool-down", "Slowly reach up, then bend down towards your toes. Breathe deeply and calmly."),
        "workout": {
            1: [
                ("Shoulder circles", "Big slow shoulder circles: half the time forwards, half backwards."),
                ("Side bends", "Hands on hips, slowly bend to the left and to the right."),
                ("Torso twists", "Standing, arms in front of your chest, gently twist left and right."),
                ("Calf raises", "Holding the desk, rise onto your toes and lower slowly."),
                ("March on the spot", "March on the spot at an easy pace, swinging your arms."),
                ("Chest opener", "Clasp your hands behind your back, open your shoulders and pull your arms back and down."),
                ("Desk cat-cow", "Hands on the desk edge, alternate rounding and arching your back."),
                ("Hip circles", "Hands on hips, slow hip circles in both directions."),
            ],
            2: [
                ("Squats", "Feet shoulder-width apart, sit back as if onto a chair. Keep your back straight."),
                ("Desk push-ups", "Hands on the edge of a sturdy desk, body straight, bend your elbows."),
                ("Lunges", "Step forward until both knees are at 90°. Alternate legs."),
                ("Wall sit", "Back against a wall, slide down until your knees are at 90° and hold."),
                ("Desk plank", "Forearms on the desk, body in a straight line from head to heels. Hold."),
                ("Side leg raises", "Holding the desk, lift a straight leg out to the side. Switch halfway."),
                ("High knees", "March on the spot, lifting your knees to hip height."),
                ("Chair dips", "Hands on the edge of a sturdy chair behind you, bend your elbows to 90°."),
            ],
            3: [
                ("Jumping jacks", "Jump feet apart with arms overhead, then jump back. Keep a quick pace."),
                ("Squat jumps", "Squat and jump up explosively. Land softly on bent knees."),
                ("Push-ups", "On the floor or on your knees. Keep your body straight, chest towards the floor."),
                ("Running on the spot", "Fast, knees up to waist height, pump your arms."),
                ("Mountain climbers", "In a high plank, quickly drive your knees towards your chest in turn."),
                ("Alternating lunges", "Deep forward lunges, alternating legs."),
                ("Plank", "On your forearms, body straight, core tight. Hold."),
                ("Burpees without the jump", "Squat, hands to the floor, step back into a plank, back to a squat and stand up."),
                ("Sumo squats", "Wide stance, toes out, deep squat."),
            ],
        },
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
