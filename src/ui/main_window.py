import os
import sys
import csv
import json
import difflib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Any
from urllib.error import HTTPError, URLError
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QFileDialog, QTableWidget,
                               QTableWidgetItem, QHeaderView, QProgressBar,
                               QLabel, QTabWidget, QTextEdit, QCheckBox,
                               QSplitter, QLineEdit, QMenu, QInputDialog, QMessageBox,
                               QScrollArea, QApplication)
from PySide6.QtGui import QAction, QColor, QCursor, QFont, QFontDatabase, QIcon
from PySide6.QtCore import Qt, QSettings, QTimer
from sqlmodel import select, col
from services.resource_service import ResourceLoader
from core.parser import FoundryParser
from core.engine import TranslationEngine
from core.masker import Masker
from ui.worker import TranslationWorker
from ui.settings_tab import SettingsTab
from ui.editor_panel import EditorPanel
from ui.integrity_tab import IntegrityTab
from ui.login_dialog import LoginDialog
from services.llm_service import LLMService
from services.provider_http_client import ProviderHttpClient
from services.token_storage import TokenStorage
from services.plugin_sync_service import GitHubPluginSyncService
from core.i18n import I18N
from core.tag_utils import extract_tags, strip_tags
from core.database import (save_translation, get_cached_record,
                           Session, TranslationRecord, engine,
                           find_translation_conflicts, get_project_integrity_report,
                           normalize_project_term)
from core.parser import TranslationSegment
from services.plugin_loader import PluginRegistry

TAG_ERROR_PREFIX = "[TAG ERROR]"
TAG_ERROR_PREFIX_WITH_SPACE = f"{TAG_ERROR_PREFIX} "
METRICS_SECTION_STYLE = "font-weight: bold; margin-top: 8px;"
METRICS_MONO_STYLE = "font-family: 'Consolas', 'Courier New';"
METRICS_MONO_BOLD_STYLE = f"{METRICS_MONO_STYLE} font-weight: bold;"


@dataclass
class BatchMetrics:
    started_at: float | None = None
    processed_rows: int = 0
    duration_seconds: float | None = None
    avg_seconds: float | None = None
    model_name: str | None = None


class FoundryGUI(QMainWindow):
    def __init__(self, plugin_registry: Optional['PluginRegistry'] = None):
        super().__init__()
        self.setWindowTitle(f"FoundryL10n - {I18N.t('ui_workstation')}")
        self.plugin_registry = plugin_registry
        self.segments = []
        self.current_row = -1
        self.input_path = Path()
        self._file_loaded = False
        self._context_menu_indices = []
        self._context_menu_row = None
        self._context_menu_count = 0
        self._history_menu_item = None
        self._active_provider_id = ""
        self._tsv_parser = FoundryParser()
        self.llm_service = LLMService()
        self.token_storage = TokenStorage()
        self._login_dialog: LoginDialog | None = None
        self._remote_change_ready = False
        self._remote_change_map: dict[str, dict[str, str]] = {}
        self.llm_request_count = 0
        self.llm_failure_count = 0
        self._batch_metrics = BatchMetrics()

        # Icon
        # --- ICON LOADING LOGIC ---
        if getattr(sys, 'frozen', False):
            # If running as EXE, resources are in the temp folder
            res_base = Path(getattr(sys, '_MEIPASS')) / "resources"
        else:
            # If running in Dev mode (src is current, resources is two levels up)
            res_base = Path(__file__).parent.parent.parent / "resources"

        icon_path = res_base / "icon_256.png"

        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Main Layout: Tabs
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        self.setMinimumSize(800, 600)
        self._init_actions()
        self._init_sync_controls()

        self.init_translate_tab()

        self.settings_tab = SettingsTab(plugin_registry=self.plugin_registry)
        self.settings_tab.font_changed.connect(self.apply_font_size)
        self.settings_tab.profile_loaded.connect(
            self.on_profile_loaded_profile)
        if hasattr(self.settings_tab, "language_changed"):
            self.settings_tab.language_changed.connect(self.retranslate_ui)
        if hasattr(self.settings_tab, "provider_changed"):
            self.settings_tab.provider_changed.connect(self.on_provider_changed)
        if hasattr(self.settings_tab, "login_requested"):
            self.settings_tab.login_requested.connect(self.open_login_dialog)
        if hasattr(self.settings_tab, "llm_status_warning"):
            self.settings_tab.llm_status_warning.connect(
                self.on_llm_status_warning
            )
        self.tabs.currentChanged.connect(self.on_tab_changed)

        self.tabs.addTab(self.settings_tab, I18N.t("tab_settings"))


        # Connect editor actions
        self.editor.btn_translate_now.clicked.connect(
            self.translate_current_row)
        self.editor.btn_rollback.clicked.connect(self.rollback_to_ai)

        self._current_fuzzy_text = ""
        self.editor.btn_use_fuzzy.clicked.connect(self.on_use_fuzzy_clicked)
        self.editor.btn_use_history.clicked.connect(self.on_use_history_clicked)

        # Integrity Tab
        self.integrity_tab = IntegrityTab()
        self.integrity_tab.btn_refresh.clicked.connect(self.run_integrity_scan)
        self.tabs.addTab(self.integrity_tab, I18N.t("tab_integrity"))
        self.integrity_tab.btn_auto_normalize.clicked.connect(
            self.run_auto_normalize)
        self.init_metrics_tab()
        self.tabs.addTab(self.metrics_tab, I18N.t("tab_metrics"))

        # Load states
        self.load_ui_state()
        self.settings_tab.load_settings()
        self.on_provider_changed(self.settings_tab.get_settings().get("provider_id", ""))
        self.retranslate_ui()

    def init_translate_tab(self):
        self.translate_tab = QWidget()
        layout = QVBoxLayout(self.translate_tab)

        # --- TOP CONTROL BAR ---
        top_bar = QHBoxLayout()
        self.btn_open = QPushButton(I18N.t("btn_import_tsv"))
        self.btn_open.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_open.clicked.connect(self.request_tsv_import)

        self.btn_export_tsv = QPushButton(I18N.t("btn_export_tsv"))
        self.btn_export_tsv.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_export_tsv.setEnabled(False)
        self.btn_export_tsv.clicked.connect(self.request_tsv_export)

        self.file_label = QLabel(I18N.t("ui_no_file_selected"))
        self.file_label.setStyleSheet("color: #888; font-style: italic;")

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText(I18N.t("ui_search_placeholder"))
        self.search_bar.textChanged.connect(self.filter_table)

        self.cb_only_errors = QCheckBox(I18N.t("ui_show_only_errors"))
        self.cb_only_errors.toggled.connect(self.filter_table)

        self.btn_toggle_editor = QPushButton(I18N.t("btn_toggle_editor"))
        self.btn_toggle_editor.setCheckable(True)
        self.btn_toggle_editor.setChecked(True)
        self.btn_toggle_editor.clicked.connect(self.toggle_editor)

        self.btn_zen = QPushButton(I18N.t("btn_zen_mode"))
        self.btn_zen.setCheckable(True)
        self.btn_zen.clicked.connect(self.toggle_zen_mode)
        top_bar.addWidget(self.btn_zen)

        self.btn_reverse_zen = QPushButton(I18N.t("btn_reverse_zen_mode"))
        self.btn_reverse_zen.setCheckable(True)
        self.btn_reverse_zen.clicked.connect(self.toggle_reverse_zen_mode)
        top_bar.addWidget(self.btn_reverse_zen)

        top_bar.addWidget(self.btn_open)
        top_bar.addWidget(self.btn_export_tsv)
        top_bar.addWidget(self.file_label, 1)  # Give it stretch
        self.search_label = QLabel(I18N.t("ui_search_label"))
        top_bar.addWidget(self.search_label)
        top_bar.addWidget(self.search_bar)
        top_bar.addWidget(self.cb_only_errors)
        top_bar.addWidget(self.btn_toggle_editor)
        layout.addLayout(top_bar)

        # --- CENTRAL SPLITTER ---
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Table
        self.table = QTableWidget(0, 4)

        # Selection behavior
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(
            QTableWidget.SelectionMode.ExtendedSelection)

        # Headers
        self.table.setHorizontalHeaderLabels(
            [
                I18N.t("header_state"),
                I18N.t("header_key"),
                I18N.t("header_source"),
                I18N.t("ui_translation"),
            ])

        # Column resize: Excel-like (drag)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        # Fixed State column (icon only)
        self.table.setColumnWidth(0, 60)   # State + sync indicators

        # Sensible starting widths
        self.table.setColumnWidth(1, 150)  # Key
        self.table.setColumnWidth(2, 400)  # Source
        self.table.setColumnWidth(3, 400)  # Translation

        header.sectionDoubleClicked.connect(self._auto_fit_column)

        # Context menu + selection change
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemSelectionChanged.connect(self.on_row_selected)
        self.table.itemSelectionChanged.connect(self.update_selection_info)

        # Right: Editor
        self.editor = EditorPanel()
        self.editor_container = QScrollArea()
        self.editor_container.setWidgetResizable(True)
        self.editor_container.setWidget(self.editor)
        self.editor.btn_save.clicked.connect(self.save_manual_edit)
        self.editor.btn_next.clicked.connect(self.nav_next_needed)
        self.editor.btn_prev.clicked.connect(lambda: self.nav_error(-1))
        self.editor.request_next_needed.connect(self.nav_next_needed)
        self.editor.history_list.itemDoubleClicked.connect(
            self.restore_from_history_list)
        self.editor.history_list.itemSelectionChanged.connect(
            self.update_history_action_state)

        self.editor.history_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.history_list.customContextMenuRequested.connect(
            self.show_history_context_menu)

        self.splitter.addWidget(self.table)
        self.splitter.addWidget(self.editor_container)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)

        layout.addWidget(self.splitter)

        # --- BOTTOM BAR (Counters + Log) ---
        self.thought_log = QTextEdit()
        self.thought_log.setReadOnly(True)
        self.thought_log.setMaximumHeight(80)
        
        layout.addWidget(self.thought_log)

        bottom = QHBoxLayout()
        self.progress_bar = QProgressBar()

        self.cb_follow = QCheckBox(I18N.t("ui_follow"))
        self.cb_follow.setChecked(True)

        self.btn_run = QPushButton(I18N.t("ui_start_bulk"))
        self.btn_run.clicked.connect(self.handle_run_clicked)
        self.btn_run.setMinimumHeight(40)
        self.btn_run.setStyleSheet("font-weight: bold;")
        self._bulk_stopping = False

        self.lbl_stats = QLabel(
            self._format_stats_text(0, 0, 0, 0, 0, 0))

        bottom.addWidget(self.progress_bar)
        bottom.addWidget(self.cb_follow)
        bottom.addWidget(self.lbl_stats)
        bottom.addWidget(self.btn_run)
        layout.addLayout(bottom)

        self.tabs.addTab(self.translate_tab, I18N.t("ui_workstation"))
        self.table.itemChanged.connect(self.on_table_cell_edited)

    def init_metrics_tab(self):
        self.metrics_tab = QWidget()
        layout = QVBoxLayout(self.metrics_tab)
        layout.setContentsMargins(16, 16, 16, 16)

        self.metrics_header_label = QLabel(I18N.t("metrics_title"))
        self.metrics_header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.metrics_header_label)

        self.metrics_intro_label = QLabel(I18N.t("metrics_intro"))
        self.metrics_intro_label.setWordWrap(True)
        layout.addWidget(self.metrics_intro_label)

        self.metrics_stats_title = QLabel(I18N.t("metrics_qa_title"))
        self.metrics_stats_title.setStyleSheet(METRICS_SECTION_STYLE)
        layout.addWidget(self.metrics_stats_title)

        self.metrics_stats_label = QLabel()
        self.metrics_stats_label.setStyleSheet(METRICS_MONO_BOLD_STYLE)
        layout.addWidget(self.metrics_stats_label)

        self.metrics_llm_title = QLabel(I18N.t("metrics_llm_title"))
        self.metrics_llm_title.setStyleSheet(METRICS_SECTION_STYLE)
        layout.addWidget(self.metrics_llm_title)

        self.metrics_llm_label = QLabel()
        self.metrics_llm_label.setStyleSheet(METRICS_MONO_STYLE)
        layout.addWidget(self.metrics_llm_label)

        self.metrics_accuracy_title = QLabel(I18N.t("metrics_accuracy_title"))
        self.metrics_accuracy_title.setStyleSheet(METRICS_SECTION_STYLE)
        layout.addWidget(self.metrics_accuracy_title)

        self.metrics_accuracy_label = QLabel()
        self.metrics_accuracy_label.setWordWrap(True)
        layout.addWidget(self.metrics_accuracy_label)

        layout.addStretch()
        self._update_metrics_labels(0, 0, 0, 0, 0, 0, 0, 0)

    def _init_actions(self):
        self.action_verify_rows = QAction(self)
        self.action_verify_rows.triggered.connect(self._handle_bulk_verify)

        self.action_unverify_rows = QAction(self)
        self.action_unverify_rows.triggered.connect(self._handle_bulk_unverify)

        self.action_skip_rows = QAction(self)
        self.action_skip_rows.triggered.connect(self._handle_bulk_skip)

        self.action_clear_translations = QAction(self)
        self.action_clear_translations.triggered.connect(
            self._handle_clear_selected_translations)

        self.action_purge_memory = QAction(self)
        self.action_purge_memory.triggered.connect(self.remove_current_from_memory)

        self.action_generate_pseudo = QAction(self)
        self.action_generate_pseudo.triggered.connect(self.run_pseudo_batch)

        self.action_purge_record = QAction(self)
        self.action_purge_record.triggered.connect(self.remove_current_from_memory)

        self.action_copy_source = QAction(self)
        self.action_copy_source.triggered.connect(self._handle_copy_source)

        self.action_mark_verified = QAction(self)
        self.action_mark_verified.triggered.connect(self._handle_mark_verified)

        self.action_never_translate = QAction(self)
        self.action_never_translate.triggered.connect(self._handle_never_translate)

        self.action_clear_translation = QAction(self)
        self.action_clear_translation.triggered.connect(self._handle_clear_translation)

        self.action_search_replace = QAction(self)
        self.action_search_replace.triggered.connect(self.show_find_replace)

        self.action_export_verified = QAction(self)
        self.action_export_verified.triggered.connect(self.export_verified_glossary)

        self.action_history_delete = QAction(self)
        self.action_history_delete.triggered.connect(self._handle_history_delete)

        self.action_fetch_segments = QAction(self)
        self.action_fetch_segments.triggered.connect(self.handle_fetch_segments)

        self.action_submit_suggestion = QAction(self)
        self.action_submit_suggestion.triggered.connect(self.handle_submit_suggestion)

        self.action_submit_verified = QAction(self)
        self.action_submit_verified.triggered.connect(
            self.handle_submit_verified_segments
        )

        self.action_sync_plugins = QAction(self)
        self.action_sync_plugins.triggered.connect(self.handle_plugin_sync)

    def _init_sync_controls(self) -> None:
        self.sync_menu = self.menuBar().addMenu(I18N.t("menu_sync"))
        self.sync_menu.addAction(self.action_fetch_segments)
        self.sync_menu.addAction(self.action_submit_suggestion)
        self.sync_menu.addAction(self.action_submit_verified)
        self.sync_menu.addSeparator()
        self.sync_menu.addAction(self.action_sync_plugins)
        self.update_sync_action_state()

    def _update_context_menu_texts(self, count: int) -> None:
        self.action_verify_rows.setText(
            I18N.t("menu_verify_rows").format(count=count)
        )
        self.action_unverify_rows.setText(
            I18N.t("menu_unverify_rows").format(count=count)
        )
        self.action_skip_rows.setText(
            I18N.t("menu_skip_rows").format(count=count)
        )
        self.action_clear_translations.setText(
            I18N.t("menu_clear_translations").format(count=count)
        )
        self.action_purge_memory.setText(I18N.t("menu_purge_memory"))
        self.action_generate_pseudo.setText(I18N.t("menu_generate_pseudo"))
        self.action_purge_record.setText(I18N.t("menu_purge_record"))
        self.action_copy_source.setText(I18N.t("menu_copy_source"))
        self.action_mark_verified.setText(I18N.t("menu_mark_verified"))
        self.action_never_translate.setText(I18N.t("menu_never_translate"))
        self.action_clear_translation.setText(I18N.t("menu_clear_translation"))
        self.action_search_replace.setText(I18N.t("menu_search_replace"))
        self.action_export_verified.setText(I18N.t("menu_export_verified"))
        self.action_history_delete.setText(I18N.t("menu_history_delete"))

    def _handle_bulk_verify(self):
        if self._context_menu_indices:
            self.bulk_verify_selected(self._context_menu_indices)

    def _handle_bulk_unverify(self):
        if self._context_menu_indices:
            self.bulk_unverify_selected(self._context_menu_indices)

    def _handle_bulk_skip(self):
        if self._context_menu_indices:
            self.bulk_skip_selected(self._context_menu_indices)

    def _handle_clear_selected_translations(self):
        if self._context_menu_indices:
            self.clear_selected_rows()

    def _handle_copy_source(self):
        if self._context_menu_row is not None:
            self.quick_action(self._context_menu_row, "copy")

    def _handle_mark_verified(self):
        if self._context_menu_row is not None:
            self.quick_action(self._context_menu_row, "verify")

    def _handle_never_translate(self):
        if self._context_menu_row is not None:
            self.quick_action(self._context_menu_row, "skip")

    def _handle_clear_translation(self):
        if self._context_menu_row is not None:
            self.quick_action(self._context_menu_row, "clear")

    def _handle_history_delete(self):
        if not self._history_menu_item:
            return
        settings = self.settings_tab.get_settings()
        seg = self.segments[self.current_row]

        record = get_cached_record(
            seg.source_text,
            settings['lang'],
            project_name=settings.get('project_name', 'default'),
            segment_key=seg.key,
        )

        if record and record.history_json:
            try:
                h_data = json.loads(record.history_json)
                new_h = [v for v in h_data if v != self._history_menu_item.text()]

                with Session(engine) as session:
                    session.add(record)
                    record.history_json = json.dumps(new_h)
                    session.commit()

                self.on_row_selected()
            except Exception as e:
                print(f"History purge error: {e}")

    # --- LOGIC & SLOTS ---
    def on_profile_loaded_profile(self):
        if not hasattr(self, "segments"):
            return

        self.audit_database_consistency()
        self.update_stats()
        self.thought_log.append(I18N.t("log_profile_loaded"))

    def on_provider_changed(self, provider_id: str):
        is_valid = (
            self.plugin_registry
            and provider_id
            and provider_id in self.plugin_registry.providers
        )
        self._active_provider_id = provider_id if is_valid else ""
        if not is_valid:
            if self._login_dialog is not None:
                self._login_dialog.close()
            self._login_dialog = None
        self.update_sync_action_state()

    def on_llm_status_warning(self, message: str) -> None:
        if hasattr(self, "thought_log"):
            self.thought_log.append(message)

    def open_login_dialog(self, provider_id: str) -> None:
        if not self.plugin_registry or not provider_id:
            return
        provider = self.plugin_registry.providers.get(provider_id)
        if not provider:
            return
        auth_type = str(provider.get("auth", {}).get("type", "bearer")).lower()
        provider_name = provider.get("metadata", {}).get("name", provider_id)
        focused = QApplication.focusWidget()
        dialog = LoginDialog(provider_name, auth_type, parent=self)
        dialog.submitted.connect(
            lambda credentials: self._handle_login_submit(
                provider_id, provider, credentials, dialog
            )
        )
        dialog.show()
        self._login_dialog = dialog
        if focused is not None:
            QTimer.singleShot(
                0, lambda: focused.setFocus(Qt.FocusReason.OtherFocusReason)
            )

    def _handle_login_submit(
        self,
        provider_id: str,
        provider: dict[str, object],
        credentials: dict[str, str],
        dialog: LoginDialog,
    ) -> None:
        client = ProviderHttpClient(provider)
        try:
            result = client.auth_login(credentials)
        except (HTTPError, URLError, ValueError) as exc:
            dialog.set_error(
                I18N.t("msg_login_failed").format(error=str(exc))
            )
            return
        token = str(result.get("token", ""))
        if not token:
            dialog.set_error(I18N.t("msg_login_failed").format(error="Empty token"))
            return
        self.token_storage.set_token(provider_id, token)
        self.thought_log.append(
            I18N.t("log_login_success").format(provider=provider_id)
        )
        dialog.accept()
        self.update_sync_action_state()

    def update_sync_action_state(self) -> None:
        token = self._get_provider_token()
        is_enabled = bool(token)
        self.action_fetch_segments.setEnabled(is_enabled)
        self.action_submit_suggestion.setEnabled(is_enabled)
        self.action_submit_verified.setEnabled(is_enabled)
        self.action_sync_plugins.setEnabled(True)

    def _get_provider_token(self) -> str | None:
        provider_id, _ = self._get_active_provider()
        if not provider_id:
            return None
        return self.token_storage.get_token(provider_id)

    def _get_provider_and_token(self) -> tuple[str, dict, str] | None:
        provider_id, provider = self._get_active_provider()
        if not provider_id or not provider:
            return None
        token = self.token_storage.get_token(provider_id)
        if not token:
            self.thought_log.append(I18N.t("log_sync_auth_required"))
            self.update_sync_action_state()
            return None
        return provider_id, provider, token

    def _get_active_provider(self) -> tuple[str, dict] | tuple[None, None]:
        if not self.plugin_registry or not self._active_provider_id:
            return None, None
        provider = self.plugin_registry.providers.get(self._active_provider_id)
        if not provider:
            return None, None
        return self._active_provider_id, provider

    def get_project_context(self) -> dict[str, str | None]:
        provider_id, _ = self._get_active_provider()
        token = self._get_provider_token()
        is_remote = bool(provider_id and token)
        return {
            "mode": "remote-synced" if is_remote else "local-only",
            "provider_id": provider_id or None,
        }

    def _resolve_segment_id(self, seg: TranslationSegment) -> str | None:
        if hasattr(seg, "segment_id") and getattr(seg, "segment_id"):
            return str(getattr(seg, "segment_id"))
        if remote_id := getattr(seg, "remote_id", None):
            return str(remote_id)
        row = getattr(seg, "original_row", {}) or {}
        for key in ("segment_id", "remote_id", "id"):
            value = row.get(key)
            if value:
                return str(value)
        return None

    def _segment_change_key(self, seg: TranslationSegment) -> str:
        return self._resolve_segment_id(seg) or seg.key

    def _reset_remote_change_state(self) -> None:
        self._remote_change_ready = False
        self._remote_change_map = {}
        if hasattr(self, "editor"):
            self.editor.set_remote_change(None)

    def _build_local_snapshot(self) -> dict[str, dict[str, str]]:
        snapshot: dict[str, dict[str, str]] = {}
        for seg in self.segments:
            key = self._segment_change_key(seg)
            snapshot[key] = {
                "source": seg.source_text or "",
                "translation": seg.translation or "",
            }
        return snapshot

    def _detect_remote_changes(
        self,
        local_snapshot: dict[str, dict[str, str]],
        fetched_segments: list[TranslationSegment],
    ) -> dict[str, dict[str, str]]:
        settings = self.settings_tab.get_settings()
        project_name = settings.get("project_name", "default")
        target_lang = settings.get("lang", "BG")
        changes: dict[str, dict[str, str]] = {}
        for seg in fetched_segments:
            key = self._segment_change_key(seg)
            local_source = ""
            local_translation = ""
            snapshot = local_snapshot.get(key)
            if snapshot:
                local_source = snapshot.get("source", "")
                local_translation = snapshot.get("translation", "")
            else:
                record = get_cached_record(
                    seg.source_text,
                    target_lang,
                    project_name=project_name,
                    segment_key=seg.key,
                )
                if record:
                    local_source = record.source_text
                    local_translation = record.translation
            remote_source = seg.source_text or ""
            remote_translation = seg.translation or ""
            source_changed = local_source != remote_source
            translation_changed = local_translation != remote_translation
            if source_changed or translation_changed:
                changes[key] = {
                    "local_source": local_source,
                    "remote_source": remote_source,
                    "local_translation": local_translation,
                    "remote_translation": remote_translation,
                }
        return changes

    def _build_diff_text(
        self,
        local_text: str,
        remote_text: str,
        local_label: str,
        remote_label: str,
    ) -> str:
        local_lines = (local_text or "").splitlines()
        remote_lines = (remote_text or "").splitlines()
        diff_lines = list(
            difflib.unified_diff(
                local_lines,
                remote_lines,
                fromfile=local_label,
                tofile=remote_label,
                lineterm="",
            )
        )
        return "\n".join(diff_lines).strip()

    def _update_remote_change_panel(self, seg: TranslationSegment) -> None:
        if not self._remote_change_ready:
            self.editor.set_remote_change(None)
            return
        key = self._segment_change_key(seg)
        change = self._remote_change_map.get(key)
        if not change:
            self.editor.set_remote_change(None)
            return
        sections: list[str] = []
        local_source = change.get("local_source", "")
        remote_source = change.get("remote_source", "")
        if local_source != remote_source:
            source_diff = self._build_diff_text(
                local_source,
                remote_source,
                I18N.t("ui_remote_diff_local_source"),
                I18N.t("ui_remote_diff_remote_source"),
            )
            if source_diff:
                sections.append(
                    f"{I18N.t('ui_remote_diff_source_header')}\n{source_diff}"
                )
        local_translation = change.get("local_translation", "")
        remote_translation = change.get("remote_translation", "")
        if local_translation != remote_translation:
            translation_diff = self._build_diff_text(
                local_translation,
                remote_translation,
                I18N.t("ui_remote_diff_local_target"),
                I18N.t("ui_remote_diff_remote_target"),
            )
            if translation_diff:
                sections.append(
                    f"{I18N.t('ui_remote_diff_target_header')}\n{translation_diff}"
                )
        diff_text = "\n\n".join(sections).strip()
        self.editor.set_remote_change(diff_text if diff_text else None)

    def _update_provider_fields_panel(self, seg: TranslationSegment) -> None:
        if not hasattr(self.editor, "set_provider_fields"):
            return
        provider_id = (
            getattr(seg, "provider_id", None)
            or getattr(seg, "original_row", {}).get("provider_id")
            or self._active_provider_id
        )
        provider = None
        if provider_id and self.plugin_registry:
            provider = self.plugin_registry.providers.get(provider_id)
        custom_fields = []
        if isinstance(provider, dict):
            custom_fields = provider.get("custom_fields", [])
        if not isinstance(custom_fields, list):
            custom_fields = []
        field_values = getattr(seg, "original_row", {}) or {}
        if not isinstance(field_values, dict):
            field_values = {}
        self.editor.set_provider_fields(custom_fields, field_values)

    def _build_segments_from_provider(
        self,
        items: list[dict[str, object]],
        provider_id: str,
    ) -> list[TranslationSegment]:
        segments: list[TranslationSegment] = []
        for item in items:
            segment_id = item.get("segment_id") or item.get("id")
            remote_id = item.get("remote_id") or segment_id
            source_text = str(item.get("source") or "")
            translation = item.get("target") or ""
            ai_draft = item.get("local_draft") or ""
            last_sync = self._resolve_remote_sync_timestamp(item)
            key = str(segment_id) if segment_id else source_text[:40] or "remote"
            seg = TranslationSegment(
                key=key,
                source_text=str(source_text),
                translation=str(translation),
                ai_draft=str(ai_draft),
                original_row={
                    "segment_id": segment_id,
                    "provider_id": provider_id,
                    "remote_id": remote_id,
                    "last_sync": last_sync,
                },
                provider_id=provider_id,
                remote_id=str(remote_id) if remote_id is not None else None,
                last_sync=last_sync,
            )
            segments.append(seg)
        return segments

    def _load_segments_into_table(self, segments: list[TranslationSegment]) -> None:
        self.segments = segments
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)
        try:
            self.table.setRowCount(len(self.segments))
            for i, seg in enumerate(self.segments):
                self.table.setItem(i, 0, QTableWidgetItem("⚪"))
                self.table.setItem(i, 1, QTableWidgetItem(seg.key))
                self.table.setItem(i, 2, QTableWidgetItem(seg.source_text))
                self.table.setItem(i, 3, QTableWidgetItem(seg.translation))
                self.update_row_visuals(i)
        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)
        self.progress_bar.setMaximum(len(self.segments))
        self.progress_bar.setValue(0)
        self.update_stats()

    def handle_fetch_segments(self) -> None:
        resolved = self._get_provider_and_token()
        if resolved is None:
            return
        provider_id, provider, token = resolved
        settings = self.settings_tab.get_settings()
        project_id = settings.get("project_name") or None
        page = int(settings.get("sync_page", 1))
        local_snapshot = self._build_local_snapshot()
        client = ProviderHttpClient(provider)
        try:
            segments = client.fetch_segments(token, project_id=project_id, page=page)
        except (HTTPError, URLError, ValueError) as exc:
            self.thought_log.append(
                I18N.t("log_sync_fetch_failed").format(error=str(exc))
            )
            return
        self._file_loaded = True
        self.file_label.setText(I18N.t("ui_remote_segments_loaded"))
        new_segments = self._build_segments_from_provider(segments, provider_id)
        self._remote_change_map = self._detect_remote_changes(
            local_snapshot, new_segments
        )
        self._remote_change_ready = True
        for seg in new_segments:
            seg.remote_changed = self._segment_change_key(seg) in self._remote_change_map
        self._load_segments_into_table(new_segments)
        self.thought_log.append(
            I18N.t("log_sync_fetch_success").format(count=len(segments))
        )
        if self._remote_change_map:
            self.thought_log.append(
                I18N.t("log_sync_remote_changes").format(
                    count=len(self._remote_change_map)
                )
            )

    def handle_submit_suggestion(self) -> None:
        resolved = self._get_provider_and_token()
        if resolved is None:
            return
        _, provider, token = resolved
        if self.current_row < 0 or self.current_row >= len(self.segments):
            self.thought_log.append(I18N.t("log_sync_no_selection"))
            return
        seg = self.segments[self.current_row]
        segment_id = self._resolve_segment_id(seg)
        if not segment_id:
            self.thought_log.append(I18N.t("log_sync_missing_segment_id"))
            return
        suggestion_text = seg.translation or ""
        client = ProviderHttpClient(provider)
        try:
            client.submit_suggestion(
                token,
                segment_id=segment_id,
                suggestion_text=suggestion_text,
            )
        except (HTTPError, URLError, ValueError) as exc:
            self.thought_log.append(
                I18N.t("log_sync_submit_failed").format(error=str(exc))
            )
            return
        self.thought_log.append(I18N.t("log_sync_submit_success"))

    def handle_submit_verified_segments(self) -> None:
        resolved = self._get_provider_and_token()
        if resolved is None:
            return
        _, provider, token = resolved
        verified_segments = [
            seg for seg in self.segments if getattr(seg, "is_verified", False)
        ]
        if not verified_segments:
            self.thought_log.append(I18N.t("log_sync_submit_all_none"))
            return
        client = ProviderHttpClient(provider)
        submitted = 0
        skipped = 0
        for seg in verified_segments:
            segment_id = self._resolve_segment_id(seg)
            if not segment_id:
                skipped += 1
                continue
            suggestion_text = seg.translation or ""
            try:
                client.submit_suggestion(
                    token,
                    segment_id=segment_id,
                    suggestion_text=suggestion_text,
                )
                submitted += 1
            except (HTTPError, URLError, ValueError) as exc:
                self.thought_log.append(
                    I18N.t("log_sync_submit_failed").format(error=f"Segment '{seg.key}': {exc}")
                )
        self.thought_log.append(
            I18N.t("log_sync_submit_all_success").format(
                count=submitted, skipped=skipped
            )
        )

    def handle_plugin_sync(self) -> None:
        service = GitHubPluginSyncService()
        result = service.sync_plugins()
        for error in result.errors:
            self.thought_log.append(
                I18N.t("log_plugin_sync_error").format(error=error)
            )
        if result.conflicts:
            self.thought_log.append(
                I18N.t("log_plugin_sync_conflicts").format(
                    count=len(result.conflicts)
                )
            )
        self.thought_log.append(
            I18N.t("log_plugin_sync_complete").format(
                downloaded=len(result.downloaded),
                updated=len(result.updated),
                skipped=len(result.skipped),
            )
        )

    def get_current_project(self):
        return self.settings_tab.get_settings().get('project_name', 'default')

    def on_table_cell_edited(self, item):
        """Syncs table cell edits to the Editor Panel."""
        if item.column() != 3:
            return  # Translation column only

        row = item.row()
        new_text = item.text()
        seg = self.segments[row]

        # Avoid pointless loops
        if seg.translation == new_text:
            return

        seg.translation = new_text

        # If the editor is looking at this row, update the editor box
        if self.current_row == row:
            self.editor.trans_edit.blockSignals(True)
            self.editor.trans_edit.setPlainText(
                new_text.replace(TAG_ERROR_PREFIX_WITH_SPACE, ""))
            self.editor.trans_edit.blockSignals(False)

    def on_use_fuzzy_clicked(self):
        """Apply current fuzzy suggestion when the button is clicked."""
        if self._current_fuzzy_text:
            self.apply_fuzzy_suggestion(self._current_fuzzy_text)

    def on_use_history_clicked(self):
        """Apply selected history entry to the editor."""
        item = self.editor.history_list.currentItem()
        if not item:
            return
        self.apply_history_suggestion(item.text())

    def nav_next_needed(self):
        """Jumps to the next row that is Red (Error) or White (Untranslated)."""
        start = self.current_row + 1
        for i in range(start, self.table.rowCount()):
            seg = self.segments[i]
            # Jump if it's an error OR if it's empty
            if TAG_ERROR_PREFIX in seg.translation or not seg.translation or not seg.is_verified:
                self.table.setCurrentCell(i, 1)
                return
        self.thought_log.append(I18N.t("log_end_of_file"))

    def _auto_fit_column(self, index):
        if index > 0:  # Don't auto-fit the icon column
            self.table.resizeColumnToContents(index)

    def toggle_zen_mode(self):
        """Hides UI elements and switches table to 'Full Screen' Stretch mode."""
        is_zen = self.btn_zen.isChecked()

        if is_zen and self.btn_reverse_zen.isChecked():
            self.btn_reverse_zen.blockSignals(True)
            self.btn_reverse_zen.setChecked(False)
            self.btn_reverse_zen.blockSignals(False)

        # 1. Hide/Show standard elements
        self.thought_log.setVisible(not is_zen)
        self.progress_bar.setVisible(not is_zen)
        self.lbl_stats.setVisible(not is_zen)
        self.file_label.setVisible(not is_zen)
        self.editor_container.setVisible(not is_zen)
        self.btn_toggle_editor.setChecked(not is_zen)
        self.btn_toggle_editor.setEnabled(True)
        self.table.setVisible(True)

        # 2. Dynamic Column Stretching
        header = self.table.horizontalHeader()
        if is_zen:
            # In Focus: Table, make Source and Translation fill the screen
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        else:
            # When leaving Focus: Table, go back to Interactive (Excel-style)
            # This allows you to drag them again
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)

            # Restore your preferred widths from the saved state
            self.load_ui_state()

    def toggle_reverse_zen_mode(self):
        """Editor-focused mode: minimize the table and maximize the editor."""
        is_reverse = self.btn_reverse_zen.isChecked()

        if is_reverse and self.btn_zen.isChecked():
            self.btn_zen.blockSignals(True)
            self.btn_zen.setChecked(False)
            self.btn_zen.blockSignals(False)

        self.table.setVisible(not is_reverse)
        self.editor_container.setVisible(True)
        self.btn_toggle_editor.setChecked(True)
        self.btn_toggle_editor.setEnabled(not is_reverse)

        if not is_reverse:
            self.load_ui_state()

    def run_auto_normalize(self):
        settings = self.settings_tab.get_settings()
        reply = QMessageBox.question(
            self,
            I18N.t("dlg_auto_normalize_title"),
            I18N.t("msg_auto_normalize_confirm"),
        )
        if reply == QMessageBox.StandardButton.Yes:
            from core.database import auto_normalize_all_conflicts
            count = auto_normalize_all_conflicts(
                settings['project_name'], settings['lang'])
            QMessageBox.information(
                self,
                I18N.t("dlg_success_title"),
                I18N.t("msg_auto_normalize_success").format(count=count),
            )
            self.run_integrity_scan()  # Refresh the list
            self.refresh_table_from_db()  # Refresh the workstation icons
            self.audit_database_consistency()

    def remove_current_from_memory(self):
        """Wipes the current selection from the database entirely."""
        indices = self.table.selectionModel().selectedRows()
        if not indices:
            return

        reply = QMessageBox.question(
            self,
            I18N.t("dlg_forget_translation_title"),
            I18N.t("msg_forget_translation_confirm").format(count=len(indices)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            from core.database import delete_record
            settings = self.settings_tab.get_settings()

            for idx in indices:
                row = idx.row()
                seg = self.segments[row]
                # 1. Kill it in the DB
                delete_record(seg.source_text,
                              settings['lang'], settings['project_name'])
                # 2. Reset the UI segment
                seg.translation = ""
                seg.is_verified = False
                seg.thought = I18N.t("thought_purged_memory")
                self.update_row_visuals(row)

            self.update_stats()
            QMessageBox.information(
                self,
                I18N.t("dlg_success_title"),
                I18N.t("msg_segments_purged"),
            )

    def clear_selected_rows(self):
        """Wipes translations for all highlighted rows in UI and DB."""
        # Get unique selected row indices
        indices = self.table.selectionModel().selectedRows()
        if not indices:
            return

        reply = QMessageBox.question(
            self,
            I18N.t("dlg_clear_selected_title"),
            I18N.t("msg_clear_selected_confirm").format(count=len(indices)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            settings = self.settings_tab.get_settings()
            lang = settings.get('lang', 'BG')
            project_name = settings.get(
                'project_name', settings.get('project', 'default'))

            for index in indices:
                row_idx = index.row()
                if self.table.isRowHidden(row_idx):
                    continue
                seg = self.segments[row_idx]

                # Wipe data
                seg.translation = ""
                seg.is_verified = False
                seg.never_translate = False
                seg.thought = I18N.t("thought_wiped_by_user")

                # Update Database (Save as empty string)
                save_translation(
                    seg.source_text,
                    lang,
                    "",
                    project_name=project_name,
                    segment_key=seg.key,
                    verified=False,
                    skip=False,
                    ai_draft=getattr(seg, 'ai_draft', ""),
                )

                # Update Table Visuals
                self.update_row_visuals(row_idx)

            self.update_stats()

    def toggle_editor(self):
        self.editor_container.setVisible(self.btn_toggle_editor.isChecked())

    def filter_table(self):
        search_text = self.search_bar.text().lower()
        only_errors = self.cb_only_errors.isChecked()

        for i in range(self.table.rowCount()):
            key_item = self.table.item(i, 1)
            src_item = self.table.item(i, 2)

            key = key_item.text().lower() if key_item else ""
            src = src_item.text().lower() if src_item else ""
            # Get translation from the segment data directly
            trans = self.segments[i].translation.lower()

            match_search = search_text in key or search_text in src or search_text in trans
            match_error = TAG_ERROR_PREFIX in trans.upper(
            ) if only_errors else True

            self.table.setRowHidden(i, not (match_search and match_error))

    def translate_current_row(self):
        """Sends the currently selected single row to the LLM with a Stop option."""
        if self.current_row < 0:
            return

        # If a single worker is already running, this action is STOP.
        if hasattr(self, "single_worker") and self.single_worker.isRunning():
            self.single_worker.stop()
            # Optional: self.single_worker.terminate() if stop() is insufficient.
            self.editor.btn_translate_now.setText(I18N.t("btn_translate_line"))
            self.editor.btn_translate_now.setStyleSheet(
                "background-color: #34495e; color: white;"
            )
            return

        seg = self.segments[self.current_row]
        settings = self.settings_tab.get_settings()

        # Enter the "thinking" mode.
        self.editor.btn_translate_now.setText(I18N.t("btn_stop_thinking"))
        self.llm_request_count += 1
        self._update_llm_metrics_label()
        

        project_name = settings.get("project_name", "default")

        svc = LLMService(
            model_name=settings["model"],
            timeout=settings.get("llm_timeout"),
        )
        self.single_worker = TranslationWorker(
            segments=[seg],
            target_lang=settings["lang"],
            llm_service=svc,
            glossary_path=settings["glossary_path"],
            style_path=settings["style_path"],
            forbidden_path=settings["forbidden_path"],
            prompt_template=settings["prompt_template"],
            temp=settings["temp"],
            strict=settings["strict_mode"],
            project_name=project_name,
        )

        self.single_worker.finished_signal.connect(self.on_single_done)
        self.single_worker.start()

    def on_single_done(self, result):
        self.editor.btn_translate_now.setEnabled(True)
        self.editor.btn_translate_now.setText(I18N.t("btn_translate_line"))

        # Update visuals and editor content
        self.update_row_visuals(self.current_row)
        seg = self.segments[self.current_row]
        if (seg.translation or "").startswith(TAG_ERROR_PREFIX):
            self.llm_failure_count += 1
            self._update_llm_metrics_label()
        self.editor.trans_edit.setPlainText(
            seg.translation.replace(TAG_ERROR_PREFIX_WITH_SPACE, ""))
        self.editor.ai_draft_display.setPlainText(seg.ai_draft)
        self.update_stats()

    def _format_stats_text(
        self,
        verified,
        draft,
        risk,
        error,
        conflict,
        pending,
        repair_success=0,
        repair_failed=0,
    ):
        return I18N.t("stats_template").format(
            verified=verified,
            draft=draft,
            risk=risk,
            error=error,
            conflict=conflict,
            pending=pending,
            repair_success=repair_success,
            repair_failed=repair_failed,
        )

    def update_selection_info(self):
        """Updates the status bar with selection count without making the window explode."""
        selected_indices = self.table.selectionModel().selectedRows()
        count = len(selected_indices)

        # 1. Start with fresh stats
        v, qa, risk, err, pend, conflict = 0, 0, 0, 0, 0, 0
        repair_success = repair_failed = 0
        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if item:
                txt = item.text()
                state_icon = self._resolve_state_icon(txt)
                if state_icon == "🟢":
                    v += 1
                elif state_icon == "🟡":
                    qa += 1
                elif state_icon == "🔶":
                    risk += 1
                elif state_icon == "🔴":
                    err += 1
                elif state_icon == "🔵":
                    conflict += 1
                else:
                    pend += 1
            if i < len(self.segments):
                seg = self.segments[i]
                if getattr(seg, "repair_success", False):
                    repair_success += 1
                if getattr(seg, "repair_failed", False):
                    repair_failed += 1

        stats_text = self._format_stats_text(
            v,
            qa,
            risk,
            err,
            conflict,
            pend,
            repair_success,
            repair_failed,
        )

        # 2. Add selection info ONLY if more than 1 is selected
        # We set the text CLEANly here to prevent the "selected: 4 selected: 3" loop
        if count > 1:
            self.lbl_stats.setText(
                I18N.t("stats_selected_template").format(
                    count=count,
                    stats=stats_text,
                )
            )
        else:
            self.lbl_stats.setText(stats_text)

    def _resolve_state_icon(self, text: str) -> str:
        if not text:
            return ""
        for icon in ("🔵", "🟢", "🔴", "🔶", "🟡", "⚪"):
            if text.startswith(icon):
                return icon
        return ""

    def on_row_selected(self):
        """When a row is clicked, load data into the editor safely."""
        row = self.table.currentRow()
        if row < 0:
            return

        self.current_row = row
        seg = self.segments[row]

        # Block signals so the editor doesn't try to sync
        # back to the table while we are just loading the row data.
        self.editor.trans_edit.blockSignals(True)
        self.editor.source_edit.blockSignals(True)

        # 1. Update text fields
        self.editor.source_edit.setText(seg.source_text)
        self.editor.ai_draft_display.setText(seg.ai_draft)
        if hasattr(self.editor, "refresh_tag_chips"):
            self.editor.refresh_tag_chips(seg.source_text)
        raw_translation = (seg.translation or "").strip()
        
        if not raw_translation:
            m = Masker()
            skeleton = m.get_tag_skeleton(seg.source_text)
            self.editor.trans_edit.setPlainText(skeleton)
        else:
            self.editor.trans_edit.setPlainText(
                raw_translation.replace(TAG_ERROR_PREFIX_WITH_SPACE, "")
            )

        # Unblock after loading is finished
        self.editor.trans_edit.blockSignals(False)
        self.editor.source_edit.blockSignals(False)

        # 2. Sync checkboxes with segment flags
        self.editor.cb_verified.setChecked(getattr(seg, "is_verified", False))

        # 3. LOAD HISTORY LIST
        self.editor.history_list.clear()
        try:
            settings = self.settings_tab.get_settings()
            record = get_cached_record(
                seg.source_text,
                settings.get("lang", "BG"),
                project_name=settings.get("project_name", "default"),
                segment_key=seg.key,
            )

            if record and record.history_json:
                history_data = json.loads(record.history_json or "[]")
                for old_ver in reversed(history_data):
                    if old_ver.strip():
                        self.editor.history_list.addItem(old_ver)
        except Exception:
            pass
        self.update_history_action_state()

        # 4. Conditional Fuzzy Match Search
        is_skip = getattr(seg, 'never_translate', False)

        if self._segment_needs_fuzzy(seg) and not is_skip:
            self.search_fuzzy_matches(seg.source_text)
        else:
            self.editor.fuzzy_display.clear()
            self.editor.btn_use_fuzzy.setVisible(False)

        self._update_remote_change_panel(seg)
        self._update_provider_fields_panel(seg)

    def search_fuzzy_matches(self, text):
        """Looks for similar lines and updates the editor panel."""
        self.editor.fuzzy_display.clear()
        self.editor.btn_use_fuzzy.setVisible(False)
        self._current_fuzzy_text = ""

        if self.current_row < 0:
            return

        settings = self.settings_tab.get_settings()
        engine_helper = TranslationEngine(self.llm_service)

        match = engine_helper.find_fuzzy_match(
            text,
            settings.get("project_name", "default"),
            settings.get("lang", "BG"),
        )

        if match:
            info = (
                f"{I18N.t('fuzzy_score').format(score=match['score'])}\n"
                f"{I18N.t('fuzzy_source').format(source=match['source'])}\n"
                f"{I18N.t('fuzzy_suggestion').format(translation=match['translation'])}"
            )
            self.editor.fuzzy_display.setText(info)
            self.editor.btn_use_fuzzy.setVisible(True)
            self._current_fuzzy_text = match["translation"]

    def apply_fuzzy_suggestion(self, text: str) -> None:
        """Copies the fuzzy match translation into the active editor."""
        self._apply_editor_suggestion(text)
        self.editor.btn_use_fuzzy.setVisible(False)
        self.thought_log.append(
            I18N.t("log_fuzzy_applied"))

    def apply_history_suggestion(self, text: str) -> None:
        """Copies a history entry into the editor without changing verification."""
        self._apply_editor_suggestion(text)
        self.thought_log.append(I18N.t("log_history_restored"))

    def _segment_needs_fuzzy(self, seg) -> bool:
        has_tag_error = TAG_ERROR_PREFIX in (seg.translation or "")
        has_risk = bool(getattr(seg, "has_risk", False)) or "⚠️" in (seg.thought or "")
        return has_tag_error or has_risk

    def _normalize_suggestion_text(self, suggestion: str, source_text: str) -> str:
        cleaned = (suggestion or "").replace(TAG_ERROR_PREFIX_WITH_SPACE, "").strip()
        source_tags = extract_tags(source_text or "")
        if not source_tags:
            return cleaned
        suggestion_tags = extract_tags(cleaned)
        suggestion_tags_copy = list(suggestion_tags)
        missing_tags = []
        for tag in source_tags:
            try:
                suggestion_tags_copy.remove(tag)
            except ValueError:
                missing_tags.append(tag)
        if missing_tags:
            spacer = " " if cleaned and not cleaned.endswith(" ") else ""
            cleaned = f"{cleaned}{spacer}{' '.join(missing_tags)}".strip()
        return cleaned

    def _apply_editor_suggestion(self, text: str) -> None:
        if self.current_row < 0:
            return
        seg = self.segments[self.current_row]
        safe_text = self._normalize_suggestion_text(text, seg.source_text)
        self.editor.trans_edit.setPlainText(safe_text)

    def _refresh_fuzzy_for_segment(self, seg) -> None:
        if self.current_row < 0:
            return
        if self._segment_needs_fuzzy(seg):
            self.search_fuzzy_matches(seg.source_text)
        else:
            self.editor.fuzzy_display.clear()
            self.editor.btn_use_fuzzy.setVisible(False)

    def update_history_action_state(self) -> None:
        has_selection = bool(self.editor.history_list.currentItem())
        self.editor.btn_use_history.setEnabled(has_selection)

    def nav_error(self, direction):
        """Navigates to the next or previous Red row."""
        start = self.current_row + direction
        rng = range(start, self.table.rowCount()
                    ) if direction > 0 else range(start, -1, -1)

        for i in rng:
            if TAG_ERROR_PREFIX in self.segments[i].translation:
                self.table.setCurrentCell(i, 1)
                break

    def save_manual_edit(self):
        """Master commit from the Editor: save text, force-verify, and persist scoped to project/lang."""
        if self.current_row < 0:
            return

        seg = self.segments[self.current_row]

        # 1) Get text from Editor
        new_text = self.editor.trans_edit.toPlainText()

        # 2) Update segment state (SYNC is important)
        seg.translation = new_text
        seg.is_verified = True  # Save always verifies
        seg.thought = I18N.t("thought_verified_by_human")
        self.editor.cb_verified.setChecked(True)

        # 3) Project/Lang
        settings = self.settings_tab.get_settings()
        project_name = settings.get("project_name", "default")
        lang = settings.get("lang", "BG")

        # 4) Save to DB with all flags
        save_translation(
            seg.source_text,
            lang,
            new_text,
            project_name=project_name,
            segment_key=seg.key,
            verified=True,
            skip=getattr(seg, "never_translate", False),
            ai_draft=getattr(seg, "ai_draft", ""),
        )

        # 5) UI refresh
        self.update_row_visuals(self.current_row)
        self.update_stats()
        self.table.setFocus()

        # 6) QoL: auto-jump to next line that needs attention
        self.nav_next_needed()

    def get_best_font(self, size: int):
        """Scans the system for the best font supporting the target language's script."""
        settings = self.settings_tab.get_settings()
        # e.g., "BG", "JA", "AR"
        lang_code = settings.get('lang', 'BG').upper()

        db = QFontDatabase()

        # 1. Map Language Codes to Qt Writing Systems
        # This covers the major "Non-Latin" game localization targets
        script_map = {
            "BG": QFontDatabase.WritingSystem.Cyrillic,
            "RU": QFontDatabase.WritingSystem.Cyrillic,
            "UK": QFontDatabase.WritingSystem.Cyrillic,
            "EL": QFontDatabase.WritingSystem.Greek,
            "JA": QFontDatabase.WritingSystem.Japanese,
            "ZH": QFontDatabase.WritingSystem.SimplifiedChinese,
            "KO": QFontDatabase.WritingSystem.Korean,
            "AR": QFontDatabase.WritingSystem.Arabic,
            "HE": QFontDatabase.WritingSystem.Hebrew,
            "TH": QFontDatabase.WritingSystem.Thai,
            "HI": QFontDatabase.WritingSystem.Devanagari,
        }

        # Determine the writing system (Default to Latin if unknown)
        target_system = script_map.get(
            lang_code, QFontDatabase.WritingSystem.Latin)
        supported_families = db.families(target_system)

        # 2. Cross-platform priority list
        priority_list = [
            "Segoe UI", "San Francisco", "Ubuntu", "Noto Sans",
            "DejaVu Sans", "Arial", "MS PGothic", "Microsoft YaHei"
        ]

        selected_family = ""
        for family in priority_list:
            if family in supported_families:
                selected_family = family
                break

        # Fallback: Just take the first font that supports the required script
        if not selected_family and supported_families:
            selected_family = supported_families[0]

        font = QFont(selected_family or "Sans Serif", size)
        font.setStyleHint(QFont.StyleHint.SansSerif)
        return font

    def apply_font_size(self, size):
        """Updates font size globally using the universal font scanner."""
        new_font = self.get_best_font(int(size))

        self.table.setFont(new_font)

        if hasattr(self, 'editor'):
            self.editor.source_edit.setFont(new_font)
            self.editor.trans_edit.setFont(new_font)
            self.editor.history_list.setFont(new_font)
            # Update the AI Draft display as well
            if hasattr(self.editor, 'ai_draft_display'):
                self.editor.ai_draft_display.setFont(new_font)

        if hasattr(self, 'lbl_stats'):
            self.lbl_stats.setFont(new_font)

        self.thought_log.setFont(new_font)
        self.current_font = new_font

    def show_context_menu(self, pos):
        """Right-click menu for the table."""
        # If nothing is selected, try to select the row under the mouse
        if not self.table.selectionModel().hasSelection():
            item = self.table.itemAt(pos)
            if item:
                self.table.selectRow(item.row())

        selected_indices = self.table.selectionModel().selectedRows()
        if not selected_indices:
            return

        self._context_menu_indices = selected_indices
        self._context_menu_row = selected_indices[0].row()
        menu = QMenu(self)
        count = len(selected_indices)
        self._context_menu_count = count
        self._update_context_menu_texts(count)

        if count > 1:
            # --- MULTI-ROW ACTIONS ---
            menu.addAction(self.action_verify_rows)
            menu.addAction(self.action_unverify_rows)
            menu.addAction(self.action_skip_rows)

            menu.addSeparator()
            menu.addAction(self.action_purge_memory)

            menu.addSeparator()
            menu.addAction(self.action_generate_pseudo)
            menu.addAction(self.action_purge_record)
            menu.addAction(self.action_clear_translations)
        else:
            # --- SINGLE-ROW ACTIONS ---
            menu.addAction(self.action_copy_source)
            menu.addAction(self.action_mark_verified)
            menu.addAction(self.action_never_translate)
            menu.addSeparator()
            menu.addAction(self.action_clear_translation)
            menu.addAction(self.action_purge_record)

        # --- GLOBAL ACTIONS ---
        menu.addSeparator()
        menu.addAction(self.action_search_replace)
        menu.addAction(self.action_export_verified)

        # Map local table coordinates to global screen coordinates correctly
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def bulk_verify_selected(self, indices):
        if not indices:
            return
        settings = self.settings_tab.get_settings()
        lang = settings.get('lang', 'BG')
        project_name = settings.get(
            'project_name', settings.get('project', 'default'))
        for idx in indices:
            row = idx.row()
            seg = self.segments[row]
            if seg.translation:
                seg.is_verified = True  # Update memory
                # Update DB
                save_translation(
                    seg.source_text,
                    lang,
                    seg.translation,
                    project_name=project_name,
                    segment_key=seg.key,
                    verified=True,
                    skip=seg.never_translate,
                    ai_draft=getattr(seg, 'ai_draft', ""),
                )
                self.update_row_visuals(row)
        self.update_stats()

    def quick_action(self, row, action_type):
        seg = self.segments[row]
        settings = self.settings_tab.get_settings()

        lang = settings.get("lang", "BG")
        project_name = settings.get(
            "project_name", settings.get("project", "default"))

        # Current flags
        is_ver = bool(getattr(seg, "is_verified", False))
        is_skip = bool(getattr(seg, "never_translate", False))

        if action_type == "skip":
            # Never translate → copy source and flag as skip
            seg.translation = seg.source_text
            is_skip = True
            is_ver = False

        elif action_type == "copy":
            # Copy source text into translation
            seg.translation = seg.source_text

        elif action_type == "clear":
            # Clear translation and reset flags
            seg.translation = ""
            is_ver = False
            is_skip = False

        elif action_type == "verify":
            # Mark as manually verified
            is_ver = True

        # Persist to DB with full context
        save_translation(
            seg.source_text,
            lang,
            seg.translation,
            project_name=project_name,
            segment_key=seg.key,
            verified=is_ver,
            skip=is_skip,
            ai_draft=getattr(seg, "ai_draft", ""),
        )

        # Sync back to segment object
        seg.is_verified = is_ver
        seg.never_translate = is_skip

        self.update_row_visuals(row)
        self.update_stats()

    def update_row_visuals(self, row_idx: int):
        if row_idx < 0 or row_idx >= len(self.segments):
            return

        seg = self.segments[row_idx]

        # Ensure items exist
        for column_index in (0, 3):
            if not self.table.item(row_idx, column_index):
                self.table.setItem(row_idx, column_index, QTableWidgetItem())

        state_item = self.table.item(row_idx, 0)
        trans_item = self.table.item(row_idx, 3)

        # --- FLAGS ---
        is_skip = getattr(seg, "never_translate", False)
        is_verified = getattr(seg, "is_verified", False)
        is_conflict = getattr(seg, "has_conflict", False)

        translation = seg.translation or ""
        thought = seg.thought or ""

        has_tag_error = TAG_ERROR_PREFIX in translation
        has_risk = "⚠️" in thought

        # --- PRIORITY RESOLUTION (single source of truth) ---
        if is_conflict:
            icon, color = "🔵", QColor("#1a237e")
        elif is_skip:
            icon, color = "⚪", QColor("#3c3f41")
        elif is_verified:
            icon, color = "🟢", QColor("#113311")
        elif has_tag_error:
            icon, color = "🔴", QColor("#441111")
        elif has_risk:
            icon, color = "🔶", QColor("#443311")
        elif translation:
            icon, color = "🟡", QColor("#333311")
        else:
            icon, color = "⚪", QColor("#222222")

        sync_icon, sync_tooltip = self._sync_indicator_for_segment(seg)
        has_remote_change = self._remote_change_ready and (
            getattr(seg, "remote_changed", False)
            or self._segment_change_key(seg) in self._remote_change_map
        )
        if has_remote_change:
            sync_icon = f"{sync_icon}⚠️"

        # --- APPLY VISUALS ---
        if state_item:
            state_item.setText(f"{icon}{sync_icon}")
            state_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
        if trans_item:
            trans_item.setText(translation)

        for c in range(4):
            item = self.table.item(row_idx, c)
            if item:
                item.setBackground(color)
                item.setForeground(QColor("#eeeeee"))

        # --- TOOLTIP LOGIC (derived from resolved state) ---
        status_msg = I18N.t("status_header").format(icon=icon) + "\n"

        if is_skip:
            status_msg += I18N.t("status_locked")
        elif is_conflict:
            status_msg += I18N.t("status_conflict")
        elif is_verified:
            status_msg += I18N.t("status_verified")
        elif has_tag_error:
            status_msg += I18N.t("status_tag_error")
        elif has_risk:
            # Extract first audit warning safely
            status_msg += I18N.t("status_audit_alert").format(
                issue=thought.split('|')[0].strip()
            )
        elif translation:
            status_msg += I18N.t("status_ai_draft")
        else:
            status_msg += I18N.t("status_untranslated")

        if state_item:
            status_msg += "\n" + sync_tooltip
            if has_remote_change:
                status_msg += "\n" + I18N.t("status_sync_remote_changed")
            state_item.setToolTip(status_msg)

        # QoL: show full text on hover
        if trans_item:
            trans_item.setToolTip(translation)

        src_item = self.table.item(row_idx, 2)
        if src_item:
            src_item.setToolTip(seg.source_text)

        if row_idx == self.current_row:
            self._refresh_fuzzy_for_segment(seg)

    def _resolve_remote_sync_timestamp(self, item: dict[str, Any]) -> str | None:
        for key in ("last_sync", "synced_at", "updated_at"):
            value = item.get(key)
            if value:
                return str(value)
        return None

    def _sync_indicator_for_segment(self, seg: TranslationSegment) -> tuple[str, str]:
        if self._has_remote_metadata(seg):
            last_sync = self._resolve_remote_sync_timestamp(seg.original_row or {})
            if last_sync:
                timestamp_text = last_sync
            else:
                timestamp_text = I18N.t("status_sync_unknown")

            return "☁️", I18N.t("status_sync_remote").format(timestamp=timestamp_text)

        return "🏠", I18N.t("status_sync_local")


    def _has_remote_metadata(self, seg: TranslationSegment) -> bool:
        row = getattr(seg, "original_row", {}) or {}
        return bool(
            getattr(seg, "provider_id", None)
            or getattr(seg, "remote_id", None)
            or row.get("provider_id")
            or row.get("remote_id")
        )

    def _resolve_segment_sync_timestamp(self, seg: TranslationSegment) -> str | None:
        if getattr(seg, "last_sync", None):
            return str(seg.last_sync)
        row = getattr(seg, "original_row", {}) or {}
        for key in ("last_sync", "synced_at", "updated_at"):
            value = row.get(key)
            if value:
                return str(value)
        return None

    def run_pseudo_batch(self):
        engine = TranslationEngine(self.llm_service)
        engine.run_pseudo_localization(self.segments)
        for i in range(self.table.rowCount()):
            self.update_row_visuals(i)
        self.update_stats()

    def show_find_replace(self):
        text_find, ok1 = QInputDialog.getText(
            self,
            I18N.t("dlg_find_title"),
            I18N.t("msg_find_text"),
        )
        if not ok1 or not text_find:
            return
        text_replace, ok2 = QInputDialog.getText(
            self,
            I18N.t("dlg_replace_title"),
            I18N.t("msg_replace_with").format(text=text_find),
        )
        if not ok2:
            return

        count = 0
        for seg in self.segments:
            if text_find in seg.translation:
                seg.translation = seg.translation.replace(
                    text_find, text_replace)
                count += 1

        # Refresh the table view
        for i in range(self.table.rowCount()):
            self.update_row_visuals(i)

        QMessageBox.information(
            self,
            I18N.t("dlg_replace_complete_title"),
            I18N.t("msg_replace_complete").format(count=count),
        )

    def on_tab_changed(self, index):
        """If returning to the workstation, refresh the icons based on current project."""
        if index == 0 and self.segments:
            # Re-scan the database for the new project name/lang
            self.refresh_table_from_db()

    def show_history_context_menu(self, pos):
        """Right-click menu for the history list to purge bad versions."""
        item = self.editor.history_list.itemAt(pos)
        if not item:
            return

        self._history_menu_item = item
        menu = QMenu()
        menu.addAction(self.action_history_delete)
        menu.exec(QCursor.pos())

    def refresh_table_from_db(self):
        """Force-syncs table with DB, preserving session-specific errors and risks."""
        settings = self.settings_tab.get_settings()
        p_name = settings.get('project_name', 'default')
        lang = settings['lang']

        for i, seg in enumerate(self.segments):
            # 1. PRESERVE TRANSIENT STATE
            # Store current session info before we look at the DB
            current_is_error = TAG_ERROR_PREFIX in seg.translation
            current_thought = seg.thought or ""
            has_warning = "⚠️" in current_thought

            # 2. DATABASE LOOKUP
            record = get_cached_record(
                seg.source_text,
                lang,
                project_name=p_name,
                segment_key=seg.key,
            )

            if record:
                # Only overwrite if the DB has a VERIFIED translation
                # OR if we don't currently have an error marker.
                if record.is_verified or not current_is_error:
                    seg.translation = record.translation
                    seg.is_verified = record.is_verified
                    seg.never_translate = record.never_translate
                    seg.ai_draft = record.ai_draft

                    # Only overwrite the thought if it doesn't contain a session warning
                    if not has_warning:
                        seg.thought = I18N.t("thought_restored_from_memory")
            else:
                # If no record in DB, we keep what we have in memory (preserving [TAG ERROR])
                pass

            # 3. VISUAL UPDATE
            self.update_row_visuals(i)

        self.update_stats()

    def run_integrity_scan(self):
        """Scans DB and populates the Integrity Hub (Integrity tab)."""

        settings = self.settings_tab.get_settings()
        project_name = settings.get(
            "project_name", settings.get("project", "default"))
        lang = settings.get("lang", "BG")

        report = get_project_integrity_report(project_name, lang)

        # Fill the Integrity tab table
        self.integrity_tab.populate_report(report)

        # Wire up the Normalize buttons
        for i in range(self.integrity_tab.table.rowCount()):
            btn = self.integrity_tab.table.cellWidget(i, 2)
            if isinstance(btn, QPushButton):
                source = report[i]["source"]
                variants = list(report[i]["variants"].keys())
                btn.clicked.connect(
                    lambda checked=False, s=source, v=variants: self.resolve_conflict_dialog(s, v))

    def resolve_conflict_dialog(self, source, variants):
        """Shows a dialog to pick the one true translation and normalizes the DB."""

        settings = self.settings_tab.get_settings()
        project_name = settings.get(
            "project_name", settings.get("project", "default"))
        lang = settings.get("lang", "BG")

        choice, ok = QInputDialog.getItem(
            self,
            I18N.t("dlg_resolve_conflict_title"),
            I18N.t("msg_resolve_conflict_prompt").format(source=source),
            variants,
            0,
            False,
        )

        if ok and choice:
            normalize_project_term(project_name, lang, source, choice)
            QMessageBox.information(
                self,
                I18N.t("dlg_success_title"),
                I18N.t("msg_resolve_conflict_success"),
            )

            # Refresh Integrity Hub and table markers
            self.run_integrity_scan()
            self.audit_database_consistency()

    def audit_database_consistency(self):
        """Scans the DB for conflicts and marks rows using normalized comparison."""
        settings = self.settings_tab.get_settings()
        p_name = settings.get('project_name', 'default')
        lang = settings['lang']

        # This returns a list of normalized source strings that have conflicts
        conflicts = find_translation_conflicts(p_name, lang)

        if not conflicts:
            # Clear any old blue markers if conflicts were resolved
            for seg in self.segments:
                seg.has_conflict = False
            return

        count = 0
        for i, seg in enumerate(self.segments):
            # Normalize the segment source text exactly like the DB does
            norm_seg_src = " ".join(seg.source_text.lower().split())

            if norm_seg_src in conflicts:
                seg.has_conflict = True
                self.update_row_visuals(i)
                count += 1
            else:
                seg.has_conflict = False

        if count > 0:
            self.thought_log.append(
                I18N.t("log_integrity_found").format(count=count))
            self.update_stats()

    def global_db_replace(self):
        """Finds and replaces text across the ENTIRE database for this project/lang."""
        text_find, ok1 = QInputDialog.getText(
            self,
            I18N.t("dlg_global_db_fix_title"),
            I18N.t("msg_global_db_find"),
        )
        if not ok1 or not text_find:
            return

        text_replace, ok2 = QInputDialog.getText(
            self,
            I18N.t("dlg_global_db_fix_title"),
            I18N.t("msg_global_db_replace_with").format(text=text_find),
        )
        if not ok2:
            return

        settings = self.settings_tab.get_settings()
        project_name = settings.get("project_name", "default")
        lang = settings.get("lang", "BG")

        with Session(engine) as session:
            statement = select(TranslationRecord).where(
                TranslationRecord.project_name == project_name,
                TranslationRecord.target_lang == lang,
                col(TranslationRecord.translation).like(f"%{text_find}%"),
            )
            records = session.exec(statement).all()

            if not records:
                QMessageBox.information(
                    self,
                    I18N.t("dlg_global_db_fix_title"),
                    I18N.t("msg_global_db_no_matches"),
                )
                return

            reply = QMessageBox.question(
                self,
                I18N.t("dlg_global_db_confirm_title"),
                I18N.t("msg_global_db_confirm").format(count=len(records)),
            )
            if reply == QMessageBox.StandardButton.Yes:
                for r in records:
                    if r.translation:
                        r.translation = r.translation.replace(
                            text_find, text_replace)
                        r.is_verified = True
                        session.add(r)
                session.commit()

        QMessageBox.information(
            self,
            I18N.t("dlg_success_title"),
            I18N.t("msg_global_db_success").format(count=len(records)),
        )

    def keyPressEvent(self, event):
        """Standard window-level shortcut for the Delete key."""
        if event.key() == Qt.Key.Key_Delete:
            # Only trigger if the table is the active widget
            if self.table.hasFocus():
                self.clear_selected_rows()
        super().keyPressEvent(event)

    def update_stats(self):
        """Calculates and updates the bottom bar dashboard counters."""
        v = qa = risk = err = pend = conflict = 0
        repair_success = repair_failed = 0

        for i in range(self.table.rowCount()):
            item = self.table.item(i, 0)
            if not item:
                continue
            txt = item.text()
            state_icon = self._resolve_state_icon(txt)
            if state_icon == "🟢":
                v += 1
            elif state_icon == "🟡":
                qa += 1
            elif state_icon == "🔶":
                risk += 1
            elif state_icon == "🔴":
                err += 1
            elif state_icon == "🔵":
                conflict += 1
            else:
                pend += 1
            if i < len(self.segments):
                seg = self.segments[i]
                if getattr(seg, "repair_success", False):
                    repair_success += 1
                if getattr(seg, "repair_failed", False):
                    repair_failed += 1

        # 1. Update the text with clear separators
        self.lbl_stats.setText(
            self._format_stats_text(
                v,
                qa,
                risk,
                err,
                conflict,
                pend,
                repair_success,
                repair_failed,
            )
        )
        self.lbl_stats.setStyleSheet("""
            QLabel { 
                font-family: 'Consolas', 'Courier New'; 
                font-weight: bold; 
                padding: 2px 10px;
                border-radius: 4px;
            }
        """)

        # 2. Update the Tooltip (Hover info)
        self.lbl_stats.setToolTip(
            I18N.t("stats_tooltip").format(
                title=I18N.t("stats_tooltip_title"),
                verified=I18N.t("stats_tooltip_verified"),
                draft=I18N.t("stats_tooltip_draft"),
                risk=I18N.t("stats_tooltip_risk"),
                error=I18N.t("stats_tooltip_error"),
                conflict=I18N.t("stats_tooltip_conflict"),
                pending=I18N.t("stats_tooltip_pending"),
                repair=I18N.t("stats_tooltip_repair"),
            )
        )
        self._update_metrics_labels(
            v,
            qa,
            risk,
            err,
            conflict,
            pend,
            repair_success,
            repair_failed,
        )

    def _update_llm_metrics_label(self) -> None:
        if hasattr(self, "metrics_llm_label"):
            batch_duration = self._format_seconds(
                self._batch_metrics.duration_seconds
            )
            avg_row = self._format_seconds(self._batch_metrics.avg_seconds)
            model_name = self._batch_metrics.model_name or I18N.t(
                "metrics_model_unknown"
            )
            self.metrics_llm_label.setText(
                I18N.t("metrics_llm_template").format(
                    requests=self.llm_request_count,
                    failures=self.llm_failure_count,
                    model=model_name,
                    batch_duration=batch_duration,
                    avg_row=avg_row,
                )
            )

    @staticmethod
    def _format_seconds(value: float | None) -> str:
        if value is None:
            return "—"
        if value >= 60:
            minutes = int(value // 60)
            seconds = value % 60
            return f"{minutes}m {seconds:.1f}s"
        return f"{value:.1f}s"

    def _update_metrics_labels(
        self,
        verified: int,
        draft: int,
        risk: int,
        error: int,
        conflict: int,
        pending: int,
        repair_success: int,
        repair_failed: int,
    ) -> None:
        if not hasattr(self, "metrics_stats_label"):
            return
        total = verified + draft + risk + error + conflict + pending
        verified_rate = f"{(verified / total * 100):.1f}%" if total else "0%"
        self.metrics_stats_label.setText(
            self._format_stats_text(
                verified,
                draft,
                risk,
                error,
                conflict,
                pending,
                repair_success,
                repair_failed,
            )
        )
        self._update_llm_metrics_label()
        self.metrics_accuracy_label.setText(
            I18N.t("metrics_accuracy_template").format(
                verified_rate=verified_rate,
                placeholder_errors=error,
                audit_warnings=risk,
                conflicts=conflict,
            )
        )

    def _update_run_button_text(self):
        if self._bulk_stopping:
            self.btn_run.setText(I18N.t("ui_stopping_bulk"))
            self.btn_run.setEnabled(False)
            self.btn_run.setStyleSheet(
                "background-color: #aa3333; font-weight: bold;"
            )
        elif hasattr(self, 'worker') and self.worker.isRunning():
            self.btn_run.setText(I18N.t("ui_stop_bulk"))
            self.btn_run.setEnabled(True)
        else:
            self.btn_run.setText(I18N.t("ui_start_bulk"))
            self.btn_run.setEnabled(True)

    def _update_translate_button_text(self):
        if hasattr(self, "single_worker") and self.single_worker.isRunning():
            self.editor.btn_translate_now.setText(I18N.t("btn_stop_thinking"))
        else:
            self.editor.btn_translate_now.setText(I18N.t("btn_translate_line"))

    def _capture_workflow_focus(self) -> None:
        widget = self.focusWidget()
        if widget is None or not widget.isVisible():
            widget = self.editor.trans_edit
        self._workflow_focus_widget = widget

    def _restore_workflow_focus(self) -> None:
        widget = getattr(self, "_workflow_focus_widget", None)
        if widget is not None and widget.isVisible():
            widget.setFocus(Qt.FocusReason.OtherFocusReason)

    def request_tsv_import(self) -> None:
        self._capture_workflow_focus()
        dialog = QFileDialog(
            self,
            I18N.t("btn_import_tsv"),
            "",
            I18N.t("filter_tsv"),
        )
        dialog.setFileMode(QFileDialog.FileMode.ExistingFile)
        dialog.setModal(False)
        dialog.fileSelected.connect(
            lambda path: self.import_tsv_path(Path(path))
        )
        dialog.rejected.connect(self._restore_workflow_focus)
        dialog.open()
        self._tsv_dialog = dialog

    def request_tsv_export(self) -> None:
        if not self.segments:
            return
        self._capture_workflow_focus()
        dialog = QFileDialog(
            self,
            I18N.t("btn_export_tsv"),
            "",
            I18N.t("filter_tsv"),
        )
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setDefaultSuffix("tsv")
        dialog.setModal(False)
        default_name = self.input_path.name if self.input_path else "export.tsv"
        dialog.selectFile(default_name)
        dialog.fileSelected.connect(
            lambda path: self.export_tsv_path(Path(path))
        )
        dialog.rejected.connect(self._restore_workflow_focus)
        dialog.open()
        self._tsv_dialog = dialog

    def import_tsv_path(self, path: Path) -> None:
        if not path:
            self._restore_workflow_focus()
            return
        self._reset_remote_change_state()
        self.input_path = Path(path)
        self.file_label.setText(str(self.input_path))
        self._file_loaded = True

        # PERFORMANCE: Freeze table updates while we populate rows
        self.table.setUpdatesEnabled(False)
        self.table.blockSignals(True)

        try:
            # 1. Parse the TSV
            self.segments = self._tsv_parser.parse_tsv(self.input_path)
            self.table.setRowCount(len(self.segments))

            # 2. Get current project settings
            settings = self.settings_tab.get_settings()
            target_lang = settings["lang"]
            project_name = self.get_current_project()

            # 3. Load the glossary dictionary specifically for the audit

            engine_helper = TranslationEngine(self.llm_service)
            # We load it from the path defined in your settings tab
            glossary_dict = ResourceLoader.load_glossary_dict(
                settings["glossary_path"])

            # 4. Load cached translations + audit-on-load
            for i, seg in enumerate(self.segments):
                record = get_cached_record(
                    seg.source_text,
                    target_lang,
                    project_name,
                    segment_key=seg.key,
                )
                if record:
                    seg.translation = record.translation
                    seg.is_verified = record.is_verified
                    seg.never_translate = record.never_translate
                    seg.ai_draft = record.ai_draft
                    seg.thought = I18N.t("thought_restored_from_memory")

                    # Run audit immediately so 🔶 appears on rows already in DB
                    if seg.translation and TAG_ERROR_PREFIX not in seg.translation:
                        engine_helper.audit_segment(seg, glossary_dict)

                # 5. Populate Table Row
                self.table.setItem(i, 0, QTableWidgetItem("⚪"))
                self.table.setItem(i, 1, QTableWidgetItem(seg.key))
                self.table.setItem(i, 2, QTableWidgetItem(seg.source_text))
                self.table.setItem(i, 3, QTableWidgetItem(seg.translation))

                # Apply state colors/icons
                self.update_row_visuals(i)

        finally:
            self.table.blockSignals(False)
            self.table.setUpdatesEnabled(True)

        # UI Refresh
        self.btn_run.setEnabled(True)
        self.progress_bar.setMaximum(len(self.segments))
        self.update_stats()

        # Set progress bar to current completion level
        finished_count = sum(1 for s in self.segments if s.is_verified)
        self.progress_bar.setValue(finished_count)

        # Final consistency audit for 🔵 markers
        self.audit_database_consistency()
        self.btn_export_tsv.setEnabled(True)
        self._restore_workflow_focus()

    def export_tsv_path(self, path: Path) -> None:
        if not path or not self.segments:
            self._restore_workflow_focus()
            return
        self._tsv_parser.save_tsv(self.segments, path)
        self.file_label.setText(
            I18N.t("msg_file_saved").format(path=path)
        )
        self._restore_workflow_focus()

    def open_file(self):
        self.request_tsv_import()

    def handle_run_clicked(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
            self._bulk_stopping = True
            self._update_run_button_text()
            self.progress_bar.setValue(0)  # RESET BAR
        else:
            self.start_translation()

    def start_translation(self):
        settings = self.settings_tab.get_settings()
        self._bulk_stopping = False
        self.btn_run.setText(I18N.t("ui_stop_bulk"))
        self.btn_run.setStyleSheet(
            "background-color: #aa3333; font-weight: bold;")
        self.llm_request_count += self._count_llm_requests(self.segments)
        self._batch_metrics.started_at = time.monotonic()
        self._batch_metrics.processed_rows = 0
        self._batch_metrics.duration_seconds = None
        self._batch_metrics.avg_seconds = None
        self._batch_metrics.model_name = settings.get("model")
        self._update_llm_metrics_label()

        svc = LLMService(
            model_name=settings['model'],
            timeout=settings.get("llm_timeout"),
        )
        self.worker = TranslationWorker(
            segments=self.segments,
            target_lang=settings['lang'],
            llm_service=svc,
            glossary_path=settings['glossary_path'],
            style_path=settings['style_path'],
            forbidden_path=settings['forbidden_path'],
            prompt_template=settings['prompt_template'],
            project_name=settings.get('project_name', 'default'),
            temp=settings['temp'],
            strict=settings["strict_mode"],
        )
        self.worker.progress_signal.connect(self.update_row_ui)
        self.worker.finished_signal.connect(self.on_done)
        self.worker.start()

    def bulk_lock_selected(self, indices):
        settings = self.settings_tab.get_settings()
        lang = settings.get('lang', 'BG')
        project_name = settings.get(
            'project_name', settings.get('project', 'default'))
        for idx in indices:
            row = idx.row()
            seg = self.segments[row]
            # Pass all current flags to database
            save_translation(
                seg.source_text,
                lang,
                seg.translation,
                project_name=project_name,
                segment_key=seg.key,
                verified=seg.is_verified,
                skip=seg.never_translate,
                ai_draft=getattr(seg, 'ai_draft', ""),
            )
            self.update_row_visuals(row)
        self.update_stats()

    def restore_from_history_list(self, item):
        """When you double-click a history item, it puts it in the editor."""
        version_text = item.text()
        self.apply_history_suggestion(version_text)

    def rollback_to_ai(self):
        """Restores the translation to the original AI draft."""
        if self.current_row < 0:
            return
        seg = self.segments[self.current_row]

        if seg.ai_draft:
            self.editor.trans_edit.setPlainText(seg.ai_draft)
            self.thought_log.append(I18N.t("log_rollback_ai"))
        else:
            QMessageBox.information(
                self,
                I18N.t("dlg_no_history_title"),
                I18N.t("msg_no_ai_draft"),
            )

    def bulk_skip_selected(self, indices):
        """Marks all selected rows as 'Never Translate'."""
        reply = QMessageBox.question(
            self,
            I18N.t("dlg_never_translate_title"),
            I18N.t("msg_never_translate_confirm").format(count=len(indices)),
        )
        if reply == QMessageBox.StandardButton.Yes:
            settings = self.settings_tab.get_settings()
            lang = settings.get('lang', 'BG')
            project_name = settings.get(
                'project_name', settings.get('project', 'default'))
            for idx in indices:
                row = idx.row()
                seg = self.segments[row]
                # In 'Skip' mode, we usually keep the original source as the translation
                seg.translation = seg.source_text
                seg.is_verified = False
                seg.never_translate = True
                seg.thought = I18N.t("thought_never_translate_bulk")
                # skip=True tells the DB to never send this to LLM
                save_translation(
                    seg.source_text,
                    lang,
                    seg.translation,
                    project_name=project_name,
                    segment_key=seg.key,
                    verified=False,
                    skip=True,
                    ai_draft=getattr(seg, 'ai_draft', ""),
                )
                self.update_row_visuals(row)
            self.update_stats()

    def bulk_unverify_selected(self, indices):
        """Reverts verified rows back to 'AI Draft' state."""
        settings = self.settings_tab.get_settings()
        lang = settings.get('lang', 'BG')
        project_name = settings.get(
            'project_name', settings.get('project', 'default'))
        for idx in indices:
            row = idx.row()
            seg = self.segments[row]
            seg.is_verified = False
            # Save to DB with verified=False
            save_translation(
                seg.source_text,
                lang,
                seg.translation,
                project_name=project_name,
                segment_key=seg.key,
                verified=False,
                skip=seg.never_translate,
                ai_draft=getattr(seg, 'ai_draft', ""),
            )
            self.update_row_visuals(row)
        self.update_stats()

    def export_verified_glossary(self):
        """Export all Verified (Green) segments into a project/lang-scoped glossary TSV.

        - Default name: {project_name}_{lang}_verified_glossary.tsv
        - Appends to existing file instead of overwriting.
        - Skips duplicates (same term + translation).
        - Strips technical tags (<...>, [...], {...}, @@PLACEHOLDER_0@@) and normalizes whitespace.
        """
        # 1) Collect verified segments
        verified_segments = [
            s for s in self.segments if getattr(s, "is_verified", False)]
        if not verified_segments:
            QMessageBox.warning(
                self,
                I18N.t("dlg_export_title"),
                I18N.t("msg_export_no_verified"),
            )
            return

        # 2) Build default filename from project + language
        settings = self.settings_tab.get_settings()
        project_name = settings.get("project_name", "default")
        lang = settings.get("lang", "BG").lower()
        default_name = f"{project_name}_{lang}_verified_glossary.tsv"

        # 3) Ask user where to save
        path, _ = QFileDialog.getSaveFileName(
            self,
            I18N.t("dlg_save_verified_glossary_title"),
            default_name,
            I18N.t("filter_tsv"),
        )
        if not path:
            return

        # 5) Load existing term/translation pairs to avoid duplicates
        existing_pairs: set[tuple[str, str]] = set()
        file_exists = os.path.exists(path)
        file_nonempty = file_exists and os.path.getsize(path) > 0

        if file_nonempty:
            try:
                with open(path, "r", encoding="utf-8", newline="") as f:
                    reader = csv.reader(f, delimiter="\t")
                    # Skip header if present
                    header_skipped = False
                    for row in reader:
                        if not header_skipped:
                            header_skipped = True
                            # crude check: if header looks like "term" "translation", skip it
                            if len(row) >= 2 and row[0].lower() == "term":
                                continue
                        if len(row) >= 2:
                            term = row[0].strip()
                            trans = row[1].strip()
                            if term and trans:
                                existing_pairs.add((term, trans))
            except (OSError, csv.Error) as e:
                QMessageBox.critical(
                    self,
                    I18N.t("dlg_export_error_title"),
                    I18N.t("msg_export_read_failed").format(error=e),
                )
                return

        # 6) Append new lines without duplicates
        exported_count = 0
        file_empty = not file_exists or not file_nonempty

        try:
            with open(path, "a", encoding="utf-8", newline="") as f:
                if file_empty:
                    f.write("term\ttranslation\n")

                for seg in verified_segments:
                    # Clean tags from source and translation
                    raw_src = seg.source_text or ""
                    raw_trans = seg.translation or ""

                    src = strip_tags(raw_src)
                    trans = strip_tags(raw_trans)

                    # Whitespace crunch: collapse multiple spaces and trim
                    src = " ".join(src.split()).strip()
                    trans = " ".join(trans.split()).strip()

                    if not src or not trans:
                        continue

                    key = (src, trans)
                    if key in existing_pairs:
                        continue  # already present

                    f.write(f"{src}\t{trans}\n")
                    existing_pairs.add(key)
                    exported_count += 1
        except OSError as e:
            QMessageBox.critical(
                self,
                I18N.t("dlg_export_error_title"),
                I18N.t("msg_export_write_failed").format(error=e),
            )
            return

        # 7) User feedback
        if exported_count > 0:
            QMessageBox.information(
                self,
                I18N.t("dlg_export_complete_title"),
                I18N.t("msg_export_complete").format(
                    count=exported_count,
                    filename=os.path.basename(path),
                ),
            )
        else:
            QMessageBox.information(
                self,
                I18N.t("dlg_export_no_new_terms_title"),
                I18N.t("msg_export_no_new_terms"),
            )

    def update_row_ui(self, val):
        self.progress_bar.setValue(val)
        self._batch_metrics.processed_rows = max(
            self._batch_metrics.processed_rows,
            val,
        )
        self.update_row_visuals(val - 1)
        self.update_stats()
        if self.cb_follow.isChecked():
            self.table.setCurrentCell(val - 1, 1)

    def on_done(self, result):
        self._bulk_stopping = False
        self.btn_run.setEnabled(True)
        self.btn_run.setText(I18N.t("ui_start_bulk"))
        self.btn_run.setStyleSheet("font-weight: bold;")
        self.save_ui_state()
        self.settings_tab.save_settings()
        self._tally_llm_failures(result)
        if self._batch_metrics.started_at is not None:
            self._batch_metrics.duration_seconds = (
                time.monotonic() - self._batch_metrics.started_at
            )
            if self._batch_metrics.processed_rows > 0:
                self._batch_metrics.avg_seconds = (
                    self._batch_metrics.duration_seconds
                    / self._batch_metrics.processed_rows
                )
            else:
                self._batch_metrics.avg_seconds = None
            self._batch_metrics.started_at = None
            self._update_llm_metrics_label()

        parser = FoundryParser()
        settings = self.settings_tab.get_settings()
        out = Path("out") / settings['lang'] / self.input_path.name
        parser.save_tsv(result, out)
        self.file_label.setText(
            I18N.t("msg_file_saved").format(path=out)
        )

    @staticmethod
    def _count_llm_requests(segments) -> int:
        return sum(
            1
            for seg in segments
            if getattr(seg, "source_text", "").strip()
        )

    def _tally_llm_failures(self, segments) -> None:
        failures = sum(
            1
            for seg in segments
            if (getattr(seg, "translation", "") or "").startswith(TAG_ERROR_PREFIX)
        )
        if failures:
            self.llm_failure_count += failures
            self._update_llm_metrics_label()

    def save_ui_state(self):
        """Saves window geometry, splitter, table header, and current tab."""
        settings = QSettings("FoundryL10n", "Workstation")

        # Window position/size/state
        settings.setValue("window_geometry", self.saveGeometry())
        settings.setValue("window_state", self.saveState())

        # Splitter layout
        settings.setValue("splitter_sizes", self.splitter.saveState())

        # Table header (column widths, order, etc.)
        settings.setValue("table_header_state",
                          self.table.horizontalHeader().saveState())

        # Active tab index
        settings.setValue("current_tab", self.tabs.currentIndex())

    def load_ui_state(self):
        """
        Restores window geometry, splitter, table header, and current tab safely.
        Includes a safety check to ensure the window fits on the current screen.
        """
        settings = QSettings("FoundryL10n", "Workstation")
        try:
            # 1) Restore window geometry (position and size)
            geom = settings.value("window_geometry")
            if geom is not None:
                self.restoreGeometry(geom)

            # 2) TV/Screen Safety Check: 
            # If the restored geometry is larger than the actual TV/Monitor resolution,
            # or if it's positioned off-screen, force it to a safe default.
            screen_geo = self.screen().availableGeometry()
            if self.width() > screen_geo.width() or self.height() > screen_geo.height():
                # Fallback to a safe workstation size if the saved state is "impossible"
                self.resize(1200, 800)
                # Center the window on the current screen
                self.move(
                    (screen_geo.width() - self.width()) // 2,
                    (screen_geo.height() - self.height()) // 2
                )

            # 3) Restore internal window state (maximized, etc.)
            state = settings.value("window_state")
            if state is not None:
                self.restoreState(state)

            # 4) Restore splitter layout (Table vs Editor ratio)
            splitter_state = settings.value("splitter_sizes")
            if splitter_state is not None:
                self.splitter.restoreState(splitter_state)

            # 5) Restore table header state (Column widths)
            header_state = settings.value("table_header_state")
            if header_state is not None:
                self.table.horizontalHeader().restoreState(header_state)

            # 6) Restore active tab with Pylance-safe casting
            raw_tab = settings.value("current_tab", 0)
            idx = int(str(raw_tab))
            if 0 <= idx < self.tabs.count():
                self.tabs.setCurrentIndex(idx)

        except Exception as exc:
            # We use a simple print here so startup doesn't crash if config is corrupted
            print(f"UI Restore Warning: {exc}")

    def retranslate_ui(self):
        self.setWindowTitle(f"FoundryL10n - {I18N.t('ui_workstation')}")

        if hasattr(self, "translate_tab"):
            self.tabs.setTabText(
                self.tabs.indexOf(self.translate_tab),
                I18N.t("ui_workstation"),
            )
        self.tabs.setTabText(
            self.tabs.indexOf(self.settings_tab),
            I18N.t("tab_settings"),
        )
        if hasattr(self, "integrity_tab"):
            self.tabs.setTabText(
                self.tabs.indexOf(self.integrity_tab),
                I18N.t("tab_integrity"),
            )
        if hasattr(self, "metrics_tab"):
            self.tabs.setTabText(
                self.tabs.indexOf(self.metrics_tab),
                I18N.t("tab_metrics"),
            )

        self.btn_open.setText(I18N.t("btn_import_tsv"))
        self.btn_export_tsv.setText(I18N.t("btn_export_tsv"))
        if not self._file_loaded:
            self.file_label.setText(I18N.t("ui_no_file_selected"))
        self.search_label.setText(I18N.t("ui_search_label"))
        self.search_bar.setPlaceholderText(I18N.t("ui_search_placeholder"))
        self.cb_only_errors.setText(I18N.t("ui_show_only_errors"))
        self.btn_toggle_editor.setText(I18N.t("btn_toggle_editor"))
        self.btn_zen.setText(I18N.t("btn_zen_mode"))
        self.btn_reverse_zen.setText(I18N.t("btn_reverse_zen_mode"))
        self.cb_follow.setText(I18N.t("ui_follow"))
        if hasattr(self, "metrics_tab"):
            self.metrics_header_label.setText(I18N.t("metrics_title"))
            self.metrics_intro_label.setText(I18N.t("metrics_intro"))
            self.metrics_stats_title.setText(I18N.t("metrics_qa_title"))
            self.metrics_llm_title.setText(I18N.t("metrics_llm_title"))
            self.metrics_accuracy_title.setText(I18N.t("metrics_accuracy_title"))

        self.table.setHorizontalHeaderLabels(
            [
                I18N.t("header_state"),
                I18N.t("header_key"),
                I18N.t("header_source"),
                I18N.t("ui_translation"),
            ]
        )

        self._update_run_button_text()
        if hasattr(self, "editor"):
            if hasattr(self.editor, "retranslate_ui"):
                self.editor.retranslate_ui()
            self._update_translate_button_text()

        self._update_context_menu_texts(self._context_menu_count)
        self.action_fetch_segments.setText(I18N.t("menu_sync_fetch"))
        self.action_submit_suggestion.setText(I18N.t("menu_sync_submit"))
        self.action_submit_verified.setText(I18N.t("menu_sync_submit_verified"))
        self.action_sync_plugins.setText(I18N.t("menu_sync_plugins"))
        if hasattr(self, "sync_menu"):
            self.sync_menu.setTitle(I18N.t("menu_sync"))
        self.update_stats()

        if hasattr(self.settings_tab, "retranslate_ui"):
            self.settings_tab.retranslate_ui()
        if hasattr(self, "integrity_tab") and hasattr(
            self.integrity_tab, "retranslate_ui"
        ):
            self.integrity_tab.retranslate_ui()
        if hasattr(self, "metrics_tab"):
            self._update_llm_metrics_label()

    def closeEvent(self, event):
        """Stops all threads and saves settings before exiting."""
        # 1. Save UI State
        self.save_ui_state()
        self.settings_tab.save_settings()

        # 2. Force Stop the Worker
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()  # Tell it to stop the loop
            self.worker.terminate()  # Force kill the thread if it's stuck in Ollama
            self.worker.wait()  # Wait for cleanup

        event.accept()


def run_gui():
    app = QApplication(sys.argv)
    window = FoundryGUI()
    window.show()
    sys.exit(app.exec())
