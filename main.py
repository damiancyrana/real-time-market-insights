import os
import logging
import datetime
import asyncio
import traceback
import orjson
import pandas as pd
import threading
from collections import deque, defaultdict
from websocket_commands import *
from config import *

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
import uvicorn

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Lista symboli do pobrania
SYMBOLS = ["BITCOIN"]

class getTickData:
    def __init__(self, client, symbols):
        self.client = client
        self.symbols = symbols
        self.is_running = False
        self.save_task = None
        self.dataframes = {symbol: deque() for symbol in symbols}
        self.volume_profiles = {symbol: defaultdict(float) for symbol in symbols}
        # Asynchroniczna blokada dla kodu asynchronicznego
        self.async_data_lock = asyncio.Lock()
        # Blokada wątku dla kodu synchronicznego
        self.thread_data_lock = threading.Lock()
        # Inicjalizacja order book dla każdego symbolu
        self.order_books = {symbol: {} for symbol in symbols}
        self.previous_order_books = {symbol: {} for symbol in symbols}
        self.websockets = set()
        self.ws_lock = asyncio.Lock()
        self.market_metrics = {symbol: {'total_volume': 0, 'average_volume': 0, 'trade_count': 0} for symbol in symbols}

    async def subscribe_ticks(self):
        tasks = [self._subscribe_tick(symbol) for symbol in self.symbols]
        await asyncio.gather(*tasks)

    async def _subscribe_tick(self, symbol):
        subscribe_command = {
            "command": "getTickPrices",
            "streamSessionId": self.client.stream_session_id,
            "symbol": symbol,
            "minArrivalTime": 1,  # Otrzymywanie danych z maksymalną częstotliwością
            "maxLevel": 5  # Otrzymywanie danych głębokości rynku do 5 poziomów
        }
        await self.client.send_command(subscribe_command)

    async def start(self):
        self.is_running = True
        await self.subscribe_ticks()
        self.save_task = asyncio.create_task(self.save_data_periodically())
        await self.receive_ticks()

    async def receive_ticks(self):
        try:
            while self.is_running:
                try:
                    message = await self.client.receive()
                    if message:
                        await self.process_message(message)
                except websockets.exceptions.ConnectionClosed as e:
                    logging.error(f"Connection closed in receive_ticks: {e}")
                    self.is_running = False
                    break
        except Exception as e:
            logging.error(f"Error in receive_ticks: {e}")
            self.is_running = False

    async def process_message(self, message):
        if 'command' in message and message['command'] == 'tickPrices':
            data = message['data']
            await self.process_tick(data)

    async def process_tick(self, data):
        symbol = data['symbol']
        level = data['level']
        if symbol in self.symbols:
            order_book = self.order_books[symbol]
            order_book[level] = {
                'ask': data['ask'],
                'askVolume': data.get('askVolume', 0),
                'bid': data['bid'],
                'bidVolume': data.get('bidVolume', 0),
                'timestamp': data['timestamp'],
            }

            # Analiza wolumenu i profil wolumenu
            price_level = (data['ask'] + data['bid']) / 2
            volume = (data.get('askVolume', 0) + data.get('bidVolume', 0)) / 2
            self.volume_profiles[symbol][price_level] += volume

            # Aktualizacja statystyk rynkowych
            self.market_metrics[symbol]['total_volume'] += volume
            self.market_metrics[symbol]['trade_count'] += 1
            self.market_metrics[symbol]['average_volume'] = self.market_metrics[symbol]['total_volume'] / self.market_metrics[symbol]['trade_count']

            # Śledzenie zmian w czasie rzeczywistym
            self.previous_order_books[symbol] = order_book.copy()

            await self.broadcast_order_book(symbol)

            # Zapisz tick do pliku
            tick_data = {
                'timestamp': data['timestamp'],
                'ask': data['ask'],
                'bid': data['bid'],
                'askVolume': data.get('askVolume', 0),
                'bidVolume': data.get('bidVolume', 0),
                'level': data.get('level'),
                'spreadRaw': data.get('spreadRaw'),
                'spreadTable': data.get('spreadTable'),
                'quoteId': data.get('quoteId')
            }
            async with self.async_data_lock:
                self.dataframes[symbol].append(tick_data)
            print(f"Tick for {symbol}: {tick_data}")

    async def broadcast_order_book(self, symbol):
        order_book = self.order_books[symbol]
        volume_profile = self.volume_profiles[symbol]
        market_metrics = self.market_metrics[symbol]

        message = {
            'symbol': symbol,
            'order_book': order_book,
            'volume_profile': volume_profile,
            'market_metrics': market_metrics,
        }
        websockets_to_remove = set()
        async with self.ws_lock:
            for ws in self.websockets:
                try:
                    await ws.send_json(message)
                except Exception as e:
                    logging.error(f"Error sending to websocket: {e}")
                    websockets_to_remove.add(ws)
            for ws in websockets_to_remove:
                await self.unregister(ws)

    async def register(self, websocket):
        async with self.ws_lock:
            self.websockets.add(websocket)

    async def unregister(self, websocket):
        async with self.ws_lock:
            self.websockets.discard(websocket)

    async def save_data_periodically(self):
        while self.is_running:
            await asyncio.sleep(DISK_SAVE_INTERVAL)
            await self.save_data()

    async def save_data(self):
        await asyncio.to_thread(self._save_data_sync)

    def _save_data_sync(self):
        data_dir = "Data"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)

        with self.thread_data_lock:
            data_copy = {symbol: list(self.dataframes[symbol]) for symbol in self.symbols}
            for symbol in self.symbols:
                self.dataframes[symbol].clear()

        for symbol, data_list in data_copy.items():
            if data_list:
                df = pd.DataFrame(data_list)
                file_path = os.path.join(data_dir, f"{symbol}_ticks.csv")
                if os.path.exists(file_path):
                    df.to_csv(file_path, mode='a', header=False, index=False)
                else:
                    df.to_csv(file_path, index=False)
                logging.info(f"Saved data for {symbol} to {file_path}")

    async def stop(self):
        self.is_running = False
        await asyncio.sleep(0)
        if self.save_task:
            self.save_task.cancel()
            try:
                await self.save_task
            except asyncio.CancelledError:
                pass
        await self.save_data()


@asynccontextmanager
async def lifespan(app: FastAPI):
    main_uri = MAIN_URI
    streaming_uri = STREAMING_URI
    client = WebSocketClient(main_uri)
    tick_data = None 
    try:
        await client.connect()
        logging.info("WebSocket connection established successfully")

        login_response = await login(client)
        if not login_response or not login_response.get("status"):
            logging.error("Login failed")
            yield
            return

        stream_session_id = login_response.get('streamSessionId')
        if not stream_session_id:
            logging.error("No streamSessionId received")
            yield
            return

        streaming_client = StreamingWebSocketClient(streaming_uri, stream_session_id)
        await streaming_client.connect()
        logging.info("Streaming WebSocket connection established successfully")

        tick_data = getTickData(streaming_client, SYMBOLS)
        app.state.tick_data = tick_data 
        # tick_data.start() jako zadanie w tle
        task = asyncio.create_task(tick_data.start())
        yield  # Aplikacja jest gotowa do obsługi żądań

    except Exception as e:
        logging.error(f"Unexpected error in lifespan: {e}\n{traceback.format_exc()}")
        yield

    finally:
        if tick_data:
            await tick_data.stop()
        try:
            await logout(client)
            await client.disconnect()
            await streaming_client.disconnect()
        except Exception as e:
            logging.error(f"Error during disconnection: {e}")


app = FastAPI(lifespan=lifespan)
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def get(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logging.error(f"Błąd podczas renderowania szablonu index.html: {e}\n{traceback.format_exc()}")
        return HTMLResponse("Wystąpił błąd serwera", status_code=500)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    tick_data = app.state.tick_data
    await tick_data.register(websocket)
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        await tick_data.unregister(websocket)


if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
