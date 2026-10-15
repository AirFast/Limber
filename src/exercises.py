"""The Rhythmos exercise library. Each exercise is described in both languages and has a muscle group.

Entry: (kind, group, level, (title_uk, text_uk), (title_en, text_en))
  kind:   mini: a mini break (seated, no preparation)
          active: a short body exercise on a mini break (intensity level 2+)
          long: a long break without a workout; the text is a list of steps
          workout: an interval workout exercise; level 1–3
"""
import random

import i18n

GROUPS = ("eyes", "neck", "back", "arms", "legs", "body")

EXERCISES = [
    # ---------- mini breaks ----------
    ("mini", "eyes", None, ("Правило 20-20-20", "Знайдіть предмет щонайменше за 6 метрів і дивіться на нього 20 секунд."),
     ("The 20-20-20 rule", "Find something at least 6 metres away and look at it for 20 seconds.")),
    ("mini", "eyes", None, ("Кліпання", "Часто покліпайте 10 секунд, потім заплющіть очі й розслабтеся."),
     ("Blinking", "Blink rapidly for 10 seconds, then close your eyes and relax.")),
    ("mini", "eyes", None, ("Очі вгору-вниз", "Не повертаючи голови, повільно подивіться вгору, потім униз. Повторіть 5 разів."),
     ("Eyes up and down", "Without moving your head, slowly look up, then down. Repeat 5 times.")),
    ("mini", "eyes", None, ("Очі вліво-вправо", "Не повертаючи голови, повільно переведіть погляд уліво, потім управо. 5 разів."),
     ("Eyes left and right", "Without moving your head, slowly look left, then right. Repeat 5 times.")),
    ("mini", "eyes", None, ("Вісімка очима", "Повільно «намалюйте» очима велику вісімку: тричі в один бік і тричі в інший."),
     ("Figure eight", "Slowly trace a large figure eight with your eyes: three times each way.")),
    ("mini", "eyes", None, ("Ближче — далі", "Подивіться на палець перед носом, потім удалину за вікно. Повторіть 5 разів."),
     ("Near and far", "Focus on a finger in front of your nose, then on something out the window. Repeat 5 times.")),
    ("mini", "eyes", None, ("Пальмінг", "Розітріть долоні до тепла й накрийте ними заплющені очі. Посидьте в темряві."),
     ("Palming", "Rub your palms until warm and cup them over your closed eyes. Rest in the dark.")),
    ("mini", "eyes", None, ("Кола очима", "Повільно обведіть очима велике коло — тричі за годинниковою стрілкою й тричі проти."),
     ("Eye circles", "Slowly roll your eyes in a big circle — three times clockwise and three times anticlockwise.")),
    ("mini", "eyes", None, ("Діагоналі", "Подивіться в лівий верхній кут, потім у правий нижній, і навпаки. По 5 разів."),
     ("Diagonals", "Look to the top left, then the bottom right, and the other way round. 5 times each.")),

    ("mini", "neck", None, ("Нахили голови", "Нахиліть голову до правого плеча, затримайтеся на 10 секунд. Потім до лівого."),
     ("Head tilts", "Tilt your head towards your right shoulder and hold for 10 seconds. Then the left.")),
    ("mini", "neck", None, ("Кола плечима", "Покрутіть плечима 10 разів назад, потім 10 разів уперед."),
     ("Shoulder rolls", "Roll your shoulders backwards 10 times, then forwards 10 times.")),
    ("mini", "neck", None, ("Повороти голови", "Повільно поверніть голову ліворуч, затримайтеся на 5 секунд, потім праворуч. 5 разів."),
     ("Head turns", "Slowly turn your head to the left, hold for 5 seconds, then to the right. 5 times.")),
    ("mini", "neck", None, ("Підборіддя до грудей", "Опустіть підборіддя до грудей і відчуйте розтяжку шиї ззаду — 15 секунд."),
     ("Chin to chest", "Lower your chin to your chest and feel the stretch at the back of your neck — 15 seconds.")),
    ("mini", "neck", None, ("Втягування підборіддя", "Не нахиляючи голови, відведіть підборіддя назад, ніби робите «подвійне підборіддя». 10 разів."),
     ("Chin tucks", "Without tilting your head, draw your chin straight back into a 'double chin'. 10 times.")),
    ("mini", "neck", None, ("Плечі до вух", "Підніміть плечі до вух, затримайтеся на 3 секунди й розслаблено опустіть. 10 разів."),
     ("Shoulder shrugs", "Lift your shoulders up to your ears, hold for 3 seconds and let them drop. 10 times.")),

    ("mini", "back", None, ("Постава", "Сядьте рівно: стопи на підлозі, спина на спинці крісла, плечі опущені й розслаблені."),
     ("Posture", "Sit up straight: feet flat, back against the chair, shoulders down and relaxed.")),
    ("mini", "back", None, ("Котик сидячи", "Сидячи, по черзі округлюйте спину й прогинайтеся в попереку. 10 разів."),
     ("Seated cat-cow", "While seated, alternate rounding and arching your back. 10 times.")),
    ("mini", "back", None, ("Скручування сидячи", "Поверніть корпус, тримаючись за спинку стільця, — по 15 секунд у кожен бік."),
     ("Seated twist", "Twist your torso, holding the back of the chair — 15 seconds each way.")),
    ("mini", "back", None, ("Олівець між лопатками", "Зведіть лопатки, ніби тримаєте між ними олівець. 5 секунд, 10 разів."),
     ("Pencil squeeze", "Squeeze your shoulder blades as if holding a pencil between them. 5 seconds, 10 times.")),
    ("mini", "back", None, ("Потягування вгору", "Зчепіть пальці, виверніть долоні до стелі й потягніться вгору на 15 секунд."),
     ("Overhead reach", "Interlace your fingers, turn your palms to the ceiling and reach up for 15 seconds.")),

    ("mini", "arms", None, ("Кулаки", "Стисніть кулаки, потім широко розчепірте пальці. Повторіть 10 разів."),
     ("Fists", "Make tight fists, then spread your fingers wide. Repeat 10 times.")),
    ("mini", "arms", None, ("Кола зап'ястями", "Покрутіть кистями по 10 разів у кожен бік."),
     ("Wrist circles", "Circle your wrists 10 times in each direction.")),
    ("mini", "arms", None, ("Розтяжка передпліччя", "Витягніть руку долонею вперед і другою рукою м'яко потягніть пальці на себе. По 15 секунд."),
     ("Forearm stretch", "Hold one arm out, palm forward, and gently pull the fingers back with the other hand. 15 seconds each.")),
    ("mini", "arms", None, ("Пальці", "По черзі торкайтеся великим пальцем кінчиків інших пальців. 10 кіл на кожній руці."),
     ("Finger taps", "Touch your thumb to each fingertip in turn. 10 rounds on each hand.")),
    ("mini", "arms", None, ("Струсніть руками", "Опустіть руки вздовж тіла й легко струсніть кистями 10 секунд."),
     ("Shake out", "Let your arms hang and gently shake out your hands for 10 seconds.")),

    ("mini", "legs", None, ("Кола стопами", "Підніміть стопи й покрутіть ними по 10 разів у кожен бік."),
     ("Ankle circles", "Lift your feet and circle your ankles 10 times in each direction.")),
    ("mini", "legs", None, ("Носок — п'ятка", "Сидячи, по черзі піднімайте носки й п'яти — 20 разів."),
     ("Toe-heel rocks", "While seated, alternately lift your toes and heels — 20 times.")),
    ("mini", "legs", None, ("Випрямлення ніг", "Сидячи, випряміть ногу й затримайте на 5 секунд. По 10 разів кожною."),
     ("Leg extensions", "While seated, straighten one leg and hold for 5 seconds. 10 times each.")),

    ("mini", "body", None, ("Дихання 4-4-6", "Вдих на 4 рахунки, затримка на 4, повільний видих на 6. Повторіть 3 рази."),
     ("4-4-6 breathing", "Breathe in for 4 counts, hold for 4, breathe out slowly for 6. Repeat 3 times.")),
    ("mini", "body", None, ("Дихання животом", "Покладіть руку на живіт і дихайте так, щоб піднімався живіт, а не груди. 6 вдихів."),
     ("Belly breathing", "Place a hand on your belly and breathe so that it rises, not your chest. 6 breaths.")),
    ("mini", "body", None, ("Хвилина тиші", "Заплющіть очі й просто прислухайтеся до звуків довкола."),
     ("A quiet moment", "Close your eyes and simply listen to the sounds around you.")),

    # ---------- active mini exercises ----------
    ("active", "legs", None, ("10 присідань", "Встаньте й зробіть 10 спокійних присідань. Спина рівна, п'яти на підлозі."),
     ("10 squats", "Stand up and do 10 easy squats. Keep your back straight and heels down.")),
    ("active", "legs", None, ("Підйоми на носки", "Встаньте й 20 разів підніміться на носки, повільно опускаючись."),
     ("Calf raises", "Stand up and rise onto your toes 20 times, lowering slowly.")),
    ("active", "legs", None, ("Розтяжка стегна", "Стоячи й тримаючись за стіл, підтягніть п'яту до сідниці. По 15 секунд кожною."),
     ("Quad stretch", "Standing and holding the desk, pull your heel towards your glutes. 15 seconds each.")),
    ("active", "arms", None, ("Віджимання від столу", "Зробіть 10 віджимань від краю стійкого столу."),
     ("Desk push-ups", "Do 10 push-ups against the edge of a sturdy desk.")),
    ("active", "neck", None, ("Кола руками", "Встаньте й зробіть 10 великих кіл прямими руками вперед і 10 назад."),
     ("Arm circles", "Stand up and make 10 big circles with straight arms forwards and 10 backwards.")),
    ("active", "back", None, ("Нахил до носків", "Встаньте, повільно нахиліться до носків і розслабте шию — 15 секунд."),
     ("Forward fold", "Stand up, slowly bend towards your toes and let your neck relax — 15 seconds.")),
    ("active", "body", None, ("Потягніться", "Встаньте на носки, потягніться руками вгору й затримайтеся на 10 секунд."),
     ("Stretch up", "Stand on your toes, reach up high and hold for 10 seconds.")),
    ("active", "body", None, ("Пройдіться", "Встаньте й пройдіться кімнатою — сидіння теж треба перебивати."),
     ("Take a walk", "Get up and walk around the room — long sitting needs breaking up too.")),

    # ---------- long break without a workout ----------
    ("long", "eyes", None, ("Відпочинок для очей", ["Відведіть погляд від екрана й подивіться вдалину — 30 секунд.",
                                                     "Часто покліпайте 10 секунд.",
                                                     "Пальмінг: теплі долоні на заплющені очі на хвилину.",
                                                     "Повільно обведіть очима коло в кожен бік."]),
     ("Eye rest", ["Look away from the screen into the distance — 30 seconds.", "Blink rapidly for 10 seconds.",
                   "Palming: warm palms over closed eyes for a minute.", "Slowly roll your eyes in a circle each way."])),
    ("long", "neck", None, ("Шия та плечі", ["Повільно покрутіть головою по 5 разів у кожен бік.",
                                             "Зведіть лопатки й потримайте 5 секунд — 10 разів.",
                                             "Потягніть руку через груди іншою рукою — по 15 секунд."]),
     ("Neck and shoulders", ["Slowly roll your head 5 times in each direction.",
                             "Squeeze your shoulder blades together for 5 seconds — 10 times.",
                             "Pull one arm across your chest with the other — 15 seconds each."])),
    ("long", "back", None, ("Розтяжка спини", ["Встаньте, зчепіть руки в замок над головою.", "Потягніться вгору на 10 секунд.",
                                               "Нахиліться вліво, потім управо — по 10 секунд.", "Повторіть 3 рази."]),
     ("Back stretch", ["Stand up and interlace your fingers above your head.", "Reach up for 10 seconds.",
                       "Lean left, then right — 10 seconds each.", "Repeat 3 times."])),
    ("long", "back", None, ("Повороти корпусу", ["Сядьте на край стільця, спина рівна.",
                                                 "Поверніть корпус ліворуч і затримайтеся на 15 секунд.",
                                                 "Те саме праворуч.", "Зробіть 3 підходи."]),
     ("Seated twists", ["Sit on the edge of your chair with a straight back.",
                        "Twist your torso to the left and hold for 15 seconds.", "Same to the right.", "Do 3 rounds."])),
    ("long", "arms", None, ("Віджимання від стіни", ["Встаньте на відстані витягнутих рук від стіни.", "Зробіть 10–15 віджимань.",
                                                     "Покрутіть кистями й розімніть зап'ястя."]),
     ("Wall push-ups", ["Stand an arm's length from a wall.", "Do 10–15 push-ups.",
                        "Circle your hands and loosen your wrists."])),
    ("long", "arms", None, ("Руки й зап'ястя", ["Покрутіть кистями по 10 разів у кожен бік.",
                                                "Потягніть пальці на себе й від себе — по 15 секунд на кожну руку.",
                                                "Зробіть 10 віджимань від краю столу.", "Струсніть руками й розслабте плечі."]),
     ("Arms and wrists", ["Circle your wrists 10 times each way.",
                          "Pull your fingers back and then forward — 15 seconds per hand.",
                          "Do 10 push-ups against the desk.", "Shake out your arms and relax your shoulders."])),
    ("long", "legs", None, ("Ноги", ["Встаньте й зробіть 10 присідань.", "Нахиліться й потягніться до пальців ніг — 15 секунд.",
                                     "Підніміться на носки 15 разів."]),
     ("Legs", ["Stand up and do 10 squats.", "Bend forward and reach for your toes — 15 seconds.",
               "Rise onto your toes 15 times."])),
    ("long", "body", None, ("Прогулянка", ["Встаньте з-за столу.", "Пройдіться кімнатою чи коридором.",
                                           "Подивіться у вікно вдалину.", "Випийте склянку води."]),
     ("A short walk", ["Get up from your desk.", "Walk around the room or down the hallway.",
                       "Look out of the window into the distance.", "Drink a glass of water."])),
    ("long", "body", None, ("Розкриття грудей", ["Станьте в дверному отворі, долоні на одвірках.",
                                                 "Подайтеся вперед до легкого натягу в грудях — 20 секунд.",
                                                 "Повторіть 3 рази, глибоко дихаючи."]),
     ("Chest opener", ["Stand in a doorway with your palms on the frame.",
                       "Lean forward until you feel a gentle stretch in your chest — 20 seconds.",
                       "Repeat 3 times, breathing deeply."])),

    # ---------- workout: level 1 (easy) ----------
    ("workout", "neck", 1, ("Кола плечима", "Великі повільні кола плечима: половину часу вперед, половину — назад."),
     ("Shoulder circles", "Big slow shoulder circles: half the time forwards, half backwards.")),
    ("workout", "neck", 1, ("Розтяжка шиї", "Повільно нахиляйте голову вперед і в боки, затримуючись на 5 секунд."),
     ("Neck stretch", "Slowly tilt your head forward and to each side, holding for 5 seconds.")),
    ("workout", "back", 1, ("Нахили в боки", "Руки на поясі, повільно нахиляйтеся вліво й управо."),
     ("Side bends", "Hands on hips, slowly bend to the left and to the right.")),
    ("workout", "back", 1, ("Повороти корпусу", "Стоячи, руки перед грудьми, плавно повертайте корпус уліво-вправо."),
     ("Torso twists", "Standing, arms in front of your chest, gently twist left and right.")),
    ("workout", "back", 1, ("Котик біля столу", "Руки на край столу, по черзі округлюйте й прогинайте спину."),
     ("Desk cat-cow", "Hands on the desk edge, alternate rounding and arching your back.")),
    ("workout", "back", 1, ("Кола тазом", "Руки на поясі, повільні кола тазом в обидва боки."),
     ("Hip circles", "Hands on hips, slow hip circles in both directions.")),
    ("workout", "arms", 1, ("Кола руками", "Руки в сторони, маленькі кола: половину часу вперед, половину — назад."),
     ("Arm circles", "Arms out to the sides, small circles: half the time forwards, half backwards.")),
    ("workout", "arms", 1, ("Розкриття грудей", "Зчепіть руки за спиною, розправте плечі й потягніть руки назад і вниз."),
     ("Chest opener", "Clasp your hands behind your back, open your shoulders and pull your arms back and down.")),
    ("workout", "legs", 1, ("Підйоми на носки", "Тримаючись за стіл, піднімайтеся на носки й повільно опускайтеся."),
     ("Calf raises", "Holding the desk, rise onto your toes and lower slowly.")),
    ("workout", "legs", 1, ("Перекати з п'яти на носок", "Повільно перекочуйтеся з п'ят на носки й назад."),
     ("Heel-to-toe rocks", "Slowly rock from your heels onto your toes and back.")),
    ("workout", "body", 1, ("Ходьба на місці", "Крокуйте на місці в спокійному темпі, розмахуючи руками."),
     ("March on the spot", "March on the spot at an easy pace, swinging your arms.")),

    # ---------- workout: level 2 (moderate) ----------
    ("workout", "legs", 2, ("Присідання", "Ноги на ширині плечей, сідайте назад, ніби на стілець. Спина рівна."),
     ("Squats", "Feet shoulder-width apart, sit back as if onto a chair. Keep your back straight.")),
    ("workout", "legs", 2, ("Випади на місці", "Крок уперед, обидва коліна під кутом 90°. Чергуйте ноги."),
     ("Lunges", "Step forward until both knees are at 90°. Alternate legs.")),
    ("workout", "legs", 2, ("Стільчик біля стіни", "Спиною до стіни, сповзіть до кута в колінах 90° і тримайте."),
     ("Wall sit", "Back against a wall, slide down until your knees are at 90° and hold.")),
    ("workout", "legs", 2, ("Махи ногою в бік", "Тримаючись за стіл, відводьте пряму ногу в бік. Половину часу — кожною."),
     ("Side leg raises", "Holding the desk, lift a straight leg out to the side. Switch halfway.")),
    ("workout", "arms", 2, ("Віджимання від столу", "Руки на край стійкого столу, тіло рівне, згинайте лікті."),
     ("Desk push-ups", "Hands on the edge of a sturdy desk, body straight, bend your elbows.")),
    ("workout", "arms", 2, ("Зворотні віджимання", "Руки на край стійкого стільця за спиною, згинайте лікті до 90°."),
     ("Chair dips", "Hands on the edge of a sturdy chair behind you, bend your elbows to 90°.")),
    ("workout", "back", 2, ("Супермен стоячи", "Нахиліться вперед з рівною спиною, руки в сторони, зводьте лопатки."),
     ("Standing superman", "Hinge forward with a flat back, arms out to the sides, squeeze your shoulder blades.")),
    ("workout", "neck", 2, ("Підйоми Y-T", "Нахиліться вперед і піднімайте прямі руки буквою Y, потім буквою T."),
     ("Y-T raises", "Hinge forward and lift straight arms into a Y, then into a T.")),
    ("workout", "body", 2, ("Планка на столі", "Передпліччя на стіл, тіло рівною лінією від голови до п'ят. Тримайте."),
     ("Desk plank", "Forearms on the desk, body in a straight line from head to heels. Hold.")),
    ("workout", "body", 2, ("Високі коліна", "Крокуйте на місці, піднімаючи коліна до рівня стегна."),
     ("High knees", "March on the spot, lifting your knees to hip height.")),

    # ---------- workout: level 3 (vigorous) ----------
    ("workout", "body", 3, ("Джампінг-джек", "Стрибок — ноги ширше, руки над головою; стрибок назад. У швидкому темпі."),
     ("Jumping jacks", "Jump feet apart with arms overhead, then jump back. Keep a quick pace.")),
    ("workout", "body", 3, ("Біг на місці", "Швидко, коліна до рівня пояса, активно працюйте руками."),
     ("Running on the spot", "Fast, knees up to waist height, pump your arms.")),
    ("workout", "body", 3, ("Альпініст", "Упор лежачи, по черзі швидко підтягуйте коліна до грудей."),
     ("Mountain climbers", "In a high plank, quickly drive your knees towards your chest in turn.")),
    ("workout", "body", 3, ("Берпі без стрибка", "Присід, руки на підлогу, ноги назад у планку, назад у присід і встати."),
     ("Burpees without the jump", "Squat, hands to the floor, step back into a plank, back to a squat and stand up.")),
    ("workout", "legs", 3, ("Присідання зі стрибком", "Присід і вибуховий стрибок угору. Приземляйтеся м'яко, на зігнуті ноги."),
     ("Squat jumps", "Squat and jump up explosively. Land softly on bent knees.")),
    ("workout", "legs", 3, ("Випади з чергуванням", "Глибокі випади вперед, по черзі кожною ногою."),
     ("Alternating lunges", "Deep forward lunges, alternating legs.")),
    ("workout", "legs", 3, ("Присідання сумо", "Широко ноги, носки назовні, глибокий присід."),
     ("Sumo squats", "Wide stance, toes out, deep squat.")),
    ("workout", "arms", 3, ("Віджимання", "Від підлоги або з колін. Тіло рівне, опускайтеся грудьми до підлоги."),
     ("Push-ups", "On the floor or on your knees. Keep your body straight, chest towards the floor.")),
    ("workout", "arms", 3, ("Вузькі віджимання", "Долоні під плечима, лікті йдуть уздовж тіла. Можна з колін."),
     ("Close-grip push-ups", "Hands under your shoulders, elbows tucked in. Knees down is fine.")),
    ("workout", "back", 3, ("Планка", "Упор на передпліччя, тіло рівне, живіт підтягнутий. Тримайте."),
     ("Plank", "On your forearms, body straight, core tight. Hold.")),
    ("workout", "back", 3, ("Бокова планка", "На передпліччі боком, тіло рівне. Половину часу — на кожен бік."),
     ("Side plank", "On one forearm, body straight. Switch sides halfway.")),
    ("workout", "back", 3, ("Ягідичний місток", "Лежачи на спині, ноги зігнуті: піднімайте таз до прямої лінії й опускайте."),
     ("Glute bridge", "Lying on your back with knees bent, lift your hips into a straight line and lower.")),
]


def _localize(entry):
    _kind, group, _level, uk, en = entry
    title, text = uk if i18n.get_language() == "uk" else en
    return title, text, group


def _select(kind, group=None, levels=None):
    return [_localize(e) for e in EXERCISES
            if e[0] == kind and (group is None or e[1] == group) and (levels is None or e[2] in levels)]


def mini_pool(level, group=None):
    """A mini break: calm exercises; at level 2+ sometimes a short body exercise."""
    if group:
        return _select("mini", group) + (_select("active", group) if level >= 2 else [])
    if level >= 2 and random.random() < 0.4:
        return _select("active")
    return _select("mini")


def long_pool(group=None):
    return _select("long", group) or _select("long")


def workout_pool(level, group=None):
    """Workout exercises: the own level and one below; for a group, from any level,
    and for the eyes (the workout has none) the mini eye exercises."""
    levels = {level, level - 1}
    pool = _select("workout", group, levels)
    if group and not pool:
        pool = _select("workout", group) or _select("mini", group)
    return pool
