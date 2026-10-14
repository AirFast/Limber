"""Логіка system.busy_reason на простих даних, без звернень до ОС, і короткі перевірки на справжній ОС."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import system  # noqa: E402

MONITOR = (0, 0, 2560, 1440)
REASONS = (None, "fullscreen", "camera", "microphone")


def test_covers_monitor():
    assert system._covers_monitor((0, 0, 2560, 1440), MONITOR)
    assert system._covers_monitor((-8, -8, 2568, 1448), MONITOR)            # трохи більше за екран
    assert not system._covers_monitor((-8, -8, 2568, 1408), MONITOR)        # розгорнуте: над панеллю завдань
    assert not system._covers_monitor((0, 0, 1280, 1440), MONITOR)          # половина екрана
    assert not system._covers_monitor((0, 0, 2560, 1440), (2560, 0, 4480, 1080))  # інший монітор
    assert not system._covers_monitor((0, 0, 0, 0), (0, 0, 0, 0))           # порожній монітор


def test_fullscreen_window_windows_logic():
    def check(**overrides):
        args = dict(class_name="Chrome_WidgetWin_1", pid=200, own_pid=100, rect=MONITOR, monitor=MONITOR)
        args.update(overrides)
        return system._is_fullscreen_window(**args)

    assert check()
    assert not check(pid=100)                                   # власний екран перерви
    for shell in ("Progman", "WorkerW", "Shell_TrayWnd"):
        assert not check(class_name=shell)
    assert not check(rect=(-8, -8, 2568, 1408))                 # розгорнуте вікно
    assert not check(rect=(-8, -8, 2568, 1448), maximized_with_title=True)  # автоприховування панелі
    assert check(rect=(-8, -8, 2568, 1448))                     # без заголовка — справжній повний екран
    assert check(rect=(2560, 0, 4480, 1080), monitor=(2560, 0, 4480, 1080))  # другий монітор


def test_device_in_use():
    assert not system._device_in_use([])
    assert not system._device_in_use([{}])                      # ключ NonPackaged сам без значень
    assert not system._device_in_use([{"LastUsedTimeStart": 0, "LastUsedTimeStop": 0}])     # ніколи не вмикали
    assert not system._device_in_use([{"LastUsedTimeStart": 5, "LastUsedTimeStop": 9}])     # уже закінчили
    assert not system._device_in_use([{"LastUsedTimeStart": 5}])                           # немає Stop
    assert system._device_in_use([{"LastUsedTimeStart": 5, "LastUsedTimeStop": 9},
                                  {"LastUsedTimeStart": 133700000000000000, "LastUsedTimeStop": 0}])


def test_device_in_use_stops_early():
    seen = []

    def apps():
        for app in ({"LastUsedTimeStart": 1, "LastUsedTimeStop": 0}, {"LastUsedTimeStart": 2, "LastUsedTimeStop": 3}):
            seen.append(app)
            yield app

    assert system._device_in_use(apps())
    assert len(seen) == 1


def _mac_window(x=0, y=0, w=1512, h=982, layer=0, pid=200, owner="Safari", alpha=1.0):
    return {"kCGWindowLayer": layer, "kCGWindowOwnerPID": pid, "kCGWindowOwnerName": owner, "kCGWindowAlpha": alpha,
            "kCGWindowBounds": {"X": x, "Y": y, "Width": w, "Height": h}}


def test_fullscreen_in_mac_logic():
    screens = [(0, 0, 1512, 982), (1512, 0, 3432, 1080)]
    assert not system._fullscreen_in([], screens, 100)
    assert system._fullscreen_in([_mac_window()], screens, 100)
    assert system._fullscreen_in([_mac_window(x=1512, w=1920, h=1080)], screens, 100)  # на другому екрані
    assert not system._fullscreen_in([_mac_window(pid=100)], screens, 100)              # власне вікно перерви
    assert not system._fullscreen_in([_mac_window(y=33, h=880)], screens, 100)          # розгорнуте: між рядком меню й Dock
    assert not system._fullscreen_in([_mac_window(layer=20, owner="Dock")], screens, 100)
    assert not system._fullscreen_in([_mac_window(owner="Window Server")], screens, 100)
    assert not system._fullscreen_in([_mac_window(alpha=0)], screens, 100)              # невидиме вікно-накладка
    assert system._fullscreen_in([_mac_window(y=33, h=880), _mac_window(x=1512, w=1920, h=1080)], screens, 100)
    assert not system._fullscreen_in([{}], screens, 100)                                # неповний словник


def _fake_mac_properties(monkeypatch, props):
    """props: {(framework, об'єкт, selector): значення}; відсутня властивість — None, як помилка ОС."""
    monkeypatch.setattr(system, "_mac_property",
                        lambda framework, obj, selector, as_list=False: props.get((framework, obj, selector)))


def test_microphone_mac_logic(monkeypatch):
    own = os.getpid()
    # macOS 14+: список аудіопроцесів; записує хтось інший
    _fake_mac_properties(monkeypatch, {("CoreAudio", 1, "prs#"): [10, 11],
                                       ("CoreAudio", 10, "piri"): 0, ("CoreAudio", 10, "ppid"): 500,
                                       ("CoreAudio", 11, "piri"): 1, ("CoreAudio", 11, "ppid"): 501})
    assert system._microphone_in_use_mac()
    # записує лише сам Rhythmos — не рахуємо
    _fake_mac_properties(monkeypatch, {("CoreAudio", 1, "prs#"): [11],
                                       ("CoreAudio", 11, "piri"): 1, ("CoreAudio", 11, "ppid"): own})
    assert not system._microphone_in_use_mac()
    # старіша macOS: немає списку процесів — дивимося на стандартний пристрій введення
    _fake_mac_properties(monkeypatch, {("CoreAudio", 1, "dIn "): 42, ("CoreAudio", 42, "gone"): 1})
    assert system._microphone_in_use_mac()
    _fake_mac_properties(monkeypatch, {("CoreAudio", 1, "dIn "): 42, ("CoreAudio", 42, "gone"): 0})
    assert not system._microphone_in_use_mac()
    _fake_mac_properties(monkeypatch, {})
    assert not system._microphone_in_use_mac()


def test_camera_mac_logic(monkeypatch):
    _fake_mac_properties(monkeypatch, {("CoreMediaIO", 1, "dev#"): [5, 6],
                                       ("CoreMediaIO", 5, "gone"): 0, ("CoreMediaIO", 6, "gone"): 1})
    assert system._camera_in_use_mac()
    _fake_mac_properties(monkeypatch, {("CoreMediaIO", 1, "dev#"): [5], ("CoreMediaIO", 5, "gone"): 0})
    assert not system._camera_in_use_mac()
    _fake_mac_properties(monkeypatch, {})                       # камер немає або CoreMediaIO не відповіла
    assert not system._camera_in_use_mac()


def test_fourcc():
    assert system._fourcc("glob") == 0x676C6F62
    assert system._fourcc("dIn ") == 0x64496E20


def test_busy_reason_never_raises(monkeypatch):
    def boom():
        raise OSError("ОС не відповіла")

    for name in ("_fullscreen_windows", "_fullscreen_mac", "_camera_in_use_mac", "_microphone_in_use_mac",
                 "_consent_apps"):
        monkeypatch.setattr(system, name, boom)
    assert system.busy_reason() is None


def test_busy_reason_order(monkeypatch):
    monkeypatch.setattr(system, "_fullscreen_windows", lambda: False)
    monkeypatch.setattr(system, "_fullscreen_mac", lambda: False)
    monkeypatch.setattr(system, "_camera_in_use_mac", lambda: True)
    monkeypatch.setattr(system, "_microphone_in_use_mac", lambda: True)
    monkeypatch.setattr(system, "_consent_apps",
                        lambda capability: [{"LastUsedTimeStart": 1, "LastUsedTimeStop": 0}])
    expected = "camera" if system.IS_WINDOWS or system.IS_MAC else None
    assert system.busy_reason() == expected


@pytest.mark.skipif(not (system.IS_WINDOWS or system.IS_MAC), reason="лише Windows і macOS")
def test_busy_reason_real_os_is_fast():
    system.busy_reason()  # перший виклик завантажує бібліотеки ОС
    start = time.perf_counter()
    for _ in range(5):
        assert system.busy_reason() in REASONS
    assert (time.perf_counter() - start) / 5 < 0.2


@pytest.mark.skipif(not system.IS_WINDOWS, reason="лише Windows")
def test_windows_checks_return_bool():
    assert system._fullscreen_windows() in (True, False)
    for capability in ("webcam", "microphone"):
        assert system._device_in_use(system._consent_apps(capability)) in (True, False)


@pytest.mark.skipif(not system.IS_MAC, reason="лише macOS")
def test_mac_checks_return_bool():
    assert system._fullscreen_mac() in (True, False)
    assert system._camera_in_use_mac() in (True, False)
    assert system._microphone_in_use_mac() in (True, False)
