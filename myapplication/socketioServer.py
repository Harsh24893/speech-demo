import asyncio
import time

import socketio
from aiohttp import web
from aiohttp.web_runner import GracefulExit
from loguru import logger


class SocketIOServer:
    def __init__(self, signals, stt, modules=None):
        if modules is None:
            modules = {}
        self.signals = signals
        self.stt = stt
        self.modules = modules

    def start_server(self):
        logger.debug("Starting Socket.io server")
        sio = socketio.AsyncServer(async_mode="aiohttp", cors_allowed_origins="*")
        app = web.Application()
        sio.attach(app)

        @sio.event
        async def get_blacklist(sid):
            await sio.emit("get_blacklist", self.llmWrapper.API.get_blacklist())

        @sio.event
        async def set_blacklist(sid, message):
            self.llmWrapper.API.set_blacklist(message)

        @sio.event
        async def disable_LLM(sid):
            self.llmWrapper.API.set_LLM_status(False)

        @sio.event
        async def enable_LLM(sid):
            self.llmWrapper.API.set_LLM_status(True)

        @sio.event
        async def disable_TTS(sid):
            self.tts.API.set_TTS_status(False)

        @sio.event
        async def enable_TTS(sid):
            self.tts.API.set_TTS_status(True)

        @sio.event
        async def disable_STT(sid):
            self.stt.API.set_STT_status(False)

        @sio.event
        async def enable_STT(sid):
            self.stt.API.set_STT_status(True)

        @sio.event
        async def disable_multimodal(sid):
            if "multimodal" in self.modules:
                self.modules["multimodal"].API.set_multimodal_status(False)

        @sio.event
        async def enable_multimodal(sid):
            if "multimodal" in self.modules:
                self.modules["multimodal"].API.set_multimodal_status(True)

        @sio.event
        async def get_hotkeys(sid):
            if "vtube_studio" in self.modules:
                self.modules["vtube_studio"].API.get_hotkeys()

        @sio.event
        async def send_hotkey(sid, hotkey):
            if "vtube_studio" in self.modules:
                self.modules["vtube_studio"].API.send_hotkey(hotkey)

        @sio.event
        async def cancel_next_message(sid):
            self.llmWrapper.API.cancel_next()

        @sio.event
        async def abort_current_message(sid):
            self.tts.API.abort_current()

        @sio.event
        async def fun_fact(sid):
            self.signals.history.append({"role": "user", "content": "Let's move on. Can we get a fun fact?"})
            self.signals.new_message = True

        @sio.event
        async def new_topic(sid, message):
            self.signals.history.append({"role": "user", "content": message})
            self.signals.new_message = True

        @sio.event
        async def nuke_history(sid):
            self.signals.history = []

        @sio.event
        async def play_audio(sid, file_name):
            if "audio_player" in self.modules:
                self.modules["audio_player"].API.play_audio(file_name)

        @sio.event
        async def pause_audio(sid):
            if "audio_player" in self.modules:
                self.modules["audio_player"].API.pause_audio()

        @sio.event
        async def resume_audio(sid):
            if "audio_player" in self.modules:
                self.modules["audio_player"].API.resume_audio()

        @sio.event
        async def abort_audio(sid):
            if "audio_player" in self.modules:
                self.modules["audio_player"].API.stop_playing()

        @sio.event
        async def set_custom_prompt(sid, data):
            if "custom_prompt" in self.modules:
                self.modules["custom_prompt"].API.set_prompt(data["prompt"], priority=int(data["priority"]))
                await sio.emit("get_custom_prompt", self.modules["custom_prompt"].API.get_prompt())

        @sio.event
        async def clear_short_term(sid):
            if "memory" in self.modules:
                self.modules["memory"].API.clear_short_term()
                await sio.emit("get_memories", self.modules["memory"].API.get_memories())

        @sio.event
        async def import_json(sid):
            if "memory" in self.modules:
                self.modules["memory"].API.import_json()

        @sio.event
        async def export_json(sid):
            if "memory" in self.modules:
                self.modules["memory"].API.export_json()

        @sio.event
        async def delete_memory(sid, data):
            if "memory" in self.modules:
                self.modules["memory"].API.delete_memory(data)
                await sio.emit("get_memories", self.modules["memory"].API.get_memories())

        @sio.event
        async def get_memories(sid, data):
            if "memory" in self.modules:
                await sio.emit("get_memories", self.modules["memory"].API.get_memories(data))

        @sio.event
        async def create_memory(sid, data):
            if "memory" in self.modules:
                self.modules["memory"].API.create_memory(data)
                await sio.emit("get_memories", self.modules["memory"].API.get_memories())

        # When a new client connects, send them the status of everything
        @sio.event
        async def connect(sid, environ):
            # Set signals to themselves to trigger setter function and the sio.emit
            self.signals.AI_thinking = self.signals.AI_thinking
            self.signals.AI_speaking = self.signals.AI_speaking
            self.signals.human_speaking = self.signals.human_speaking
            await sio.emit(
                "patience_update", {"crr_time": time.time() - self.signals.last_message_time, "total_time": 60}
            )
            await sio.emit("get_blacklist", self.llmWrapper.API.get_blacklist())

            if "audio_player" in self.modules:
                await sio.emit("audio_list", self.modules["audio_player"].API.get_audio_list())
            if "custom_prompt" in self.modules:
                await sio.emit("get_custom_prompt", self.modules["custom_prompt"].API.get_prompt())
            if "multimodal" in self.modules:
                await sio.emit("multimodal_status", self.modules["multimodal"].API.get_multimodal_status())

            # Collect the enabled status of the llm, tts, stt, and movement and send it to the client
            await sio.emit("LLM_status", self.llmWrapper.API.get_LLM_status())
            await sio.emit("TTS_status", self.tts.API.get_TTS_status())
            await sio.emit("STT_status", self.stt.API.get_STT_status())

        @sio.event
        def disconnect(sid):
            logger.debug("Client disconnected")

        async def send_messages():
            while True:
                if self.signals.terminate:
                    raise GracefulExit

                while not self.signals.sio_queue.empty():
                    event, data = self.signals.sio_queue.get()
                    logger.debug(f"Sending {event} with {data}")
                    await sio.emit(event, data)
                await sio.sleep(0.1)

        async def init_app():
            sio.start_background_task(send_messages)
            return app

        # web.run_app(init_app())
        asyncio.run(init_app())
