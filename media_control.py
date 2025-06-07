# media_control.py

from winsdk.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager
)

class MediaController:
    def __init__(self):
        # don’t call request_async() yet
        self._mgr = None
        self._session = None

    def _ensure_mgr(self):
        if not self._mgr:
            try:
                op = GlobalSystemMediaTransportControlsSessionManager.request_async()
                self._mgr = op.get_results()
            except OSError as e:
                # “method called at unexpected time” → defer until next call
                self._mgr = None
                raise

    def _update_session(self):
        self._ensure_mgr()
        self._session = self._mgr.get_current_session()

    def play(self):
        try:
            self._update_session()
            if self._session:
                op = self._session.try_play_async()
                op.get_results()
        except OSError:
            # if we hit it again, we’ll just swallow and retry next time
            pass

    def pause(self):
        try:
            self._update_session()
            if self._session:
                op = self._session.try_pause_async()
                op.get_results()
        except OSError:
            pass

    def stop(self):
        try:
            self._update_session()
            if self._session:
                op = self._session.try_stop_async()
                op.get_results()
        except OSError:
            pass

    def next(self):
        try:
            self._update_session()
            if self._session:
                op = self._session.try_skip_next_async()
                op.get_results()
        except OSError:
            pass

    def previous(self):
        try:
            self._update_session()
            if self._session:
                op = self._session.try_skip_previous_async()
                op.get_results()
        except OSError:
            pass
