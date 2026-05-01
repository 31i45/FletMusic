#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FletMusic - 极简音乐播放器
"""

import time
import asyncio
import os
import tempfile
import urllib.request
from typing import Optional, Dict, List, Any, Callable, Awaitable
from dataclasses import dataclass
from functools import wraps
from enum import Enum
import flet as ft
from pyncm import apis
from pyncm.apis import cloudsearch
import pygame


class ViewType(Enum):
    PLAYLISTS = "playlists"
    SONGS = "songs"


@dataclass
class UIConfig:
    GRID_RUNS_COUNT: int = 2
    GRID_MAX_EXTENT: int = 240
    GRID_SPACING: int = 12
    COVER_SIZE_LARGE: int = 180
    COVER_SIZE_SMALL: int = 64
    COVER_SIZE_LIST: int = 56
    DEFAULT_KEYWORD: str = "华语经典"
    CACHE_EXPIRE_TIME: int = 3600
    DEFAULT_LIMIT: int = 50


BLACK = ft.Colors.BLACK
WHITE = ft.Colors.WHITE
GRAY = ft.Colors.GREY_400
LIGHT_GRAY = ft.Colors.GREY_200
PRIMARY = ft.Colors.BLUE_500


@dataclass
class CacheEntry:
    value: Any
    expire_time: float


def cached(expire_time: int = UIConfig.CACHE_EXPIRE_TIME):
    def decorator(func: Callable[..., Awaitable[Any]]):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"
            
            if not hasattr(self, '_cache'):
                self._cache = {}
            
            if cache_key in self._cache:
                entry = self._cache[cache_key]
                if entry.expire_time > time.time():
                    return entry.value
            
            result = await func(self, *args, **kwargs)
            self._cache[cache_key] = CacheEntry(
                value=result,
                expire_time=time.time() + expire_time
            )
            return result
        return wrapper
    return decorator


def format_duration(duration_ms: int) -> str:
    if duration_ms > 0:
        seconds = duration_ms // 1000
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}:{secs:02d}"
    return ""


def filter_free_songs(songs: List[Dict]) -> List[Dict]:
    return [s for s in songs if isinstance(s, dict) and s.get("fee", 0) == 0] if songs else []


def validate_song_id(song_id: int) -> bool:
    return isinstance(song_id, int) and song_id > 0


def validate_playlist_id(playlist_id: int) -> bool:
    return isinstance(playlist_id, int) and playlist_id > 0


def validate_search_keyword(keyword: str) -> str:
    if not isinstance(keyword, str) or keyword.strip() == "":
        return UIConfig.DEFAULT_KEYWORD
    return keyword.strip()


class PlayQueueManager:
    def __init__(self, play_song_callback):
        self._queue: List[Dict] = []
        self._current_index: int = -1
        self._play_song = play_song_callback

    @property
    def queue(self) -> List[Dict]:
        return self._queue

    @queue.setter
    def queue(self, songs: List[Dict]):
        self._queue = songs
        self._current_index = -1

    @property
    def current_index(self) -> int:
        return self._current_index

    @current_index.setter
    def current_index(self, idx: int):
        if 0 <= idx < len(self._queue):
            self._current_index = idx

    async def try_play_from(self, start_idx: int) -> bool:
        for i in range(start_idx, len(self._queue)):
            song_id = self._queue[i].get("id")
            success = await self._play_song(song_id)
            if success:
                self._current_index = i
                return True
        return False

    async def play_next(self) -> bool:
        return await self.try_play_from(self._current_index + 1)

    async def play_from_beginning(self) -> bool:
        return await self.try_play_from(0)

    def remove_song(self, song_id: int):
        for i, s in enumerate(self._queue):
            if s.get("id") == song_id:
                del self._queue[i]
                if self._current_index > i:
                    self._current_index -= 1
                break


class AudioCache:
    def __init__(self):
        self.temp_dir = tempfile.gettempdir()

    def get_cache_path(self, song_id: int) -> str:
        return os.path.join(self.temp_dir, f"flet_music_{song_id}.Music_31107")

    def is_cached(self, song_id: int) -> bool:
        return os.path.exists(self.get_cache_path(song_id))

    async def download(self, song_id: int, song_url: str) -> str:
        cache_path = self.get_cache_path(song_id)
        if self.is_cached(song_id):
            return cache_path
        await asyncio.to_thread(urllib.request.urlretrieve, song_url, cache_path)
        return cache_path


class AudioPlayer:
    def __init__(self):
        self.is_initialized = False
        self.is_playing = False
        self.playback_finished = False
        self.current_position_ms = 0
        self.current_duration_ms = 0
        self.current_file: Optional[str] = None
        self.progress_task: Optional[asyncio.Task] = None
        self.on_play_complete: Optional[Callable[[], Awaitable[None]]] = None
        self._progress_running = False

    def _ensure_initialized(self):
        if not self.is_initialized:
            pygame.mixer.init()
            self.is_initialized = True

    def stop(self):
        try:
            self.is_playing = False
            self.playback_finished = False
            self._stop_progress_task()
            pygame.mixer.music.stop()
            pygame.mixer.music.unload()
            time.sleep(0.1)
        except Exception:
            pass

    def pause(self):
        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False

    def unpause(self):
        if not self.is_playing and not self.playback_finished:
            pygame.mixer.music.unpause()
            self.is_playing = True

    async def play_file(self, file_path: str, duration_ms: int):
        self.stop()
        self._ensure_initialized()
        
        self.current_file = file_path
        self.current_duration_ms = duration_ms
        self.current_position_ms = 0
        self.playback_finished = False
        
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        self.is_playing = True
        self._start_progress_task()

    def replay(self):
        if self.current_file and os.path.exists(self.current_file):
            pygame.mixer.music.load(self.current_file)
            pygame.mixer.music.play()
            self.current_position_ms = 0
            self.playback_finished = False
            self.is_playing = True
            self._start_progress_task()

    def _start_progress_task(self):
        if self.progress_task and not self.progress_task.done():
            return
        self._progress_running = True
        self.progress_task = asyncio.create_task(self._update_progress())

    def _stop_progress_task(self):
        self._progress_running = False
        if self.progress_task and not self.progress_task.done():
            self.progress_task.cancel()
            self.progress_task = None

    async def _update_progress(self):
        while self._progress_running:
            await asyncio.sleep(0.5)
            if not self._progress_running:
                break
            try:
                if self.is_playing:
                    if pygame.mixer.music.get_busy():
                        self.current_position_ms = pygame.mixer.music.get_pos()
                    else:
                        self.is_playing = False
                        self.playback_finished = True
                        self._stop_progress_task()
                        if self.on_play_complete:
                            asyncio.create_task(self.on_play_complete())
            except Exception:
                break


class PlayerUI:
    def __init__(self, page: ft.Page, audio_player: AudioPlayer, on_replay_all: Optional[Callable[[], None]] = None):
        self.page = page
        self.audio_player = audio_player
        self.on_replay_all = on_replay_all
        self._running = True
        
        self.play_button = ft.IconButton(
            icon=ft.Icons.PLAY_CIRCLE,
            icon_size=48,
            icon_color=PRIMARY,
            on_click=self._toggle_play,
            disabled=True
        )
        self.song_title = ft.Text("点击歌曲播放", size=16, weight="bold", color=GRAY)
        self.song_artist = ft.Text("", size=12, color=GRAY)
        self.progress_bar = ft.ProgressBar(
            value=0, bgcolor=ft.Colors.with_opacity(0.12, BLACK),
            color=ft.Colors.with_opacity(0.85, PRIMARY),
            height=6, border_radius=3
        )
        self.time_current = ft.Text("0:00", size=11, color=ft.Colors.with_opacity(0.75, BLACK))
        self.time_total = ft.Text("0:00", size=11, color=ft.Colors.with_opacity(0.75, BLACK))
        self.song_cover = ft.Image(
            src="https://via.placeholder.com/64",
            width=UIConfig.COVER_SIZE_SMALL,
            height=UIConfig.COVER_SIZE_SMALL,
            fit="cover",
            border_radius=8
        )
        
        self._setup_progress_updater()

    def dispose(self):
        self._running = False

    def _setup_progress_updater(self):
        asyncio.create_task(self._update_ui_loop())

    async def _update_ui_loop(self):
        while self._running:
            await asyncio.sleep(0.25)
            if self._running:
                self._update_ui()

    def _update_ui(self):
        self.play_button.icon = ft.Icons.PAUSE_CIRCLE if self.audio_player.is_playing else ft.Icons.PLAY_CIRCLE
        
        if self.audio_player.current_duration_ms > 0:
            progress = min(
                self.audio_player.current_position_ms / self.audio_player.current_duration_ms,
                1.0
            )
            self.progress_bar.value = progress
            self.time_current.value = format_duration(self.audio_player.current_position_ms)
        
        try:
            self.page.update()
        except (RuntimeError, Exception):
            self._running = False

    def update_song_info(self, song: Dict[str, Any]):
        if not isinstance(song, dict):
            return
            
        song_name = song.get("name", "未知歌曲")
        artists = song.get("ar", [])
        artist_name = ", ".join([a.get("name", "未知歌手") for a in artists]) if artists else ""
        duration = song.get("dt", 0)
        
        self.audio_player.current_duration_ms = duration
        self.time_total.value = format_duration(duration)
        self.song_title.value = song_name
        self.song_title.color = BLACK
        self.song_artist.value = artist_name
        
        cover_url = song.get("al", {}).get("picUrl")
        if cover_url:
            self.song_cover.src = f"{cover_url}?param={UIConfig.COVER_SIZE_SMALL}x{UIConfig.COVER_SIZE_SMALL}"
        
        self.play_button.disabled = False
        self.page.update()

    def _toggle_play(self, _):
        if not self.audio_player.current_file:
            return
        
        if self.audio_player.is_playing:
            self.audio_player.pause()
        else:
            if self.audio_player.playback_finished:
                if self.on_replay_all:
                    self.on_replay_all()
                else:
                    self.audio_player.replay()
            elif pygame.mixer.music.get_pos() > 0:
                self.audio_player.unpause()
            else:
                self.audio_player.replay()
        
        self._update_ui()

    def get_ui(self) -> ft.Container:
        return ft.Container(
            content=ft.Row([
                self.song_cover, ft.Container(width=12),
                ft.Column([self.song_title, self.song_artist], spacing=2, alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(width=16),
                ft.Container(
                    content=ft.Row([
                        ft.Container(content=self.time_current, padding=ft.Padding.only(left=8, top=3, right=8, bottom=3),
                                     bgcolor=ft.Colors.with_opacity(0.12, BLACK), border_radius=6),
                        ft.Container(width=8),
                        ft.Container(content=self.progress_bar, expand=True, padding=ft.Padding.only(left=4, top=8, right=4, bottom=8),
                                     bgcolor=ft.Colors.with_opacity(0.12, BLACK), border_radius=12),
                        ft.Container(width=8),
                        ft.Container(content=self.time_total, padding=ft.Padding.only(left=8, top=3, right=8, bottom=3),
                                     bgcolor=ft.Colors.with_opacity(0.12, BLACK), border_radius=6),
                    ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding.only(left=12, top=8, right=12, bottom=8), bgcolor=ft.Colors.with_opacity(0.06, BLACK),
                    border_radius=12, expand=True
                ),
                ft.Container(width=16), self.play_button
            ], spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.only(left=16, top=14, right=16, bottom=14), bgcolor=WHITE,
            shadow=ft.BoxShadow(
                blur_radius=12, spread_radius=2, offset=ft.Offset(0, -4),
                color=ft.Colors.with_opacity(0.12, BLACK)
            )
        )


class MusicPlayer:
    def __init__(self, page: ft.Page, on_replay_all: Optional[Callable[[], None]] = None):
        self.page = page
        self.audio_cache = AudioCache()
        self.audio_player = AudioPlayer()
        self.player_ui = PlayerUI(page, self.audio_player, on_replay_all)

    @property
    def on_play_complete(self):
        return self.audio_player.on_play_complete

    @on_play_complete.setter
    def on_play_complete(self, callback):
        self.audio_player.on_play_complete = callback

    async def play(self, song: Dict[str, Any], song_url: str):
        self.player_ui.update_song_info(song)
        song_id = song.get("id", 0)
        cache_path = await self.audio_cache.download(song_id, song_url)
        duration = song.get("dt", 0)
        await self.audio_player.play_file(cache_path, duration)

    def get_ui(self) -> ft.Container:
        return self.player_ui.get_ui()


class MusicAPI:
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._song_index: Dict[int, Dict[str, Any]] = {}

    def _update_song_index(self, tracks: List[Dict[str, Any]]):
        for track in tracks:
            if isinstance(track, dict):
                song_id = track.get("id")
                if validate_song_id(song_id):
                    self._song_index[song_id] = track

    def find_song_info(self, song_id: int) -> Optional[Dict[str, Any]]:
        return self._song_index.get(song_id) if validate_song_id(song_id) else None

    @cached()
    async def search_playlists(self, keyword: str = UIConfig.DEFAULT_KEYWORD,
                              limit: int = UIConfig.DEFAULT_LIMIT) -> List[Dict[str, Any]]:
        keyword = validate_search_keyword(keyword)
        try:
            result = await asyncio.to_thread(
                cloudsearch.GetSearchResult, keyword,
                stype=cloudsearch.PLAYLIST, limit=limit
            )
            if result.get("code") == 200:
                return result.get("result", {}).get("playlists", [])
            return []
        except Exception:
            return []

    @cached()
    async def search_songs(self, keyword: str = "",
                          limit: int = UIConfig.DEFAULT_LIMIT) -> List[Dict[str, Any]]:
        keyword = validate_search_keyword(keyword)
        try:
            result = await asyncio.to_thread(
                cloudsearch.GetSearchResult, keyword,
                stype=cloudsearch.SONG, limit=limit
            )
            if result.get("code") == 200:
                songs = result.get("result", {}).get("songs", [])
                self._update_song_index(songs)
                return songs
            return []
        except Exception:
            return []

    @cached()
    async def get_playlist_tracks(self, playlist_id: int) -> List[Dict[str, Any]]:
        if not validate_playlist_id(playlist_id):
            return []
        try:
            result = await asyncio.to_thread(apis.playlist.GetPlaylistInfo, playlist_id)
            if result.get("code") == 200:
                tracks = result.get("playlist", {}).get("tracks", [])
                self._update_song_index(tracks)
                return tracks
            return []
        except Exception:
            return []

    async def get_song_url(self, song_id: int) -> Optional[str]:
        if not validate_song_id(song_id):
            return None
        try:
            result = await asyncio.to_thread(apis.track.GetTrackAudio, song_id)
            if result.get("code") == 200:
                data = result.get("data", [])
                if data:
                    track_data = data[0]
                    url = track_data.get("url")
                    free_trial_info = track_data.get("freeTrialInfo")
                    if free_trial_info is not None or not url:
                        return None
                    return url
            return None
        except Exception:
            return None


class UIManager:
    def __init__(self, page: ft.Page, on_search_callback, on_switch_view_callback, on_playlist_click_callback):
        self.page = page
        self.on_search = on_search_callback
        self.on_switch_view = on_switch_view_callback
        self.on_playlist_click = on_playlist_click_callback
        
        self.search_input: Optional[ft.TextField] = None
        self.playlists_grid: Optional[ft.GridView] = None
        self.songs_grid: Optional[ft.GridView] = None
        self.main_container: Optional[ft.Column] = None
        self.playlists_button: Optional[ft.Button] = None
        self.songs_button: Optional[ft.Button] = None

    @staticmethod
    def _create_button(text: str, on_click, is_active: bool = False) -> ft.Button:
        return ft.Button(
            content=ft.Text(text, color=WHITE if is_active else BLACK),
            on_click=on_click,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                bgcolor=PRIMARY if is_active else LIGHT_GRAY
            ),
        )

    @staticmethod
    def _create_cover_card(data: Dict, on_click, is_playlist: bool = True) -> ft.Card:
        if not isinstance(data, dict):
            data = {}
            
        if is_playlist:
            cover_url = data.get("coverImgUrl", "https://via.placeholder.com/200")
            title = data.get("name", "未知歌单")
            subtitle = f"{data.get('trackCount', 0)}首歌曲"
            duration_text = ""
        else:
            cover_url = data.get("al", {}).get("picUrl", "https://via.placeholder.com/200")
            title = data.get("name", "未知歌曲")
            artists = data.get("ar", [])
            subtitle = ", ".join([a.get("name", "未知歌手") for a in artists]) if artists else ""
            duration = data.get("dt", 0)
            duration_text = format_duration(duration)
        
        if cover_url:
            cover_url += "?param=200x200"
        
        image_area = ft.Container(
            width=UIConfig.COVER_SIZE_LARGE,
            height=UIConfig.COVER_SIZE_LARGE,
            content=ft.Stack([
                ft.Image(
                    src=cover_url, width=UIConfig.COVER_SIZE_LARGE,
                    height=UIConfig.COVER_SIZE_LARGE, fit="cover",
                    error_content=ft.Image(src="https://via.placeholder.com/180"),
                ),
            ] + ([
                ft.Container(
                    content=ft.Text(duration_text, size=12, color=WHITE, weight="bold"),
                    bgcolor=ft.Colors.with_opacity(0.7, BLACK),
                    padding=ft.Padding.only(left=6, top=3, right=6, bottom=3), border_radius=4,
                    right=8, bottom=8,
                )
            ] if duration_text and not is_playlist else [])),
        )
        
        return ft.Card(
            content=ft.GestureDetector(
                content=ft.Container(
                    content=ft.Column([
                        image_area,
                        ft.Container(
                            content=ft.Column([
                                ft.Text(title, size=14, color=BLACK, weight="bold", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                                ft.Text(subtitle, size=12, color=GRAY),
                            ], spacing=5),
                            padding=10,
                        ),
                    ], spacing=0),
                    width=UIConfig.COVER_SIZE_LARGE, padding=0,
                ),
                on_tap=on_click,
            ),
        )

    @staticmethod
    def _create_song_list_item(track: Dict) -> ft.Row:
        def _create_tag(text: str) -> ft.Container:
            return ft.Container(
                content=ft.Text(text, size=11, color=ft.Colors.with_opacity(0.85, BLACK)),
                padding=ft.Padding.only(left=6, top=2, right=6, bottom=2),
                bgcolor=ft.Colors.with_opacity(0.05, BLACK),
                border_radius=4,
            )
        
        if isinstance(track, dict):
            song_name = track.get("name", "未知歌曲")
            artists = track.get("ar", [])
            artist_names = ", ".join([a.get("name", "未知歌手") for a in artists])
            cover_url = track.get("al", {}).get("picUrl", "https://via.placeholder.com/56")
            duration = track.get("dt", 0)
        else:
            song_name = f"歌曲ID: {track}"
            artist_names = "未知歌手"
            cover_url = "https://via.placeholder.com/56"
            duration = 0
        
        if cover_url:
            cover_url += f"?param={UIConfig.COVER_SIZE_LIST}x{UIConfig.COVER_SIZE_LIST}"
        
        duration_text = format_duration(duration)
        
        tags = [_create_tag(artist_names)]
        if duration_text:
            tags.extend([ft.Container(width=8), _create_tag(duration_text)])
        
        return ft.Row([
            ft.Image(
                src=cover_url, width=UIConfig.COVER_SIZE_LIST,
                height=UIConfig.COVER_SIZE_LIST, fit="cover",
                error_content=ft.Image(src="https://via.placeholder.com/56"),
            ),
            ft.Column([
                ft.Text(song_name, size=16, color=BLACK, weight="bold"),
                ft.Row(tags, spacing=0),
            ], spacing=4, expand=True, alignment=ft.MainAxisAlignment.CENTER),
        ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER)

    def setup_main_page(self):
        self.page.controls.clear()
        
        self.search_input = ft.TextField(hint_text="搜索", border=ft.InputBorder.UNDERLINE, text_size=16, width=180, on_submit=self.on_search)
        
        header = ft.Container(
            content=ft.Row([
                ft.Text("免费听整首歌曲", size=22, color=BLACK, weight="bold"),
                ft.Container(expand=True),
                ft.Row([
                    self.search_input,
                    ft.Container(width=8),
                    self._create_button("搜索", on_click=self.on_search, is_active=True),
                ], spacing=0),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.Padding.only(left=16, top=16, right=16, bottom=12), bgcolor=WHITE
        )
        
        self.playlists_button = self._create_button(
            "歌单",
            on_click=lambda _: self.on_switch_view(ViewType.PLAYLISTS),
            is_active=True
        )
        self.songs_button = self._create_button(
            "单曲",
            on_click=lambda _: self.on_switch_view(ViewType.SONGS)
        )
        
        view_buttons = ft.Container(
            content=ft.Row([self.playlists_button, self.songs_button], spacing=12, alignment=ft.MainAxisAlignment.CENTER),
            padding=ft.Padding.only(left=16, top=8, right=16, bottom=8), bgcolor=WHITE
        )
        
        self.playlists_grid = ft.GridView(
            expand=True, runs_count=UIConfig.GRID_RUNS_COUNT,
            max_extent=UIConfig.GRID_MAX_EXTENT, spacing=UIConfig.GRID_SPACING,
            run_spacing=UIConfig.GRID_SPACING
        )
        self.songs_grid = ft.GridView(
            expand=True, runs_count=UIConfig.GRID_RUNS_COUNT,
            max_extent=UIConfig.GRID_MAX_EXTENT, spacing=UIConfig.GRID_SPACING,
            run_spacing=UIConfig.GRID_SPACING
        )
        
        self.main_container = ft.Column(expand=True)
        self.main_container.controls.append(self.playlists_grid)
        
        return ft.Column([header, view_buttons, self.main_container], expand=True)

    def show_tracks_page(self, playlist_name: str, on_back_callback):
        self.page.controls.clear()
        
        list_view = ft.ListView(
            expand=True, spacing=8,
            padding=ft.Padding.only(left=16, top=12, right=16, bottom=12)
        )
        
        header = ft.Container(
            content=ft.Row([
                self._create_button("返回", on_click=on_back_callback, is_active=True),
                ft.Text(playlist_name, size=20, color=BLACK, weight="bold"),
            ], alignment=ft.MainAxisAlignment.START),
            padding=ft.Padding.only(left=16, top=16, right=16, bottom=12), bgcolor=WHITE
        )
        
        return ft.Column([header, list_view], expand=True), list_view

    def switch_view(self, view_type: ViewType):
        if self.main_container:
            self.main_container.controls.clear()
            if view_type == ViewType.PLAYLISTS:
                self.main_container.controls.append(self.playlists_grid)
                self._update_button_colors(True)
            else:
                self.main_container.controls.append(self.songs_grid)
                self._update_button_colors(False)
            self.page.update()

    def _update_button_colors(self, is_playlists_active: bool):
        if self.playlists_button:
            self.playlists_button.style.bgcolor = PRIMARY if is_playlists_active else LIGHT_GRAY
            self.playlists_button.content = ft.Text("歌单", color=WHITE if is_playlists_active else BLACK)
        if self.songs_button:
            self.songs_button.style.bgcolor = LIGHT_GRAY if is_playlists_active else PRIMARY
            self.songs_button.content = ft.Text("单曲", color=BLACK if is_playlists_active else WHITE)

    def get_search_keyword(self) -> str:
        return self.search_input.value.strip() if self.search_input else ""

    @staticmethod
    def show_loading(container):
        container.controls.clear()
        container.controls.append(ft.Text("加载中...", color=GRAY))

    @staticmethod
    def show_empty(container, message: str = "暂无可播放的免费歌曲"):
        container.controls.clear()
        container.controls.append(ft.Text(message, color=GRAY))

    @staticmethod
    def show_error(container, message: str):
        container.controls.clear()
        container.controls.append(ft.Text(message, color=ft.Colors.RED))

    def render_songs(self, songs: List[Dict], container, is_grid: bool, play_song_callback, play_queue):
        if not container:
            return

        container.controls.clear()
        if not songs:
            self.show_empty(container)
            self.page.update()
            return

        play_queue.queue = songs
        item_map: Dict[int, Any] = {}

        for idx, song in enumerate(songs):
            song_id = song.get("id")

            async def on_click_handler(_, sid=song_id, idx_copy=idx):
                success = await play_song_callback(sid)
                if success:
                    play_queue.current_index = idx_copy
                elif not success and sid in item_map:
                    container.controls.remove(item_map[sid])
                    del item_map[sid]
                    play_queue.remove_song(sid)
                    self.page.update()

            if is_grid:
                item = self._create_cover_card(song, on_click_handler, is_playlist=False)
            else:
                item = ft.GestureDetector(
                    content=self._create_song_list_item(song),
                    on_tap=on_click_handler
                )
            container.controls.append(item)
            item_map[song_id] = item

        self.page.update()

    def render_playlists(self, playlists: List[Dict], container, on_playlist_click):
        if not container:
            return
        
        container.controls.clear()
        if not playlists:
            self.show_empty(container, "暂无公共歌单")
        else:
            for pl in playlists:
                card = self._create_cover_card(
                    pl,
                    lambda _, pid=pl.get("id"), pname=pl.get("name"): asyncio.create_task(
                        on_playlist_click(pid, pname)
                    ),
                    is_playlist=True
                )
                container.controls.append(card)
        self.page.update()


class MusicPlayerApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "FletMusic"
        self.page.theme_mode = ft.ThemeMode.LIGHT
        self.page.bgcolor = LIGHT_GRAY
        self.page.padding = 0
        self.page.window_width = 480
        self.page.window_height = 800
        
        self.api = MusicAPI()
        self.search_keyword = UIConfig.DEFAULT_KEYWORD
        self.ui_manager = UIManager(page, self._on_search, self._on_switch_view, self._on_playlist_click)
        self.play_queue = PlayQueueManager(self.play_song)
        self.player = MusicPlayer(page, self._on_replay_all)
        self.player.on_play_complete = self._on_play_complete

    async def play_song(self, song_id: int) -> bool:
        if not validate_song_id(song_id):
            return False
        
        try:
            song_info = self.api.find_song_info(song_id)
            if not song_info:
                self._show_error("未找到歌曲信息")
                return False

            song_url = await self.api.get_song_url(song_id)
            if not song_url:
                self._show_error("这是一首试听歌曲，无法播放完整版本")
                return False

            await self.player.play(song_info, song_url)
            return True
        except Exception:
            return False

    def _show_error(self, message: str):
        self.page.snack_bar = ft.SnackBar(content=ft.Text(message))
        self.page.snack_bar.open = True
        self.page.update()

    async def load_playlists(self, keyword: str = UIConfig.DEFAULT_KEYWORD):
        keyword = validate_search_keyword(keyword)
        if not self.ui_manager.playlists_grid:
            return

        self.ui_manager.show_loading(self.ui_manager.playlists_grid)
        self.page.update()

        try:
            playlists = await self.api.search_playlists(keyword)
            self.ui_manager.render_playlists(playlists, self.ui_manager.playlists_grid, self._on_playlist_click)
        except Exception:
            self.ui_manager.show_error(self.ui_manager.playlists_grid, "加载歌单失败")

    async def load_songs(self, keyword: str = ""):
        keyword = validate_search_keyword(keyword)
        if not self.ui_manager.songs_grid:
            return

        self.ui_manager.show_loading(self.ui_manager.songs_grid)
        self.page.update()

        try:
            songs = await self.api.search_songs(keyword)
            filtered_songs = filter_free_songs(songs)
            self.ui_manager.render_songs(filtered_songs, self.ui_manager.songs_grid, True,
                                        self.play_song, self.play_queue)
        except Exception:
            self.ui_manager.show_error(self.ui_manager.songs_grid, "加载单曲失败")

    def _on_search(self, _):
        keyword = validate_search_keyword(self.ui_manager.get_search_keyword())
        self.search_keyword = keyword
        asyncio.create_task(self.load_playlists(keyword))
        asyncio.create_task(self.load_songs(keyword))

    def _on_switch_view(self, view_type: ViewType):
        self.ui_manager.switch_view(view_type)

    async def _on_playlist_click(self, playlist_id: int, playlist_name: str):
        if not validate_playlist_id(playlist_id):
            return

        main_content, list_view = self.ui_manager.show_tracks_page(playlist_name, self._show_main_page)
        self.page.add(ft.Column([main_content, self.player.get_ui()], expand=True))

        self.ui_manager.show_loading(list_view)
        self.page.update()

        try:
            tracks = await self.api.get_playlist_tracks(playlist_id)
            filtered_tracks = filter_free_songs(tracks)
            self.ui_manager.render_songs(filtered_tracks, list_view, False,
                                        self.play_song, self.play_queue)
        except Exception:
            self.ui_manager.show_error(list_view, "加载失败")
            self.page.update()

    def _show_main_page(self):
        main_content = self.ui_manager.setup_main_page()
        self.page.add(ft.Column([main_content, self.player.get_ui()], expand=True))
        asyncio.create_task(self.load_playlists(self.search_keyword))
        asyncio.create_task(self.load_songs(self.search_keyword))

    async def _on_play_complete(self):
        await self.play_queue.play_next()

    def _on_replay_all(self):
        if self.play_queue.queue:
            asyncio.create_task(self.play_queue.play_from_beginning())

    def run(self):
        self._show_main_page()


def main(page: ft.Page):
    app = MusicPlayerApp(page)
    app.run()


if __name__ == "__main__":
    ft.run(main, view=ft.AppView.FLET_APP)
