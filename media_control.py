# media_control.py

import asyncio
from winrt.windows.media.control import (
    GlobalSystemMediaTransportControlsSessionManager
)

class MediaController:
    def __init__(self):
        # wrap the WinRT async call in a coroutine
        async def _get_mgr():
            return await GlobalSystemMediaTransportControlsSessionManager.request_async()

        # drive it to completion
        self._mgr = asyncio.run(_get_mgr())

    def _update_session(self):
        self._session = self._mgr.get_current_session()

    def play(self):
        self._update_session()
        if self._session:
            asyncio.run(self._session.try_play_async())

    def pause(self):
        self._update_session()
        if self._session:
            asyncio.run(self._session.try_pause_async())

    def stop(self):
        self._update_session()
        if self._session:
            asyncio.run(self._session.try_stop_async())

    def next(self):
        self._update_session()
        if self._session:
            asyncio.run(self._session.try_skip_next_async())

    def previous(self):
        self._update_session()
        if self._session:
            asyncio.run(self._session.try_skip_previous_async())
