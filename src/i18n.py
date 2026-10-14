"""Переклади Rhythmos: рядки інтерфейсу, поради про воду та форматування чисел (uk, en)."""

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


def fmt_clock(v):
    """Хвилини від півночі → «08:00»."""
    return f"{v // 60:02d}:{v % 60:02d}"


def fmt_days(v):
    if _current == "uk":
        return f"{v} {_plural_uk(v, 'день', 'дні', 'днів')}"
    return f"{v} {'day' if v == 1 else 'days'}"


def fmt_warn(v):
    return t("off") if v == 0 else fmt_seconds(v)


GLASS_LITERS = 0.25  # стандартна склянка — 250 мл


def fmt_volume(glasses):
    """Приблизний об'єм води: 5 склянок → «≈1,25 л» / «≈1.25 L»."""
    liters = f"{glasses * GLASS_LITERS:g}"
    if _current == "uk":
        return f"≈{liters.replace('.', ',')} л"
    return f"≈{liters} L"


def fmt_glasses(v):
    if _current == "uk":
        return f"{v} {_plural_uk(v, 'склянка', 'склянки', 'склянок')} ({fmt_volume(v)})"
    return f"{v} {'glass' if v == 1 else 'glasses'} ({fmt_volume(v)})"


def fmt_intensity(v):
    return t(f"intensity_{v}")


STRINGS = {
    "uk": {
        "tagline": "ритм здорового дня",
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
        "warn_title_mini": "Скоро міні-перерва",
        "warn_title_long": "Скоро довга перерва",
        "warn_title_workout": "Скоро довга перерва — тренування",
        "warn_countdown": "Почнеться через {time}",
        "ok": "Ок",
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
        "drank_female": "Випила",
        "drank_male": "Випив",
        "drank_custom": "Готово",  # стать не вказано — нейтрально
        # головне вікно
        "tab_status": "Стан",
        "tab_stats": "Статистика",
        "tab_settings": "Налаштування",
        "saved": "Збережено ",
        "pause_btn": "Пауза {time}",
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
        "water_today": "сьогодні {n} з {goal} · {volume}",
        "water_next": "до наступної склянки  ·  {progress}",
        # статистика
        "m_breaks": "перерв зроблено",
        "m_postponed": "відкладено",
        "stats_today": "Сьогодні, {date}",
        "stats_day": "{weekday}, {date}",
        "range_total": "За {n} днів: перерв {breaks} · пропущено {skipped} · виконано {rate} · "
                       "склянок води {water} ({volume}, у середньому {avg} на день)",
        "range_more": "За комп'ютером {work} · рух {active} · прийомів їжі {meals} · норма води поспіль: {streak}",
        "best_day": " · найкращий день {day}: перерв {n}",
        "card_last_n": "Останні {n} днів",
        "range_days": "{n} днів",
        "m_work": "год роботи",
        "m_active": "хв руху",
        "m_meals": "прийомів їжі",
        "done_rate": "виконано {pct}%",
        "postponed_n": "відкладено {n}",
        "day_end_at_tip": "день завершено о {time}",
        "tip_work": "За комп'ютером",
        "tip_active": "Рух",
        "tip_meals": "Їжа",
        "tip_day_end": "День завершено",
        "tip_mini": "Міні-перерви",
        "tip_long": "Довгі перерви",
        "tip_skipped": "Пропущено",
        "tip_postponed": "Відкладено",
        "tip_day_water": "Вода",
        "lg_mini": "міні",
        "lg_long": "довгі",
        "lg_skipped": "пропущені",
        "lg_water": "вода (заповнений — норму виконано)",
        "today": "сьогодні",
        "weekdays": "пн вт ср чт пт сб нд",
        # налаштування
        "card_breaks": "Перерви",
        "card_long": "Довгі перерви",
        "card_other": "Інше",
        "card_postpone": "Відкладання й пауза",
        "s_pause_min": "Тривалість паузи",
        "card_preview": "Перегляд",
        "workout_toggle": "Інтервальне тренування",
        "sound_toggle": "Звук на початку й наприкінці",
        "autostart_toggle": "Запускати разом з Windows",
        "autostart_toggle_mac": "Запускати під час входу в систему",
        "updates_toggle": "Перевіряти оновлення",
        "card_sound": "Звук",
        "sound_name_label": "Звук сповіщення",
        "snd_notification": "Сповіщення",
        "snd_reminder": "Нагадування",
        "snd_message": "Повідомлення",
        "snd_mail": "Пошта",
        "snd_chime": "Дзвіночок",
        "snd_default": "Стандартний",
        "snd_ding": "Дзінь",
        "snd_nudge": "Поштовх",
        "snd_balloon": "Підказка",
        "snd_classic": "Класичне сповіщення",
        "snd_exclamation": "Увага",
        "snd_device": "Пристрій",
        "snd_unlock": "Розблокування",
        "snd_print": "Друк завершено",
        "snd_logon": "Вхід у систему",
        "snd_chimes": "Куранти",
        "snd_chord": "Акорд",
        "snd_tada": "Та-да",
        "group_buttons_toggle": "Кнопки груп на перерві",
        "update_menu": "Оновити до {version}",
        "update_banner": "Нова версія {version} — оновити",
        "update_toast_title": "Доступна нова версія {version}",
        "update_toast_text": "Rhythmos завантажить і встановить її сам, а потім перезапуститься. Налаштування збережуться.",
        "download": "Відкрити сторінку",
        "update_now": "Оновити",
        "updating_title": "Оновлення до {version}",
        "updating_progress": "Завантаження… {percent}%",
        "updating_install": "Встановлення… Rhythmos перезапуститься за мить.",
        "update_failed_title": "Не вдалося оновитися автоматично",
        "update_failed_text": "Завантажте інсталятор зі сторінки релізу й встановіть поверх — налаштування збережуться.",
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
        "water_profile": "Норма",
        "water_profile_female": "Жінка",
        "water_profile_male": "Чоловік",
        "water_profile_custom": "Вручну",
        "water_hint_auto": "За рекомендацією EFSA — {volume} напоїв на день (ще близько 20% води дає їжа). "
                           "Нагадування кожні {interval} — щоб устигнути за 8 годин за комп'ютером.",
        "water_hint_custom": "Орієнтир EFSA: жінкам {female}, чоловікам {male} напоїв на день. "
                             "Щоб випити {goal} за 8 годин, нагадуйте щонайменше кожні {interval}.",
        "s_intensity": "Інтенсивність вправ",
        "intensity_1": "легко",
        "intensity_2": "середньо",
        "intensity_3": "енергійно",
        "autostart_error": "Не вдалося змінити автозапуск: {e}",
        # харчування
        "card_meals": "Харчування",
        "meal_breakfast": "Сніданок",
        "meal_lunch": "Обід",
        "meal_dinner": "Вечеря",
        "s_breakfast_at": "Нагадати о",
        "s_lunch_at": "Нагадати о",
        "s_dinner_at": "Нагадати о",
        "s_meal_pause_min": "Пауза на їжу",
        "meal_title_breakfast": "Час снідати",
        "meal_title_lunch": "Час обідати",
        "meal_title_dinner": "Час вечеряти",
        "meal_text": "Відійдіть від екрана й поїжте спокійно — перерви й вода стануть на паузу на {time}.",
        "meal_go": "Йду їсти",
        "meal_snooze": "Через {min} хв",
        "meal_over_title": "Смачного було? Продовжуємо?",
        "meal_over_text": "Таймери перерв і води почнуть відлік з початку.",
        "meal_more": "Ще {min} хв",
        "meal_until_breakfast": "сніданок до {time}",
        "meal_until_lunch": "обід до {time}",
        "meal_until_dinner": "вечеря до {time}",
        "preview_meal": "Їжа",
        # кінець робочого дня
        "card_day_end": "Кінець робочого дня",
        "day_end_toggle": "Нагадувати, що час відпочивати",
        "s_day_end_at": "Робочий день до",
        "day_end_title": "Робочий день скінчився",
        "day_end_text": "Час відпочити! Сьогодні перерв: {breaks}, води: {volume}. "
                        "«Завершити день» поставить Rhythmos на паузу до ранку.",
        "day_end_finish": "Завершити день",
        "day_end_snooze": "Ще {min} хв",
        "preview_day_end": "Кінець дня",
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
        "tagline": "the rhythm of a healthy day",
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
        "warn_title_mini": "Mini break coming up",
        "warn_title_long": "Long break coming up",
        "warn_title_workout": "Long break coming up — workout",
        "warn_countdown": "Starts in {time}",
        "ok": "OK",
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
        "drank_female": "Done",
        "drank_male": "Done",
        "drank_custom": "Done",
        "tab_status": "Status",
        "tab_stats": "Statistics",
        "tab_settings": "Settings",
        "saved": "Saved ",
        "pause_btn": "Pause {time}",
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
        "water_today": "today {n} of {goal} · {volume}",
        "water_next": "until next glass  ·  {progress}",
        "m_breaks": "breaks done",
        "m_postponed": "postponed",
        "stats_today": "Today, {date}",
        "stats_day": "{weekday}, {date}",
        "range_total": "Last {n} days: {breaks} breaks · {skipped} skipped · {rate} done · "
                       "{water} glasses of water ({volume}, {avg} a day on average)",
        "range_more": "At the computer {work} · movement {active} · {meals} meals · water goal streak: {streak}",
        "best_day": " · best day {day}: {n} breaks",
        "card_last_n": "Last {n} days",
        "range_days": "{n} days",
        "m_work": "hours of work",
        "m_active": "min moving",
        "m_meals": "meals",
        "done_rate": "{pct}% done",
        "postponed_n": "{n} postponed",
        "day_end_at_tip": "day finished at {time}",
        "tip_work": "At the computer",
        "tip_active": "Movement",
        "tip_meals": "Meals",
        "tip_day_end": "Day finished",
        "tip_mini": "Mini breaks",
        "tip_long": "Long breaks",
        "tip_skipped": "Skipped",
        "tip_postponed": "Postponed",
        "tip_day_water": "Water",
        "lg_mini": "mini",
        "lg_long": "long",
        "lg_skipped": "skipped",
        "lg_water": "water (filled — goal met)",
        "today": "today",
        "weekdays": "Mon Tue Wed Thu Fri Sat Sun",
        "card_breaks": "Breaks",
        "card_long": "Long breaks",
        "card_other": "Other",
        "card_postpone": "Postpone & pause",
        "s_pause_min": "Pause length",
        "card_preview": "Preview",
        "workout_toggle": "Interval workout",
        "sound_toggle": "Sound at start and end",
        "autostart_toggle": "Start with Windows",
        "autostart_toggle_mac": "Open at login",
        "updates_toggle": "Check for updates",
        "card_sound": "Sound",
        "sound_name_label": "Notification sound",
        "snd_notification": "Notification",
        "snd_reminder": "Reminder",
        "snd_message": "Message",
        "snd_mail": "Mail",
        "snd_chime": "Chime",
        "snd_default": "Default",
        "snd_ding": "Ding",
        "snd_nudge": "Nudge",
        "snd_balloon": "Balloon",
        "snd_classic": "Classic notify",
        "snd_exclamation": "Exclamation",
        "snd_device": "Device",
        "snd_unlock": "Unlock",
        "snd_print": "Print complete",
        "snd_logon": "Logon",
        "snd_chimes": "Chimes",
        "snd_chord": "Chord",
        "snd_tada": "Tada",
        "group_buttons_toggle": "Muscle group buttons on breaks",
        "update_menu": "Update to {version}",
        "update_banner": "Version {version} is out — update",
        "update_toast_title": "Version {version} is available",
        "update_toast_text": "Rhythmos will download and install it by itself, then restart. Your settings stay.",
        "download": "Open page",
        "update_now": "Update",
        "updating_title": "Updating to {version}",
        "updating_progress": "Downloading… {percent}%",
        "updating_install": "Installing… Rhythmos will restart in a moment.",
        "update_failed_title": "Automatic update failed",
        "update_failed_text": "Download the installer from the release page and install it over this one — your settings stay.",
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
        "water_profile": "Intake",
        "water_profile_female": "Female",
        "water_profile_male": "Male",
        "water_profile_custom": "Custom",
        "water_hint_auto": "EFSA recommends {volume} of drinks a day (food provides about 20% more). "
                           "A reminder every {interval} spreads it over 8 hours at the computer.",
        "water_hint_custom": "EFSA guideline: {female} of drinks a day for women, {male} for men. "
                             "To drink {goal} in 8 hours, get a reminder at least every {interval}.",
        "s_intensity": "Exercise intensity",
        "intensity_1": "light",
        "intensity_2": "moderate",
        "intensity_3": "vigorous",
        "autostart_error": "Could not change autostart: {e}",
        "card_meals": "Meals",
        "meal_breakfast": "Breakfast",
        "meal_lunch": "Lunch",
        "meal_dinner": "Dinner",
        "s_breakfast_at": "Remind at",
        "s_lunch_at": "Remind at",
        "s_dinner_at": "Remind at",
        "s_meal_pause_min": "Meal pause",
        "meal_title_breakfast": "Time for breakfast",
        "meal_title_lunch": "Time for lunch",
        "meal_title_dinner": "Time for dinner",
        "meal_text": "Step away from the screen and enjoy your meal — breaks and water pause for {time}.",
        "meal_go": "Going to eat",
        "meal_snooze": "In {min} min",
        "meal_over_title": "Enjoyed your meal? Shall we continue?",
        "meal_over_text": "Break and water timers will start over.",
        "meal_more": "{min} more min",
        "meal_until_breakfast": "breakfast until {time}",
        "meal_until_lunch": "lunch until {time}",
        "meal_until_dinner": "dinner until {time}",
        "preview_meal": "Meal",
        "card_day_end": "End of workday",
        "day_end_toggle": "Remind me it's time to rest",
        "s_day_end_at": "Workday ends at",
        "day_end_title": "The workday is over",
        "day_end_text": "Time to rest! Today: {breaks} breaks, {volume} of water. "
                        "“Finish the day” pauses Rhythmos until morning.",
        "day_end_finish": "Finish the day",
        "day_end_snooze": "{min} more min",
        "preview_day_end": "Day end",
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
