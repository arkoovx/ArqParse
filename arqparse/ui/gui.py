"""Kivy/KivyMD GUI для arqParse — Material 3, кроссплатформенный."""

from __future__ import annotations

import os
import threading
import webbrowser
from typing import Dict, List

# Отключаем mtdev и probesysfs до инициализации Kivy (требуют прав на /dev/input/event*)
# Используем только SDL2 — работает без root-прав
os.environ.setdefault("KIVY_INPUT_PROVIDERS", "sdl2")
os.environ.setdefault("KIVY_NO_ARGS", "1")
# Фикс: переопределяем дефолтный конфиг Kivy на лету
import kivy.config
kivy.config.Config.set("input", "mouse", "mouse")
# Удаляем probesysfs — именно он сканирует /dev/input/event* и грузит mtdev
for key in list(kivy.config.Config.options("input")):
    if "probesysfs" in kivy.config.Config.get("input", key):
        kivy.config.Config.remove_option("input", key)
# Config.write() убран, настройки применяются только в памяти для текущей сессии


# ─── Добавляем корень проекта в sys.path ──────────────────────────
import sys
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import arqparse.core.auth as auth_module
from arqparse.config.settings import RESULTS_DIR, XRAY_BIN
from arqparse.core.downloader import download_all_tasks
from arqparse.core.parser import read_configs_from_file, read_mtproto_from_file
from arqparse.utils.file_utils import has_insecure_setting
from arqparse.utils.settings_manager import get_tasks, load_settings, save_settings, reset_to_defaults
from arqparse.utils.translator import _, Translator
from arqparse.utils.android_utils import schedule_auto_update
from arqparse.core.xray_manager import ensure_xray
from arqparse.utils.formatting import get_config_id
from arqparse.core.testers import test_xray_configs
from arqparse.core.testers_mtproto import test_mtproto_configs
# ──────────────────────────────────────────────────────────────────


from kivy.core.window import Window
from kivy.animation import Animation
from kivy.clock import Clock
from kivy.graphics import Color, RoundedRectangle
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.screenmanager import FadeTransition
from kivy.utils import platform

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDButton, MDButtonText, MDIconButton


def _mk_btn(text, on_release=None, bg_color=None, text_color=None):
    """Создаёт MDButton (KivyMD 2.x стиль)."""
    btn = MDButton()
    if bg_color:
        btn.md_bg_color = bg_color
    btn.add_widget(MDButtonText(text=text, text_color=text_color or (1, 1, 1, 1)))
    if on_release:
        btn.bind(on_release=on_release)
    return btn


def _set_btn_text(btn, text):
    """Устанавливает текст MDButton (ищет MDButtonText среди детей)."""
    for c in btn.children:
        if isinstance(c, MDButtonText):
            c.text = text
            return


from kivymd.uix.label import MDLabel
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.textfield import MDTextField
from kivymd.uix.selectioncontrol import MDCheckbox

from kivy.factory import Factory
from kivy.uix.behaviors import ButtonBehavior


class ClickableLabel(ButtonBehavior, MDLabel):
    """Лейбл, который можно нажать."""
    pass


class NoTouchCheckbox(MDCheckbox):
    """Чекбокс, который не перехватывает нажатия (решает баг двойного клика на Android)."""
    def on_touch_down(self, touch):
        return False
    def on_touch_move(self, touch):
        return False
    def on_touch_up(self, touch):
        return False


class TaskRow(ButtonBehavior, MDBoxLayout):
    """Строка задачи, кликабельная по всей области."""
    def __init__(self, check_widget, **kwargs):
        super().__init__(**kwargs)
        self.check_widget = check_widget
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(48)
        self.spacing = dp(8)

    def on_release(self):
        if self.check_widget:
            self.check_widget.active = not self.check_widget.active


class NoAnimBtn(ButtonBehavior, MDBoxLayout):
    """Кнопка без анимации при клике."""
    text = StringProperty("")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_y = None
        self.height = dp(32)

        self._label = MDLabel(
            text=self.text,
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            font_size=dp(13),
            size_hint=(1, 1)
        )
        self.add_widget(self._label)

        with self.canvas.before:
            Color(0.25, 0.15, 0.5, 1)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])
            Color(0.35, 0.2, 0.65, 1)
            self._rect = RoundedRectangle(pos=(self.pos[0]+dp(1), self.pos[1]+dp(1)), 
                                         size=(self.size[0]-dp(2), self.size[1]-dp(2)), 
                                         radius=[7])

        self.bind(pos=self._upd_rect, size=self._upd_rect)
        self.bind(text=self._on_text_change)

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
        # Внутренний прямоугольник чуть меньше, чтобы создать эффект рамки в 1dp
        self._rect.pos = (self.pos[0] + dp(1), self.pos[1] + dp(1))
        self._rect.size = (max(0, self.size[0] - dp(2)), max(0, self.size[1] - dp(2)))

    def _on_text_change(self, instance, value):
        self._label.text = value


class TypeBtnButton(ButtonBehavior, MDBoxLayout):
    """Кнопка типа (xray/mtproto) с динамическим цветом."""
    ACCENT = (0.545, 0.361, 0.965, 1)
    INACTIVE_BG = (0.12, 0.12, 0.14, 1)
    ACTIVE_TEXT = (1, 1, 1, 1)
    INACTIVE_TEXT = (0.322, 0.322, 0.357, 1)

    def __init__(self, btn_type="xray", is_active=False, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_x = None
        self.width = dp(80)
        self.size_hint_y = None
        self.height = dp(28)
        self._type_val = btn_type

        self._label = MDLabel(
            text="Xray" if btn_type == "xray" else "MTProto",
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=self.ACTIVE_TEXT if is_active else self.INACTIVE_TEXT,
            font_size=dp(13),
            size_hint=(1, 1)
        )
        self.add_widget(self._label)

        bg = self.ACCENT if is_active else self.INACTIVE_BG
        with self.canvas.before:
            self._color_instr = Color(bg[0], bg[1], bg[2], bg[3])
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])

        self.bind(pos=self._upd_rect, size=self._upd_rect)

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _set_active(self, is_active):
        color = self.ACCENT if is_active else self.INACTIVE_BG
        self._color_instr.rgba = color
        self._label.text_color = self.ACTIVE_TEXT if is_active else self.INACTIVE_TEXT


class AuthTabButton(ButtonBehavior, MDBoxLayout):
    """Кнопка таба авторизации (Вход/Регистрация) с динамическим цветом."""
    tab_type = StringProperty("login")
    text = StringProperty("")
    
    ACCENT = (0.545, 0.361, 0.965, 1)
    INACTIVE_BG = (0, 0, 0, 0)
    ACTIVE_TEXT = (1, 1, 1, 1)
    INACTIVE_TEXT = (0.443, 0.443, 0.478, 1)  # c_dim
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_x = 0.5
        self.size_hint_y = None
        self.height = dp(36)
        self._label = None
        self._is_active = True  # По умолчанию активна

        with self.canvas.before:
            self._color_instr = Color(*self.ACCENT)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[7])

        self.bind(pos=self._upd_rect, size=self._upd_rect, text=self._on_text_changed, tab_type=self._on_tab_type_changed)
        # Создаём label после bind
        self._create_label()

    def _create_label(self):
        """Создаёт MDLabel."""
        if self._label is not None:
            return
        self._label = MDLabel(
            text=self.text or (_("tab_login") if self.tab_type == "login" else _("tab_register")),
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=self.ACTIVE_TEXT,
            font_size=dp(15),
            size_hint=(1, 1),
        )
        self.add_widget(self._label)
    
    def _on_text_changed(self, *args):
        """Обновляет текст при изменении text property."""
        if self._label is not None and self.text:
            self._label.text = self.text

    def _on_tab_type_changed(self, *args):
        """Обновляет текст при изменении tab_type (если text пустой)."""
        if self._label is not None and not self.text:
            self._label.text = _("tab_login") if self.tab_type == "login" else _("tab_register")

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size

    def _set_active(self, is_active):
        self._is_active = is_active
        color = self.ACCENT if is_active else self.INACTIVE_BG
        self._color_instr.rgba = color
        self._label.text_color = self.ACTIVE_TEXT if is_active else self.INACTIVE_TEXT


class AuthMainButton(ButtonBehavior, MDBoxLayout):
    """Главная кнопка авторизации (Войти/Зарегистрироваться) с фиксированным размером."""
    ACCENT = (0.545, 0.361, 0.965, 1)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "horizontal"
        self.size_hint_x = None
        self.width = dp(200)
        self.size_hint_y = None
        self.height = dp(44)

        self._label = MDLabel(
            text=_("btn_login"),
            halign="center",
            valign="middle",
            theme_text_color="Custom",
            text_color=(1, 1, 1, 1),
            font_size=dp(16),
            size_hint=(1, 1),
        )
        self.add_widget(self._label)

        with self.canvas.before:
            self._color_instr = Color(*self.ACCENT)
            self._bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[10])

        self.bind(pos=self._upd_rect, size=self._upd_rect)
        self._anim = None

    def _upd_rect(self, *args):
        self._bg_rect.pos = self.pos
        self._bg_rect.size = self.size
    
    def set_text(self, text: str):
        """Плавно меняет текст с анимацией затухания/появления."""
        if self._anim:
            self._anim.cancel(self._label)
        
        # Анимация затухания
        self._anim = Animation(text_color=(0.3, 0.3, 0.3, 0), duration=0.15)
        self._anim.bind(on_complete=lambda *_: self._show_new_text(text))
        self._anim.start(self._label)
    
    def _show_new_text(self, text):
        """Устанавливает новый текст и анимирует появление."""
        self._label.text = text
        # Анимация появления
        self._anim = Animation(text_color=(1, 1, 1, 1), duration=0.15)
        self._anim.start(self._label)


Factory.register("ClickableLabel", cls=ClickableLabel)
Factory.register("NoAnimBtn", cls=NoAnimBtn)
Factory.register("TypeBtnButton", cls=TypeBtnButton)
Factory.register("AuthTabButton", cls=AuthTabButton)
Factory.register("AuthMainButton", cls=AuthMainButton)


class AndroidFriendlyTextField(MDTextField):
    def on_touch_down(self, touch):
        if platform == 'android' and self.collide_point(*touch.pos):
            # Если поле уже в фокусе, позволяемTextInput двигать каретку,
            # но возвращаем False, чтобы касание прокидывалось в ScrollView
            if self.focus:
                super().on_touch_down(touch)
            return False 
        return super().on_touch_down(touch)


class KeyboardFriendlyScrollView(MDScrollView):
    def on_touch_down(self, touch):
        if platform == 'android' and self.collide_point(*touch.pos):
            touch.ud['start_pos'] = touch.pos
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if platform == 'android' and 'start_pos' in touch.ud:
            start_pos = touch.ud.pop('start_pos')
            # Если это тап (смещение меньше 10dp)
            if abs(touch.x - start_pos[0]) < dp(10) and abs(touch.y - start_pos[1]) < dp(10):
                for widget in self.walk():
                    if isinstance(widget, AndroidFriendlyTextField):
                        if widget.collide_point(*widget.to_widget(*touch.pos)):
                            if not widget.focus:
                                # КЛЮЧЕВОЙ МОМЕНТ: переносим фокус на следующий кадр
                                Clock.schedule_once(lambda dt: setattr(widget, 'focus', True), 0)
                            return True
        return super().on_touch_up(touch)

Factory.register("AndroidFriendlyTextField", cls=AndroidFriendlyTextField)
Factory.register("KeyboardFriendlyScrollView", cls=KeyboardFriendlyScrollView)


ACCENT = "#8b5cf6"
TEXT = "#e4e4e7"
TEXT_DIM = "#71717a"
TEXT_MUTED = "#52525b"
GREEN = "#22c55e"
YELLOW = "#facc15"
RED = "#ef4444"
CARD_BG = (0.086, 0.086, 0.094, 1)
BG = (0.05, 0.05, 0.05, 1)


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> tuple:
    """Конвертирует hex цвет в RGBA кортеж."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4)) + (alpha,)

KV = r'''
#:import dp kivy.metrics.dp

<ClickableLabel>:
    size_hint_y: None
    height: dp(24)

<ThemedCard@MDBoxLayout>:
    orientation: "vertical"
    size_hint_y: None
    adaptive_height: True
    spacing: dp(8)
    padding: [dp(12), dp(10)]
    canvas.before:
        Color:
            rgba: app.c_card
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [14, 14, 14, 14]


<HeaderBar@MDBoxLayout>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(48)
    padding: [dp(12), dp(6)]
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: app.c_bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [0]

    MDLabel:
        id: header_title
        text: app.tr("app_title", app.lang)
        bold: True
        font_style: "Headline"
        role: "small"
        theme_text_color: "Custom"
        text_color: app.c_text
        size_hint_x: 1
        adaptive_height: True
        pos_hint: {"center_y": .5}

    MDIconButton:
        icon: "cog-outline"
        user_font_size: dp(22)
        theme_text_color: "Custom"
        text_color: app.c_dim
        size_hint: None, None
        size: dp(36), dp(36)
        on_release: app.switch_screen("settings")

    MDIconButton:
        icon: "logout-variant"
        user_font_size: dp(22)
        theme_text_color: "Custom"
        text_color: app.c_dim
        size_hint: None, None
        size: dp(36), dp(36)
        on_release: app.logout()

<SettingsHeader@MDBoxLayout>:
    orientation: "horizontal"
    size_hint_y: None
    height: dp(48)
    padding: [dp(12), dp(6)]
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: app.c_bg
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [0]

    MDIconButton:
        icon: "arrow-left"
        user_font_size: dp(22)
        theme_text_color: "Custom"
        text_color: app.c_dim
        size_hint: None, None
        size: dp(36), dp(36)
        on_release: app.switch_screen("main")

    MDLabel:
        id: settings_header_title
        text: app.tr("settings", app.lang)
        bold: True
        theme_text_color: "Custom"
        text_color: app.c_text
        size_hint_x: 1

<RootWidget>:
    orientation: "vertical"

    ScreenManager:
        id: sm

        MDScreen:
            name: "login"

            MDBoxLayout:
                orientation: "vertical"
                padding: dp(24)
                spacing: dp(16)

                Widget:

                MDBoxLayout:
                    orientation: "vertical"
                    adaptive_height: True
                    spacing: 0

                    MDLabel:
                        text: app.tr("app_title", app.lang)
                        halign: "center"
                        font_style: "Display"
                        role: "small"
                        bold: True
                        theme_text_color: "Custom"
                        text_color: app.c_text
                        size_hint_y: None
                        adaptive_height: True

                    MDLabel:
                        text: app.tr("app_subtitle", app.lang)
                        halign: "center"
                        theme_text_color: "Secondary"
                        font_style: "Title"
                        role: "small"
                        size_hint_y: None
                        adaptive_height: True

                Widget:
                    size_hint_y: None
                    height: dp(20)

                ThemedCard:
                    spacing: dp(8)

                    MDLabel:
                        text: app.tr("login", app.lang)
                        theme_text_color: "Hint"
                        size_hint_y: None
                        height: dp(18)

                    MDTextField:
                        id: login_user
                        size_hint_y: None
                        height: dp(44)

                    MDLabel:
                        text: app.tr("password", app.lang)
                        theme_text_color: "Hint"
                        size_hint_y: None
                        height: dp(18)

                    MDTextField:
                        id: login_pass
                        password: True
                        size_hint_y: None
                        height: dp(44)
                        on_text_validate: app.do_auth()

                    MDBoxLayout:
                        orientation: "horizontal"
                        size_hint_y: None
                        height: dp(36)
                        padding: 0
                        spacing: dp(2)

                        AuthTabButton:
                            id: tab_login
                            tab_type: "login"
                            text: app.tr("tab_login", app.lang)
                            on_release: app.set_auth_mode("login")

                        AuthTabButton:
                            id: tab_register
                            tab_type: "register"
                            text: app.tr("tab_register", app.lang)
                            on_release: app.set_auth_mode("register")

                    AuthMainButton:
                        id: auth_btn
                        pos_hint: {"center_x": 0.5}
                        on_release: app.do_auth()

                    MDButton:
                        style: "text"
                        pos_hint: {"center_x": 0.5}
                        on_release: app.enter_guest_mode()
                        
                        MDButtonText:
                            text: app.tr("btn_guest", app.lang)
                            text_color: app.c_accent

                Widget:

                MDBoxLayout:
                    orientation: "horizontal"
                    size_hint_y: None
                    height: dp(24)
                    padding: [0, 0, 0, 0]

                    Widget:

                    MDLabel:
                        text: app.tr("by_author", app.lang)
                        theme_text_color: "Hint"
                        size_hint_x: None
                        width: dp(30) if app.lang == "en" else dp(20)

                    ClickableLabel:
                        id: arq_link_label
                        text: "arq"
                        theme_text_color: "Custom"
                        text_color: app.c_accent
                        bold: True
                        size_hint_x: None
                        width: dp(30)
                        on_release: app.open_channel_link()

                    Widget:

                Widget:

        MDScreen:
            name: "main"

            MDBoxLayout:
                orientation: "vertical"

                HeaderBar:

                KeyboardFriendlyScrollView:
                    do_scroll_x: False
                    bar_width: dp(4)

                    MDBoxLayout:
                        id: main_content
                        orientation: "vertical"
                        padding: [dp(14), dp(12)]
                        spacing: dp(12)
                        adaptive_height: True

                        MDBoxLayout:
                            orientation: "horizontal"
                            size_hint_y: None
                            height: dp(24)
                            spacing: dp(8)
                            padding: [dp(4), 0]

                            MDIcon:
                                icon: "account-circle-outline"
                                font_size: dp(18)
                                theme_text_color: "Custom"
                                text_color: app.c_accent
                                size_hint: None, None
                                size: dp(24), dp(24)
                                pos_hint: {"center_y": .5}

                            MDLabel:
                                text: app.user_login
                                bold: True
                                font_size: dp(16)
                                theme_text_color: "Custom"
                                text_color: app.c_text
                                size_hint_y: None
                                height: dp(24)
                                pos_hint: {"center_y": .5}

                        ThemedCard:
                            id: sub_card
                            spacing: dp(6)

                            MDLabel:
                                text: app.tr("subscription", app.lang)
                                bold: True
                                theme_text_color: "Primary"
                                size_hint_y: None
                                height: dp(20)

                            MDLabel:
                                id: sub_url_label
                                text: app.tr("sub_url_hint", app.lang)
                                theme_text_color: "Secondary"
                                shorten: True
                                shorten_from: "right"
                                size_hint_y: None
                                height: dp(16)

                            MDButton:
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.copy_subscription_url()

                                MDButtonText:
                                    text: app.tr("btn_copy_sub", app.lang)
                                    text_color: app.c_dim

                        MDBoxLayout:
                            id: bot_link_container
                            orientation: "horizontal"
                            size_hint_y: None
                            height: dp(24)
                            spacing: dp(2)

                            MDLabel:
                                text: app.tr("bot_link_prefix", app.lang)
                                theme_text_color: "Hint"
                                size_hint_x: None
                                adaptive_width: True

                            ClickableLabel:
                                id: bot_link_label
                                text: "@arqvpn_bot"
                                theme_text_color: "Custom"
                                text_color: app.c_accent
                                bold: True
                                size_hint_x: None
                                adaptive_width: True
                                on_release: app.open_bot_link()

                        MDButton:
                            id: start_btn
                            size_hint_x: 0.85
                            pos_hint: {"center_x": 0.5}
                            height: dp(56)
                            font_size: dp(18)
                            md_bg_color: app.c_accent
                            on_release: app.start_full_test()

                            MDButtonText:
                                text: app.tr("btn_start_test", app.lang)
                                text_color: 1, 1, 1, 1

                        NoAnimBtn:
                            id: adv_btn
                            text: app.tr("btn_adv_settings", app.lang)
                            size_hint_x: 0.85
                            pos_hint: {"center_x": 0.5}
                            height: dp(32)
                            on_release: app.toggle_advanced()

                        ThemedCard:
                            id: adv_container
                            spacing: dp(8)

                            MDLabel:
                                text: app.tr("select_tasks", app.lang)
                                theme_text_color: "Secondary"
                                size_hint_y: None
                                height: dp(18)

                            MDBoxLayout:
                                id: task_checkboxes
                                orientation: "vertical"
                                adaptive_height: True
                                spacing: dp(2)

                            MDBoxLayout:
                                orientation: "horizontal"
                                adaptive_height: True
                                spacing: dp(6)
                                size_hint_y: None
                                height: dp(38)

                                MDButton:
                                    md_bg_color: (0, 0, 0, 0)
                                    on_release: app.start_download()

                                    MDButtonText:
                                        text: app.tr("btn_download", app.lang)
                                        text_color: app.c_dim

                                MDButton:
                                    md_bg_color: (0, 0, 0, 0)
                                    on_release: app.open_results()
                                    opacity: 0 if app.PLATFORM == "android" else 1
                                    disabled: True if app.PLATFORM == "android" else False
                                    size_hint_x: None if app.PLATFORM == "android" else 1
                                    width: 0 if app.PLATFORM == "android" else self.width

                                    MDButtonText:
                                        text: app.tr("btn_results", app.lang) if app.PLATFORM != "android" else ""
                                        text_color: app.c_dim

                        MDBoxLayout:
                            orientation: "horizontal"
                            size_hint_y: None
                            height: dp(38)
                            spacing: dp(8)

                            MDButton:
                                id: skip_btn
                                disabled: True
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.skip_file()

                                MDButtonText:
                                    text: app.tr("btn_skip", app.lang)
                                    text_color: app.c_muted

                            MDButton:
                                id: stop_btn
                                disabled: True
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.stop_operation()

                                MDButtonText:
                                    text: app.tr("btn_stop", app.lang)
                                    text_color: app.c_muted

                        ThemedCard:
                            spacing: dp(4)

                            MDBoxLayout:
                                orientation: "horizontal"
                                adaptive_height: True
                                size_hint_y: None
                                height: dp(22)

                                MDLabel:
                                    text: app.tr("progress", app.lang)
                                    theme_text_color: "Secondary"
                                    adaptive_width: True

                                MDLabel:
                                    id: progress_label
                                    text: app.tr("ready", app.lang)
                                    theme_text_color: "Secondary"
                                    halign: "right"

                            MDLinearProgressIndicator:
                                id: progress
                                value: 0
                                max: 1.0
                                size_hint_y: None
                                height: dp(4)

                        ThemedCard:
                            spacing: dp(4)

                            MDBoxLayout:
                                orientation: "horizontal"
                                adaptive_height: True
                                size_hint_y: None
                                height: dp(22)

                                MDLabel:
                                    text: app.tr("event_log", app.lang)
                                    bold: True
                                    theme_text_color: "Secondary"

                                Widget:

                                MDIconButton:
                                    icon: "broom"
                                    user_font_size: dp(16)
                                    theme_text_color: "Custom"
                                    text_color: app.c_muted
                                    size_hint: None, None
                                    size: dp(24), dp(24)
                                    on_release: app.clear_log()

                            MDScrollView:
                                id: log_scroll
                                do_scroll_x: False
                                size_hint_y: None
                                height: dp(140)

                                MDLabel:
                                    id: log_label
                                    text: "> " + app.tr("log_started", app.lang)
                                    theme_text_color: "Custom"
                                    text_color: app.c_text
                                    size_hint_y: None
                                    adaptive_height: True

                        Widget:
                            size_hint_y: None
                            height: dp(16)

        MDScreen:
            name: "settings"

            MDBoxLayout:
                orientation: "vertical"

                SettingsHeader:

                KeyboardFriendlyScrollView:
                    do_scroll_x: False
                    bar_width: dp(4)

                    MDBoxLayout:
                        id: settings_content
                        orientation: "vertical"
                        padding: [dp(14), dp(12)]
                        spacing: dp(12)
                        adaptive_height: True

                        ThemedCard:
                            spacing: dp(10)

                            MDLabel:
                                text: app.tr("settings_general", app.lang)
                                bold: True
                                theme_text_color: "Primary"
                                size_hint_y: None
                                height: dp(20)

                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: dp(44)
                                spacing: dp(10)
                                
                                MDLabel:
                                    text: app.tr("auto_update", app.lang)
                                    theme_text_color: "Secondary"
                                    font_size: dp(14)
                                    valign: "center"
                                
                                MDSwitch:
                                    id: auto_update_switch
                                    active: True
                                    pos_hint: {"center_y": .5}

                            MDBoxLayout:
                                orientation: "horizontal"
                                size_hint_y: None
                                height: dp(44)
                                spacing: dp(10)
                                
                                MDLabel:
                                    text: app.tr("language", app.lang)
                                    theme_text_color: "Secondary"
                                    font_size: dp(14)
                                    valign: "center"
                                
                                MDBoxLayout:
                                    orientation: "horizontal"
                                    adaptive_width: True
                                    spacing: dp(4)
                                    pos_hint: {"center_y": .5}

                                    MDButton:
                                        style: "elevated" if app.lang == "ru" else "tonal"
                                        size_hint: None, None
                                        size: dp(48), dp(32)
                                        on_release: app.change_lang("ru")
                                        MDButtonText:
                                            text: "RU"
                                    
                                    MDButton:
                                        style: "elevated" if app.lang == "en" else "tonal"
                                        size_hint: None, None
                                        size: dp(48), dp(32)
                                        on_release: app.change_lang("en")
                                        MDButtonText:
                                            text: "EN"

                            AndroidFriendlyTextField:
                                id: user_agent
                                hint_text: "User-Agent"
                                size_hint_y: None
                                height: dp(44)
                                font_size: dp(14)

                            MDButton:
                                md_bg_color: app.c_accent
                                on_release: app.save_settings_from_ui()

                                MDButtonText:
                                    text: app.tr("btn_save", app.lang)
                                    text_color: 1, 1, 1, 1

                            MDButton:
                                md_bg_color: (0, 0, 0, 0)
                                on_release: app.reset_settings_to_defaults()

                                MDButtonText:
                                    text: app.tr("btn_reset", app.lang)
                                    text_color: app.c_dim

                        MDLabel:
                            text: app.tr("categories", app.lang)
                            bold: True
                            theme_text_color: "Custom"
                            text_color: app.c_accent
                            size_hint_y: None
                            height: dp(22)

                        MDBoxLayout:
                            id: categories_box
                            orientation: "vertical"
                            spacing: dp(10)
                            adaptive_height: True

                        MDButton:
                            size_hint_y: None
                            height: dp(32)
                            md_bg_color: (0, 0, 0, 0)
                            on_release: app.add_category()

                            MDButtonText:
                                text: app.tr("btn_add_category", app.lang)
                                text_color: app.c_accent

                        Widget:
                            size_hint_y: None
                            height: dp(16)
'''


class RootWidget(MDBoxLayout):
    pass


class KivyGUIApp(MDApp):
    user_login = StringProperty("Guest")
    lang = StringProperty("ru")

    def tr(self, key, lang_trigger=None, **kwargs):
        """Хелпер для использования в KV. Явно зависит от lang_trigger."""
        return _(key, **kwargs)

    def change_lang(self, lang_code):
        """Смена языка на лету."""
        if lang_code == self.lang:
            return
        
        # 1. Сначала меняем язык в движке перевода
        Translator.get_instance().set_lang(lang_code)
        
        # 2. Потом меняем свойство, чтобы Kivy увидел изменение и дернул tr()
        self.lang = lang_code
        
        # Сохраняем в настройки
        data = load_settings()
        data["language"] = lang_code
        save_settings(data)
        
        # Обновляем статические переводы в Python части
        if auth_module.is_logged_in():
            session = auth_module.get_session()
            self.user_login = session.get("username", self.tr("msg_user"))
            if hasattr(self, 'root') and self.root:
                self._refresh_sub_url()
        else:
            self.user_login = self.tr("msg_guest")
            if hasattr(self, 'root') and self.root:
                self.root.ids.sub_url_label.text = self.tr("msg_sub_guest")
            
        self._toast(self.tr("msg_saved"))
        # Перерисовываем полностью динамические блоки (чекбоксы и категории)
        self._render_task_checkboxes()
        self._render_categories()
        # Обновляем кнопку авторизации
        if hasattr(self, '_auth_mode'):
            self.set_auth_mode(self._auth_mode)

    def build(self):
        self.title = "arqParse"
        self.PLATFORM = platform
        
        settings = load_settings()
        self.lang = settings.get("language", "ru")
        Translator.get_instance().set_lang(self.lang)

        # Устанавливаем размер окна только если это не мобильное устройство

        if platform not in ('android', 'ios'):
            # Формат 9:16 — 420x800
            Window.size = (420, 800)
            Window.resizable = True
            
        self.theme_cls.theme_style = "Dark"
        try:
            self.theme_cls.material_style = "M3"
        except Exception:
            pass

        self.c_text = (0.894, 0.894, 0.898, 1)
        self.c_accent = (0.545, 0.361, 0.965, 1)
        self.c_dim = (0.443, 0.443, 0.478, 1)
        self.c_muted = (0.322, 0.322, 0.357, 1)
        self.c_card = (0.086, 0.086, 0.094, 1)
        self.c_bg = (0.05, 0.05, 0.05, 1)

        self.advanced_open = False
        self._is_running = False
        self._stop_event = threading.Event()
        self._skip_event = threading.Event()
        self._task_checks: Dict[str, dict] = {}
        self._category_cards: List[dict] = []
        self._loading_active = False
        self._uploading = False  # Флаг для предотвращения двойного обновления
        self._auth_mode = "login"  # "login" or "register"

        Builder.load_string(KV)
        return RootWidget()

    def on_start(self):
        self.root.ids.sm.transition = FadeTransition(duration=0.18)
        self._load_initial_state()
        
        # Планируем автообновление для Android если включено
        settings = load_settings()
        if settings.get("auto_update", True):
            schedule_auto_update()
        
        session = auth_module.get_session()
        logged = session is not None
        if logged:
            self.user_login = session.get("username", self.tr("msg_user"))
            self._refresh_sub_url()
        else:
            self.user_login = self.tr("msg_guest")
        
        self.switch_screen("login" if not logged else "main")
        # Инициализация табов авторизации
        self._init_auth_tabs()
        # Hover-эффект для arq (канал)
        arq_lbl = self.root.ids.arq_link_label
        arq_lbl.bind(on_enter=lambda *_: setattr(arq_lbl, 'text_color', (0.75, 0.55, 1, 1)))
        arq_lbl.bind(on_leave=lambda *_: setattr(arq_lbl, 'text_color', self.c_accent))
        # Hover-эффект для @arqvpn_bot
        bot_lbl = self.root.ids.bot_link_label
        bot_lbl.bind(on_enter=lambda *_: setattr(bot_lbl, 'text_color', (0.75, 0.55, 1, 1)))
        bot_lbl.bind(on_leave=lambda *_: setattr(bot_lbl, 'text_color', self.c_accent))

    def _init_auth_tabs(self):
        self.set_auth_mode("login")

    def set_auth_mode(self, mode: str):
        """Переключение между вкладками Вход/Регистрация."""
        self._auth_mode = mode
        tab_login = self.root.ids.tab_login
        tab_register = self.root.ids.tab_register

        if mode == "login":
            tab_login._set_active(True)
            tab_register._set_active(False)
        else:
            tab_register._set_active(True)
            tab_login._set_active(False)

        # Обновляем текст кнопки авторизации
        auth_btn = self.root.ids.auth_btn
        auth_btn.set_text(self.tr("btn_login") if mode == "login" else self.tr("btn_register"))

    def _load_initial_state(self):
        settings = load_settings()
        self.tasks = get_tasks()
        self.root.ids.user_agent.text = settings.get("user_agent", "")
        self.root.ids.auto_update_switch.active = settings.get("auto_update", True)
        self._render_task_checkboxes()
        self._render_categories(settings)
        # Убираем adv_container из дерева при старте
        parent = self.root.ids.main_content
        if self.root.ids.adv_container.parent is not None:
            parent.remove_widget(self.root.ids.adv_container)

    def switch_screen(self, name: str):
        sm = self.root.ids.sm
        if sm.current != name:
            sm.current = name

    def enter_guest_mode(self):
        """Вход в приложение без авторизации."""
        auth_module.clear_session()
        self.user_login = self.tr("msg_guest")
        self.root.ids.sub_url_label.text = self.tr("msg_sub_guest")
        self.switch_screen("main")
        self._toast(self.tr("msg_guest_active"))

    # ─── Авторизация ───────────────────────────────────────────
    def do_auth(self):
        username = self.root.ids.login_user.text.strip()
        password = self.root.ids.login_pass.text
        is_register = self._auth_mode == "register"

        if len(username) < 3:
            self._toast(self.tr("msg_login_min"))
            return
        if len(password) < 6:
            self._toast(self.tr("msg_pass_min"))
            return

        btn = self.root.ids.auth_btn
        btn.disabled = True
        self._loading_active = True
        self._loading_dots = 0
        self._loading_text = self.tr("msg_connecting") if not is_register else self.tr("msg_registering")
        self._animate_dots(btn)

        def worker():
            err_msg = None
            try:
                server = auth_module.DEFAULT_SERVER
                if not auth_module.check_server(server):
                    err_msg = self.tr("msg_server_offline")
                else:
                    if is_register:
                        auth_module.register(username, password, server)
                    else:
                        auth_module.login(username, password, server)
                    Clock.schedule_once(lambda *_: self._auth_ok(btn), 0)
            except Exception as exc:
                err_msg = str(exc)
            
            if err_msg:
                Clock.schedule_once(lambda *_: self._auth_fail(btn, err_msg), 0)

        threading.Thread(target=worker, daemon=True).start()

    def _animate_dots(self, btn):
        if not self._loading_active:
            return
        dots = "." * (self._loading_dots % 4)
        current_text = self.tr("msg_connecting") if self._auth_mode == "login" else self.tr("msg_registering")
        btn.set_text(f"{current_text}{dots}")
        self._loading_dots += 1
        Clock.schedule_once(lambda *_: self._animate_dots(btn), 0.5)

    def _auth_ok(self, btn):
        self._loading_active = False
        btn.disabled = False
        btn.set_text(self.tr("btn_login") if self._auth_mode == "login" else self.tr("btn_register"))
        
        session = auth_module.get_session()
        if session:
            self.user_login = session.get("username", self.tr("msg_user"))
            
        self._refresh_sub_url()
        self.switch_screen("main")
        Clock.schedule_once(lambda *_: self._show_toast(self.tr("msg_auth_success")), 0.3)

    def _auth_fail(self, btn, msg: str):
        self._loading_active = False
        btn.disabled = False
        # Восстанавливаем текст кнопки в зависимости от режима
        btn.set_text(self.tr("btn_login") if self._auth_mode == "login" else self.tr("btn_register"))

        # Показываем ошибку через Clock в главном потоке
        Clock.schedule_once(lambda *_: self._show_toast(f"{self.tr('msg_auth_error')} {msg}"), 0.1)

    def _show_toast(self, text: str):
        """Показывает toast в главном потоке."""
        self._toast(text)

    def _refresh_sub_url(self):
        try:
            url = auth_module.get_sub_url()
            self.root.ids.sub_url_label.text = url
        except Exception:
            self.root.ids.sub_url_label.text = self.tr("msg_sub_no_url")

    def copy_subscription_url(self):
        text = self.root.ids.sub_url_label.text
        if not text or self.tr("sub_url_hint") in text or text == self.tr("msg_sub_no_url"):
            return

        # 1. Попытка через Kivy Clipboard (работает на Android, iOS, Windows)
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(text)
            if platform in ('android', 'ios', 'win'):
                self._log(self.tr("msg_sub_copied"), "success")
                self._toast(self.tr("msg_sub_copied"))
                return
        except Exception:
            pass

        import os
        is_wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"

        # На Wayland пробуем wl-copy
        if is_wayland:
            import subprocess
            import shutil
            if shutil.which("wl-copy"):
                try:
                    subprocess.run(["wl-copy", "--type", "text/plain"], input=text.encode("utf-8"), timeout=2)
                    self._log(self.tr("msg_sub_copied"), "success")
                    self._toast(self.tr("msg_sub_copied"))
                    return
                except Exception:
                    pass
            # Нет wl-copy — показываем диалог
            self._show_copy_dialog(text)
            return

        # X11 — tkinter работает
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            self._log(self.tr("msg_sub_copied"), "success")
            self._toast(self.tr("msg_sub_copied"))
        except Exception as e:
            self._log(f"Error: {e}", "error")
            self._show_copy_dialog(text)

    def _show_copy_dialog(self, text: str):
        """Показать диалог с ссылкой для ручного копирования."""
        from kivymd.uix.dialog import (
            MDDialog,
            MDDialogHeadlineText,
            MDDialogButtonContainer,
            MDDialogContentContainer,
        )
        from kivy.uix.scrollview import ScrollView
        from kivy.uix.textinput import TextInput
        from kivymd.uix.button import MDButton, MDButtonText

        def _on_close(*_):
            dialog.dismiss()

        scroll = ScrollView(size_hint=(1, None), height=dp(80))
        text_input = TextInput(
            text=text,
            readonly=True,
            size_hint_y=None,
            height=dp(80),
            font_size=dp(12),
            background_color=(0.1, 0.1, 0.15, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
            cursor_color=(0.55, 0.36, 0.96, 1),
        )
        scroll.add_widget(text_input)

        msg = self.tr("dialog_copy_msg_linux")
        if platform == "android":
            msg = self.tr("dialog_copy_msg_android")

        label = MDLabel(
            text=msg,
            theme_text_color="Custom",
            text_color=(0.6, 0.6, 0.65, 1),
            markup=True,
            halign="center",
            size_hint_y=None,
            height=dp(40),
            font_size=dp(12),
        )

        container = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            adaptive_height=True,
            spacing=dp(8),
            padding=dp(10),
        )
        container.add_widget(scroll)
        container.add_widget(label)

        dialog = MDDialog(
            MDDialogHeadlineText(text=self.tr("dialog_copy_title")),
            MDDialogContentContainer(container),
            MDDialogButtonContainer(
                MDButton(MDButtonText(text=self.tr("dialog_copy_close")), on_release=_on_close, md_bg_color=self.c_accent),
            ),
            size_hint_x=0.9,
            auto_dismiss=True,
        )
        dialog.open()

    def open_bot_link(self, *args):
        webbrowser.open("https://t.me/arqvpn_bot")

    def open_channel_link(self, *args):
        webbrowser.open("https://t.me/arqhub")

    # ─── Настройки ─────────────────────────────────────────────
    def save_settings_from_ui(self):
        data = load_settings()
        data["user_agent"] = self.root.ids.user_agent.text.strip()
        data["auto_update"] = self.root.ids.auto_update_switch.active
        data["language"] = self.lang
        tasks = []
        for card in self._category_cards:
            name = card['name_input'].text.strip()
            if not name:
                continue
            urls = [r['input'].text.strip() for r in card['url_rows'] if r['input'].text.strip()]
            if not urls:
                continue
            try:
                max_ping = int(card['max_ping'].text.strip() or "9000")
            except ValueError:
                max_ping = 9000
            try:
                req_count = int(card['req_count'].text.strip() or "10")
            except ValueError:
                req_count = 10
            from arqparse.config.settings import RAW_CONFIGS_DIR
            raw_files = []
            for u in urls:
                fname = u.split("/")[-1].split("?")[0]
                if fname:
                    raw_files.append(os.path.join(RAW_CONFIGS_DIR, fname))
            profile = card['profile'].text.strip()
            out_name = name.lower().replace(' ', '_')
            tasks.append({
                "name": name, "type": card['type_var'], "urls": urls,
                "raw_files": raw_files,
                "target_url": card['target'].text.strip() or "https://www.google.com/generate_204",
                "max_ping_ms": max_ping, "required_count": req_count,
                "profile_title": profile,
                "out_file": os.path.join(RESULTS_DIR, f"top_{out_name}.txt"),
            })
        if tasks:
            data["tasks"] = tasks
        save_settings(data)
        self.tasks = get_tasks()
        self._render_task_checkboxes()
        self._render_categories()
        self._toast(self.tr("msg_saved"))

    def reset_settings_to_defaults(self):
        """Сбрасывает настройки до значений по умолчанию."""
        defaults = reset_to_defaults()
        self.tasks = get_tasks()
        self.lang = defaults.get("language", "ru")
        Translator.get_instance().set_lang(self.lang)
        self._render_task_checkboxes()
        self._render_categories(defaults)
        self.root.ids.user_agent.text = defaults.get("user_agent", "")
        self.root.ids.auto_update_switch.active = defaults.get("auto_update", True)
        self._toast(self.tr("msg_restored"))

    # ─── Чекбоксы ──────────────────────────────────────────────
    def _render_task_checkboxes(self):
        box = self.root.ids.task_checkboxes
        box.clear_widgets()
        self._task_checks.clear()
        for task in self.tasks:
            # Чекбокс, который не перехватывает клики напрямую (защита от багов на Android)
            check = NoTouchCheckbox(
                active=True,
                size_hint=(None, None),
                size=(dp(48), dp(48)),
                pos_hint={"center_y": .5},
            )
            self._task_checks[task["name"]] = {"check": check, "task": task}

            # Обычный Label (не ClickableLabel, так как кликабельной становится вся строка)
            lbl = MDLabel(
                text=f"{task['name']} ({task['type']})",
                theme_text_color="Primary",
                size_hint_y=None,
                height=dp(48),
                valign="center",
                pos_hint={"center_y": .5},
            )
            lbl.bind(size=lambda inst, val: setattr(inst, 'text_size', val))

            # Оборачиваем элементы в TaskRow (позволяет нажимать в любом месте строки)
            row = TaskRow(check_widget=check)
            row.add_widget(check)
            row.add_widget(lbl)
            box.add_widget(row)
    # ─── Категории ─────────────────────────────────────────────
    def _render_categories(self, settings=None):
        box = self.root.ids.categories_box
        box.clear_widgets()
        self._category_cards.clear()
        if settings is None:
            settings = load_settings()
        for td in settings.get("tasks", []):
            self._add_category_card(td)

    def _update_card_canvas(self, widget):
        for instr in widget.canvas.before.children[:]:
            if isinstance(instr, RoundedRectangle):
                instr.pos = widget.pos
                instr.size = widget.size
                break

    def _mk_input(self, hint="", height=dp(40), text=""):
        cls = AndroidFriendlyTextField if platform == 'android' else MDTextField
        w = cls(hint_text=hint, size_hint_y=None,
                        height=height, font_size=dp(15), multiline=False)
        w.text = text
        return w

    def _mk_small(self, width, hint="", text=""):
        cls = AndroidFriendlyTextField if platform == 'android' else MDTextField
        w = cls(hint_text=hint, size_hint_x=None, width=width,
                        height=dp(40), font_size=dp(15), multiline=False)
        w.text = text
        return w

    def _add_category_card(self, data=None):
        if data is None:
            data = {"name": "", "type": "xray", "urls": [""], "target_url": "https://www.google.com/generate_204",
                    "max_ping_ms": 9000, "required_count": 10, "profile_title": ""}

        box = self.root.ids.categories_box
        card = {'type_var': data.get("type", "xray"), 'url_rows': [], 'type_btns': []}

        frame = MDBoxLayout(orientation="vertical", size_hint_y=None,
                            adaptive_height=True, spacing=dp(10),
                            padding=[dp(14), dp(12)])
        with frame.canvas.before:
            Color(*self.c_card)
            RoundedRectangle(pos=frame.pos, size=frame.size, radius=[14, 14, 14, 14])
        frame.bind(pos=lambda inst, val: self._update_card_canvas(frame),
                   size=lambda inst, val: self._update_card_canvas(frame))

        name_input = self._mk_input(self.tr("cat_name"), dp(44), data.get("name", ""))
        card['name_input'] = name_input
        frame.add_widget(name_input)

        # Переключаемый тип
        card['type_var'] = data.get("type", "xray")
        type_row = MDBoxLayout(orientation="horizontal", adaptive_height=True,
                               spacing=dp(6), size_hint_y=None, height=dp(36))
        type_lbl = MDLabel(text=self.tr("cat_type"), theme_text_color="Secondary",
                            size_hint_x=None, adaptive_width=True)
        type_row.add_widget(type_lbl)

        card['type_btns'] = []
        
        for btn_type in ["xray", "mtproto"]:
            is_active = (card['type_var'] == btn_type)
            
            btn = TypeBtnButton(btn_type=btn_type, is_active=is_active)
            
            def on_type_click(instance, button=btn, selected_type=btn_type):
                card['type_var'] = selected_type
                for b in card['type_btns']:
                    is_sel = (selected_type == b._type_val)
                    b._set_active(is_sel)
            
            btn.bind(on_release=on_type_click)
            
            type_row.add_widget(btn)
            card['type_btns'].append(btn)
        frame.add_widget(type_row)

        frame.add_widget(MDLabel(text=self.tr("cat_sources"), theme_text_color="Secondary",
                                 bold=True, size_hint_y=None, height=dp(18)))

        url_container = MDBoxLayout(orientation="vertical", adaptive_height=True, spacing=dp(14))
        frame.add_widget(url_container)

        for url in data.get("urls", [""]):
            self._add_url_row(url_container, card, url)

        add_url = MDButton(
            MDButtonText(
                text=self.tr("btn_add_url"),
                text_color=self.c_accent,
            ),
            size_hint_x=None,
            width=dp(140),
            height=dp(30),
            md_bg_color=(0, 0, 0, 0),
        )
        add_url.bind(on_release=lambda *_: self._add_url_row(url_container, card, ""))
        frame.add_widget(add_url)

        target = self._mk_input(self.tr("cat_target"), dp(40), data.get("target_url", "https://www.google.com/generate_204"))
        card['target'] = target
        frame.add_widget(target)

        nums = MDBoxLayout(orientation="horizontal", adaptive_height=True, spacing=dp(6),
                           size_hint_y=None, height=dp(38))
        ping_lbl = MDLabel(text=self.tr("cat_max_ping"), theme_text_color="Secondary",
                           size_hint_x=None, adaptive_width=True)
        nums.add_widget(ping_lbl)
        mp = self._mk_small(dp(65), self.tr("unit_ms"), str(data.get("max_ping_ms", 9000)))
        card['max_ping'] = mp
        nums.add_widget(mp)
        req_lbl = MDLabel(text=self.tr("cat_min_count"), theme_text_color="Secondary",
                          size_hint_x=None, adaptive_width=True)
        nums.add_widget(req_lbl)
        rc = self._mk_small(dp(55), self.tr("unit_pcs"), str(data.get("required_count", 10)))
        card['req_count'] = rc
        nums.add_widget(rc)
        frame.add_widget(nums)

        profile = self._mk_input(self.tr("cat_profile"), dp(40), data.get("profile_title", ""))
        card['profile'] = profile
        frame.add_widget(profile)

        del_btn = MDButton(
            MDButtonText(
                text=self.tr("btn_delete"),
                text_color=(0.937, 0.267, 0.267, 1),
            ),
            size_hint_x=None,
            width=dp(90),
            height=dp(32),
            md_bg_color=(0, 0, 0, 0),
        )
        def _delete(*_):
            if card in self._category_cards:
                self._category_cards.remove(card)
            box.remove_widget(frame)
        del_btn.bind(on_release=_delete)
        frame.add_widget(del_btn)

        box.add_widget(frame)
        self._category_cards.append(card)

    def _add_url_row(self, container, card, url=""):
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8),
                          padding=[0, dp(3)])
        row.add_widget(MDLabel(text=">", theme_text_color="Secondary",
                                size_hint_x=None, width=dp(16)))
        inp = self._mk_input("URL", dp(48), url)
        row.add_widget(inp)
        del_btn = MDIconButton(icon="close", user_font_size=dp(14), theme_text_color="Custom",
                               text_color=self.c_muted, size_hint=(None, None), size=(dp(24), dp(24)))
        def _remove(*_):
            container.remove_widget(row)
            card['url_rows'] = [r for r in card['url_rows'] if r['input'] != inp]
        del_btn.bind(on_release=_remove)
        row.add_widget(del_btn)
        card['url_rows'].append({'input': inp, 'row': row})
        container.add_widget(row)

    def add_category(self):
        self._add_category_card()

    # ─── Advanced toggle ───────────────────────────────────────
    def _adv_idx(self):
        """Индекс для вставки adv_container (сразу после adv_btn)."""
        parent = self.root.ids.main_content
        for i, child in enumerate(parent.children):
            if child == self.root.ids.adv_btn:
                return i
        return 0

    def toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        c = self.root.ids.adv_container
        btn = self.root.ids.adv_btn
        parent = self.root.ids.main_content

        if self.advanced_open:
            # Вставляем перед adv_btn
            idx = self._adv_idx()
            if c.parent is None:
                parent.add_widget(c, idx)
            c.height = 0
            c.opacity = 0
            # Сначала даём layout пересчитать minimum_height
            Clock.schedule_once(lambda dt: self._expand_adv(c), 0.02)
        else:
            anim = Animation(opacity=0, d=0.2)
            anim.bind(on_complete=lambda *_: self._collapse_adv(c))
            anim.start(c)

    def _expand_adv(self, c):
        c.height = c.minimum_height
        Animation(opacity=1, d=0.2).start(c)

    def _collapse_adv(self, c):
        c.height = 0
        c.opacity = 0
        # Убираем из дерева чтобы не мешал кликам
        if c.parent is not None:
            c.parent.remove_widget(c)

    # ─── Лог ───────────────────────────────────────────────────
    def clear_log(self):
        self.root.ids.log_label.text = ""

    def _scroll_to_bottom(self, *args):
        """Прокрутить журнал событий вниз."""
        scroll = self.root.ids.log_scroll
        if scroll and scroll.height > 0:
            scroll.scroll_y = 0

    def _log(self, message: str, tag: str = "info"):
        # Заменяем эмодзи на ASCII — SDL2 шрифт их не поддерживает
        message = message.replace("✓", "+").replace("✗", "!").replace("✘", "!")
        message = message.replace("~", "~")
        icons = {"success": "+", "warning": "~", "error": "!", "info": "i", "title": ">"}
        icon = icons.get(tag, "i")
        lbl = self.root.ids.log_label
        lbl.text = f"{lbl.text}\n{icon} {message}" if lbl.text else f"{icon} {message}"
        # Ограничиваем количество строк, чтобы не перегружать UI
        lines = lbl.text.split("\n")
        if len(lines) > 200:
            lbl.text = "\n".join(lines[-200:])
        Clock.schedule_once(self._scroll_to_bottom, 0.05)

    def _threadsafe_log(self, msg: str, tag: str = "info"):
        Clock.schedule_once(lambda *_: self._log(msg, tag), 0)

    # ─── Прогресс ──────────────────────────────────────────────
    def _set_progress(self, value: float):
        """Устанавливает прогресс (0-100 конвертируется в 0-1)."""
        self.root.ids.progress.value = max(0, min(1.0, value / 100.0))

    def update_progress(self, current, total, suitable=0, required=0):
        """Обновляет текст и полосу прогресса. Должен вызываться из главного потока."""
        if required > 0:
            pct = min(suitable / required, 1.0)
            self.root.ids.progress_label.text = f"{suitable}/{required} ({int(pct*100)}%)"
        elif total > 0:
            pct = current / total
            self.root.ids.progress_label.text = f"{int(pct*100)}%"
        else:
            pct = 0
        self._set_progress(pct * 100)

    def _threadsafe_progress(self, current, total, suitable=0, required=0):
        """Потокобезопасная обертка для update_progress."""
        Clock.schedule_once(lambda *_: self.update_progress(current, total, suitable, required), 0)

    # ─── Кнопки ────────────────────────────────────────────────
    def _enable_control_buttons(self, running: bool):
        stop = self.root.ids.stop_btn
        skip = self.root.ids.skip_btn

        def _set_btn_state(btn, enabled, fg_color, bg_color):
            btn.disabled = not enabled
            btn.md_bg_color = bg_color
            for c in btn.children:
                if isinstance(c, MDButtonText):
                    c.text_color = fg_color
                    break

        if running:
            _set_btn_state(stop, True, _hex_to_rgba(RED, 1.0), _hex_to_rgba(RED, 0.2))
            _set_btn_state(skip, True, _hex_to_rgba(YELLOW, 1.0), _hex_to_rgba(YELLOW, 0.2))
        else:
            _set_btn_state(stop, False, self.c_muted, (0, 0, 0, 0))
            _set_btn_state(skip, False, self.c_muted, (0, 0, 0, 0))
        self.root.ids.start_btn.disabled = running

    # ─── Скачивание ────────────────────────────────────────────
    def start_download(self):
        if self._is_running:
            self._toast(self.tr("msg_op_running"))
            return
        self._is_running = True
        self._stop_event.clear()
        self._enable_control_buttons(True)
        self.root.ids.progress_label.text = self.tr("status_downloading")
        self._set_progress(0)
        self._log(self.tr("status_downloading"), "title")

        def worker():
            try:
                results = download_all_tasks(self.tasks, max_age_hours=24, force=False, log_func=self._threadsafe_log)
                d, s, f = len(results.get('downloaded',[])), len(results.get('skipped',[])), len(results.get('failed',[]))
                if d:
                    self._threadsafe_log(f"{self.tr('btn_download')}: {d}", "success")
                if s:
                    self._threadsafe_log(f"{self.tr('btn_skip')}: {s}")
                if f:
                    self._threadsafe_log(f"{self.tr('status_fail')}: {f}", "error")
            except Exception as e:
                self._threadsafe_log(str(e), "error")
            finally:
                Clock.schedule_once(lambda *_: self._finish_op(), 0)

        threading.Thread(target=worker, daemon=True).start()

    # ─── Тест ──────────────────────────────────────────────────
    def start_full_test(self):
        if self._is_running:
            self._toast(self.tr("msg_op_running"))
            return
        sel = [d['task'] for d in self._task_checks.values() if d['check'].active]
        if not sel:
            self._toast(self.tr("msg_no_tasks"))
            return
        self._is_running = True
        self._stop_event.clear()
        self._enable_control_buttons(True)
        self._set_progress(0)
        self.root.ids.progress_label.text = self.tr("msg_test_started")
        self._log(f"{self.tr('msg_test_started')} {len(sel)}", "title")

        def background_task():
            task_names = []
            
            # Предварительная проверка актуальности конфигов
            self._threadsafe_log(self.tr("msg_checking_configs"), "info")
            try:
                # Скачиваем только выбранные задачи
                download_all_tasks(sel, max_age_hours=24, force=False, log_func=self._threadsafe_log)
            except Exception as e:
                self._threadsafe_log(f"Error: {e}", "error")

            # Проверка и установка Xray
            self._threadsafe_log(self.tr("msg_checking_xray"), "info")
            xray_path = XRAY_BIN # По умолчанию
            try:
                actual_xray = ensure_xray(log_func=self._threadsafe_log)
                if actual_xray:
                    xray_path = actual_xray
                else:
                    self._threadsafe_log("Xray not found.", "warning")
            except Exception as e:
                self._threadsafe_log(f"Xray Error: {e}", "error")

            for i, t in enumerate(sel, 1):
                if self._stop_event.is_set():
                    break
                self._skip_event.clear()
                task_names.append(t['name'])
                Clock.schedule_once(lambda *_v, name=t['name']: setattr(
                    self.root.ids.progress_label, 'text', f"{self.tr('msg_testing')} {name}"), 0)
                self._threadsafe_log(f"[{i}/{len(sel)}] {t['name']}")
                self._test_task(t, xray_path=xray_path)
                Clock.schedule_once(lambda *_v, p=(i/len(sel))*100: self._set_progress(p), 0)
            
            # Объединяем VPN конфиги если тестировали Xray задачи
            xray_task_names = {tk['name'] for tk in self.tasks if tk.get('type') == 'xray'}
            if any(n in xray_task_names for n in task_names):
                Clock.schedule_once(lambda *_: self.merge_vpn_configs(), 0)
            
            Clock.schedule_once(lambda *_: self._finish_op(tested_tasks=task_names), 0)

        threading.Thread(target=background_task, daemon=True).start()

    def _test_task(self, task, xray_path=None):
        if task["type"] == "xray":
            configs = []
            for fpath in task.get("raw_files", []):
                if os.path.exists(fpath):
                    configs.extend(read_configs_from_file(fpath))
            if not configs:
                self._threadsafe_log(f"{task['name']}: no configs", "warning")
                return
                
            # Используем переданный путь или глобальный дефолт
            current_xray = xray_path or XRAY_BIN
            
            w, p, f = test_xray_configs(
                configs=configs, target_url=task["target_url"],
                max_ping_ms=task["max_ping_ms"], required_count=task["required_count"],
                xray_path=current_xray, out_file=task["out_file"],
                profile_title=task.get("profile_title"), config_type=task.get("name"),
                log_func=self._threadsafe_log, progress_func=self._threadsafe_progress,
                stop_flag=self._stop_event, skip_flag=self._skip_event)
            self._threadsafe_log(f"{task['name']}: ok={w}, pass={p}, fail={f}", "success" if p > 0 else "warning")
        else:
            configs = []
            for fpath in task.get("raw_files", []):
                if os.path.exists(fpath):
                    configs.extend(read_mtproto_from_file(fpath))
            if not configs:
                self._threadsafe_log(f"{task['name']}: no configs", "warning")
                return
            w, p, f = test_mtproto_configs(
                configs=configs, max_ping_ms=task["max_ping_ms"],
                required_count=task["required_count"], max_workers=30,
                out_file=task["out_file"],
                profile_title=task.get("profile_title"), config_type=task.get("name"),
                log_func=self._threadsafe_log,
                progress_func=lambda c, t: self._threadsafe_progress(c, t, 0, 0),
                stop_flag=self._stop_event, skip_flag=self._skip_event)
            self._threadsafe_log(f"{task['name']}: ok={w}, pass={p}, fail={f}", "success" if p > 0 else "warning")

    def skip_file(self):
        self._skip_event.set()
        self._log(self.tr("btn_skip"), "warning")

    def stop_operation(self):
        self._stop_event.set()
        self._log(self.tr("btn_stop"), "warning")

    # ─── Подписка на сервер ────────────────────────────────────
    def _upload_subscription(self, tested_tasks=None, proxy_attempt_index=0, skip_direct=False, proxy_candidates=None):
        """Отправляет на сервер результаты протестированных задач."""
        if not auth_module.is_logged_in():
            return
        
        # Блокировка повторных вызовов
        if self._uploading and not skip_direct and proxy_attempt_index == 0:
            print("[DEBUG] Subscription upload already in progress, skipping duplicate call")
            return
        
        if not skip_direct and proxy_attempt_index == 0:
            self._uploading = True

        all_task_names = [t['name'] for t in self.tasks]
        if tested_tasks is None:
            tested_tasks = all_task_names

        def _ask_retry(next_proxy_index=0, last_error="", current_proxies=None):
            """Показывает диалог при сетевой неудаче."""
            self._uploading = False # Разблокируем для ручного повтора
            try:
                from kivymd.uix.dialog import (
                    MDDialog,
                    MDDialogHeadlineText,
                    MDDialogSupportingText,
                    MDDialogButtonContainer,
                )
                from kivymd.uix.button import MDButton, MDButtonText

                proxies = current_proxies or []
                has_more_proxy_configs = next_proxy_index < len(proxies)
                next_proxy_label = ""
                if has_more_proxy_configs:
                    next_proxy_label = f"{next_proxy_index + 1} / {len(proxies)}"

                def _on_retry(*_):
                    dlg.dismiss()
                    if has_more_proxy_configs:
                        self._upload_subscription(
                            tested_tasks=tested_tasks,
                            proxy_attempt_index=next_proxy_index,
                            skip_direct=True,
                            proxy_candidates=proxies,
                        )
                    else:
                        self._upload_subscription(tested_tasks=tested_tasks)

                def _on_cancel(*_):
                    dlg.dismiss()

                base_text = self.tr("msg_upload_failed")
                if has_more_proxy_configs:
                    base_text += " " + self.tr("msg_upload_retry_proxy", label=next_proxy_label)
                else:
                    base_text += " " + self.tr("msg_upload_retry_direct")
                if last_error:
                    base_text += f"\n\n{self.tr('msg_last_error')} {last_error}"

                dlg = MDDialog(
                    MDDialogHeadlineText(text=self.tr("subscription")),
                    MDDialogSupportingText(text=base_text),
                    MDDialogButtonContainer(
                        MDButton(MDButtonText(text=self.tr("btn_no")), on_release=_on_cancel),
                        MDButton(
                            MDButtonText(
                                text=f"{self.tr('btn_config')} {next_proxy_label}" if has_more_proxy_configs else self.tr("btn_retry")
                            ),
                            on_release=_on_retry,
                            md_bg_color=self.c_accent,
                        ),
                        spacing="4dp",
                    ),
                    auto_dismiss=False,
                )
                dlg.open()
            except Exception:
                self._toast(self.tr("msg_auth_error"))

        def up():
            def _log_success(updated_names, via_proxy=False):
                self._uploading = False
                msg = f"{self.tr('msg_upload_done')}: {', '.join(updated_names)}"
                Clock.schedule_once(lambda *_: self._log(msg, "success"), 0)
                Clock.schedule_once(lambda *_: self._toast(self.tr("msg_upload_done")), 0)

            try:
                # Читаем файлы в фоновом потоке
                has_vpn_results = any(tk['name'] in tested_tasks and tk['type'] == 'xray' for tk in self.tasks)
                has_mtproto_results = any(tk['name'] in tested_tasks and tk['type'] == 'mtproto' for tk in self.tasks)

                vpn_content = ""
                mt_content = ""
                
                if has_vpn_results:
                    vpn_file = os.path.join(RESULTS_DIR, "all_top_vpn.txt")
                    if os.path.exists(vpn_file):
                        with open(vpn_file, 'r', encoding='utf-8') as f:
                            vpn_content = f.read().strip()
                    else:
                        Clock.schedule_once(lambda *_: self._log(self.tr("msg_checking_configs"), "warning"), 0)
                
                if has_mtproto_results:
                    mt_tasks = [tk for tk in self.tasks if tk['type'] == 'mtproto']
                    if mt_tasks:
                        mt_file = mt_tasks[0]['out_file']
                        if os.path.exists(mt_file):
                            with open(mt_file, 'r', encoding='utf-8') as f:
                                mt_content = f.read().strip()
                    else:
                        Clock.schedule_once(lambda *_: self._log(self.tr("msg_checking_configs"), "warning"), 0)

                if not vpn_content and not mt_content:
                    self._uploading = False
                    Clock.schedule_once(lambda *_: self._toast(self.tr("msg_no_results_upload")), 0)
                    return

                # Получаем прокси для обхода блокировок
                local_proxy_candidates = proxy_candidates
                if local_proxy_candidates is None:
                    local_proxy_candidates = []
                    vpn_file = os.path.join(RESULTS_DIR, "all_top_vpn.txt")
                    if os.path.exists(vpn_file):
                        all_proxy_candidates = read_configs_from_file(vpn_file)
                        secure_proxy_candidates = [cfg for cfg in all_proxy_candidates if not has_insecure_setting(cfg)]
                        local_proxy_candidates = secure_proxy_candidates or all_proxy_candidates

                if not skip_direct:
                    updated = []
                    if vpn_content:
                        auth_module.update_subscription(vpn_content)
                        updated.append("VPN")
                    if mt_content:
                        auth_module.update_mtproto(mt_content)
                        updated.append("MTProto")
                    _log_success(updated)
                    return

                if proxy_attempt_index >= len(local_proxy_candidates):
                    raise auth_module.AuthError("No more proxies")

                actual_xray = ensure_xray(log_func=self._threadsafe_log)
                if not actual_xray:
                    raise auth_module.AuthError("Xray not found")

                proxy_config = local_proxy_candidates[proxy_attempt_index]
                label = f"{proxy_attempt_index+1}/{len(local_proxy_candidates)}"
                Clock.schedule_once(lambda *_: self._log(self.tr("msg_upload_proxy_try", label=label), "warning"), 0)
                
                updated = auth_module.push_updates_via_xray_proxy(
                    proxy_config=proxy_config,
                    xray_path=actual_xray,
                    vpn_content=vpn_content,
                    mtproto_content=mt_content,
                )
                _log_success(updated, via_proxy=True)
            except Exception as exc:
                err_msg = str(exc)
                Clock.schedule_once(lambda *_: self._log(f"Upload Error: {err_msg}", "error"), 0)
                next_proxy_index = proxy_attempt_index + 1 if skip_direct else 0
                # Пытаемся передать прокси дальше
                Clock.schedule_once(lambda *_: _ask_retry(next_proxy_index, err_msg, local_proxy_candidates), 0)

        threading.Thread(target=up, daemon=True).start()

    def _ask_update_sub_or_open_folder(self, tested_tasks=None):
        """После теста спрашивает: обновить подписку (или GitHub для admin)."""
        session = auth_module.get_session()
        username = session.get("username") if session else None
        is_admin = (username == "admin")

        if not auth_module.is_logged_in():
            self.open_results()
            return

        try:
            from kivymd.uix.dialog import (
                MDDialog,
                MDDialogHeadlineText,
                MDDialogSupportingText,
                MDDialogButtonContainer,
            )
            from kivymd.uix.button import MDButton, MDButtonText

            def _on_yes(instance, *_):
                instance.disabled = True
                dlg.dismiss()
                if is_admin:
                    self._push_to_github()
                else:
                    self._upload_subscription(tested_tasks=tested_tasks)

            def _on_no(*_):
                dlg.dismiss()
                self.open_results()

            headline = self.tr("dialog_github") if is_admin else self.tr("dialog_update_sub")
            supporting = self.tr("dialog_github_text") if is_admin else self.tr("dialog_update_sub_text")

            dlg = MDDialog(
                MDDialogHeadlineText(text=headline),
                MDDialogSupportingText(text=supporting),
                MDDialogButtonContainer(
                    MDButton(MDButtonText(text=self.tr("btn_no")), on_release=_on_no),
                    MDButton(MDButtonText(text=self.tr("btn_yes")), on_release=_on_yes, md_bg_color=self.c_accent),
                    spacing="4dp",
                ),
                auto_dismiss=False,
            )
            dlg.open()
        except Exception:
            self.open_results()

    def merge_vpn_configs(self):
        """Объединяет все Xray-результаты в all_top_vpn.txt с дедупликацией по ID."""
        try:
            out_file = os.path.join(RESULTS_DIR, "all_top_vpn.txt")
            self._threadsafe_log(self.tr("msg_merging"), "info")
            
            # 1. Читаем старый файл, если он есть, для сохранения данных
            current_sections = {}
            seen_ids = set() # Для глобальной дедупликации
            
            if os.path.exists(out_file):
                with open(out_file, 'r', encoding='utf-8') as f:
                    current_section = "General"
                    for line in f:
                        line = line.strip()
                        if line.startswith("# SECTION:"):
                            current_section = line.replace("# SECTION:", "").strip()
                            current_sections.setdefault(current_section, [])
                        elif line and not line.startswith('#'):
                            cfg_id = get_config_id(line)
                            if cfg_id and cfg_id not in seen_ids:
                                seen_ids.add(cfg_id)
                                current_sections.setdefault(current_section, []).append(line)

            # 2. Собираем все доступные Xray задачи из настроек
            xray_tasks = [t for t in self.tasks if t.get('type') == 'xray']
            updated_sections = {}
            ordered_names = [t['name'] for t in xray_tasks]
            
            for task in xray_tasks:
                name = task['name']
                fp = task.get('out_file')
                if fp and os.path.exists(fp):
                    with open(fp, 'r', encoding='utf-8') as f:
                        cfgs = []
                        for l in f:
                            l = l.strip()
                            if l and not l.startswith('#'):
                                cfgs.append(l)
                    
                    if cfgs:
                        updated_sections[name] = cfgs
                    else:
                        self._log(f"WRN: {name} empty", "warning")
            
            # 3. Обновляем секции
            final_sections = {}
            final_seen_ids = set()
            
            all_section_names = list(ordered_names)
            for old_name in current_sections.keys():
                if old_name not in all_section_names and old_name != "General":
                    all_section_names.append(old_name)

            for name in all_section_names:
                source = updated_sections.get(name) or current_sections.get(name)
                if source:
                    final_sections[name] = []
                    for cfg in source:
                        cid = get_config_id(cfg)
                        if cid and cid not in final_seen_ids:
                            final_seen_ids.add(cid)
                            final_sections[name].append(cfg)

            # 4. Записываем файл
            with open(out_file, 'w', encoding='utf-8') as f:
                f.write("#profile-update-interval: 48\n")
                f.write("#support-url: https://t.me/arqhub\n\n")
                
                for name in all_section_names:
                    if name in final_sections and final_sections[name]:
                        f.write(f"\n# SECTION: {name}\n")
                        for c in final_sections[name]:
                            f.write(f"{c}\n")
            
            self._threadsafe_log(self.tr("msg_merge_done"), "success")
        except Exception as e:
            self._log(f"Merge error: {e}", "error")

    def _finish_op(self, tested_tasks=None):
        self._is_running = False
        self._enable_control_buttons(False)
        self._set_progress(100)
        self.root.ids.progress_label.text = self.tr("ready")
        self._log(self.tr("ready"), "success")
        self._toast(self.tr("ready"))
        if tested_tasks:
            Clock.schedule_once(lambda *_: self._ask_update_sub_or_open_folder(tested_tasks=tested_tasks), 0.5)

    # ─── Утилиты ───────────────────────────────────────────────
    def _push_to_github(self):
        """Админ-функция: отправка результатов в Git-репозиторий."""
        if platform == "android":
            self._toast(self.tr("msg_android_not_supported"))
            return

        import subprocess
        from datetime import datetime

        def push_worker():
            try:
                self._threadsafe_log(self.tr("status_uploading"), "info")

                # Корень проекта (на один уровень выше пакета arqparse)                project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                
                # 1. git add
                subprocess.run(["git", "add", RESULTS_DIR], cwd=project_dir, check=True)
                
                # 2. git commit
                commit_msg = f"Update VPN configs - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                commit_res = subprocess.run(["git", "commit", "-m", commit_msg], cwd=project_dir, capture_output=True, text=True)

                if commit_res.returncode != 0:
                    # Если нечего коммитить, git возвращает 1. Проверим, вдруг это реальная ошибка.
                    if "nothing to commit" in commit_res.stdout or "nothing to commit" in commit_res.stderr:
                        self._threadsafe_log(self.tr("msg_no_results_upload"), "info")
                        return
                    else:
                        self._threadsafe_log(f"Commit Error: {commit_res.stderr}", "error")
                        return

                # 3. git push
                res = subprocess.run(["git", "push"], cwd=project_dir, capture_output=True, text=True)                
                if res.returncode == 0:
                    self._threadsafe_log(self.tr("cli_success"), "success")
                    Clock.schedule_once(lambda *_: self._toast(self.tr("cli_success")), 0)
                else:
                    self._threadsafe_log(f"Git Error: {res.stderr}", "error")
                    Clock.schedule_once(lambda *_: self._toast(f"Git Error: {res.stderr[:50]}..."), 0)
            except Exception as e:
                self._threadsafe_log(f"System Error: {e}", "error")
                Clock.schedule_once(lambda *_: self._toast(f"System Error: {str(e)[:50]}..."), 0)

        threading.Thread(target=push_worker, daemon=True).start()

    def open_results(self):
        if platform == "android":
            return
        import subprocess
        import sys
        if not os.path.exists(RESULTS_DIR):
            self._toast(self.tr("msg_sub_no_url"))
            return
        if sys.platform == "win32":
            os.startfile(RESULTS_DIR)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", RESULTS_DIR])
        else:
            subprocess.Popen(["xdg-open", RESULTS_DIR])

    def logout(self):
        auth_module.clear_session()
        self.user_login = self.tr("msg_guest")
        self.switch_screen("login")
        self._toast(self.tr("msg_logged_out"))

    def _toast(self, text: str):
        try:
            from kivymd.uix.snackbar import MDSnackbar, MDSnackbarSupportingText
            sb = MDSnackbar(
                MDSnackbarSupportingText(
                    text=text,
                    theme_text_color="Custom",
                    text_color="#e4e4e7",
                ),
                y=0,
                pos_hint={"center_x": 0.5},
                size_hint_x=1.0,
            )
            sb.md_bg_color = [0.18, 0.18, 0.22, 1]
            sb.open()
        except Exception:
            pass

    def _show_toast(self, text: str):
        """Показывает toast в главном потоке (алиас для _toast)."""
        self._toast(text)


def main():
    KivyGUIApp().run()


if __name__ == "__main__":
    main()
