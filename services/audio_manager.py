"""
背景音乐管理模块 v2.2.0
基于 QMediaPlayer 实现单例音频控制，支持随机加载、播放、暂停、停止。
"""

import os
import random
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtCore import QUrl, QObject, Signal


class AudioManager(QObject):
    _instance = None
    state_changed = Signal(bool)  # 参数：是否正在播放

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setVolume(0.7)

        # 音乐播放结束后自动循环
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        # 监听播放状态变化（用于发射信号）
        self.player.playbackStateChanged.connect(self._on_playback_state_changed)

        self._initialized = True

    def _on_media_status_changed(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self.player.play()

    def _on_playback_state_changed(self, state):
        """当播放状态改变时发射信号"""
        is_playing = state == QMediaPlayer.PlayingState
        self.state_changed.emit(is_playing)

    def load(self, file_path):
        """加载指定路径的音频文件"""
        if os.path.exists(file_path):
            self.player.setSource(QUrl.fromLocalFile(os.path.abspath(file_path)))
            return True
        return False

    def load_random_from_folder(self, folder_path):
        """从文件夹随机选择音频文件并加载"""
        if not os.path.isdir(folder_path):
            return False
        exts = (".mp3", ".wav", ".flac", ".ogg", ".m4a")
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(exts)]
        if not files:
            return False
        chosen = random.choice(files)
        full_path = os.path.join(folder_path, chosen)
        return self.load(full_path)

    def play(self):
        if self.player.source().isValid():
            self.player.play()
            # 信号会在 playbackStateChanged 中自动发射

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.pause()
            return False
        else:
            self.play()
            return True

    def is_playing(self):
        return self.player.playbackState() == QMediaPlayer.PlayingState

    def set_volume(self, vol):
        self.audio_output.setVolume(max(0.0, min(1.0, vol)))
