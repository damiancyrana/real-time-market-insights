import os
import logging
import datetime
import asyncio
import traceback
import pandas as pd
import threading
from collections import deque
from websocket_commands import *
from config import *

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Lista symboli do pobrania
SYMBOLS = ["US100", "DE40", "EURUSD", "USDJPY", "GOLD"]


class getTickData:
    def __init__(self, client, symbols):
        self.client = client
        self.symbols = symbols
        self.is_running = False
        self.save_task = None
        self.dataframes = {symbol: deque() for symbol in symbols}
        # Asynchroniczna blokada dla kodu asynchronicznego
        self.async_data_lock = asyncio.Lock()
        # Blokada wątku dla kodu synchronicznego
        self.thread_data_lock = threading.Lock()

    async def subscribe_ticks(self):
        tasks = [self._subscribe_tick(symbol) for symbol in self.symbols]
        await asyncio.gather(*tasks)

    async def _subscribe_tick(self, symbol):
        subscribe_command = {
            "command": "getTickPrices",
            "streamSessionId": self.client.stream_session_id,
            "symbol": symbol,
            "minArrivalTime": 1
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
                message = await self.client.receive()
                if message:
                    await self.process_message(message)
        except Exception as e:
            logging.error(f"Error in receive_ticks: {e}")
            self.is_running = False

    async def process_message(self, message):
        if 'command' in message and message['command'] == 'tickPrices':
            data = message['data']
            await self.process_tick(data)

    async def process_tick(self, data):
        symbol = data['symbol']
        if symbol in self.symbols:
            tick_data = {
                'timestamp': data['timestamp'],
                'ask': data['ask'],
                'bid': data['bid'],
                'askVolume': data.get('askVolume'),
                'bidVolume': data.get('bidVolume'),
                'level': data.get('level'),
                'spreadRaw': data.get('spreadRaw'),
                'spreadTable': data.get('spreadTable'),
                'quoteId': data.get('quoteId')
            }
            async with self.async_data_lock:
                self.dataframes[symbol].append(tick_data)
            print(f"Tick data for {symbol}: {data}")

    async def save_data_periodically(self):
        while self.is_running:
            await asyncio.sleep(DISK_SAVE_INTERVAL)
            await self.save_data()

    async def save_data(self):
        # asyncio.to_thread, aby uruchomić metodę synchroniczną w osobnym wątku
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
        if self.save_task:
            self.save_task.cancel()
            try:
                await self.save_task
            except asyncio.CancelledError:
                pass
        # Zapisz pozostałem dane przed zamknięciem
        await self.save_data()


async def main():
    main_uri = MAIN_URI
    streaming_uri = STREAMING_URI
    client = WebSocketClient(main_uri)

    try:
        await client.connect()
        logging.info("WebSocket connection established successfully")

        login_response = await login(client)
        if not login_response or not login_response.get("status"):
            logging.error("Login failed")
            return

        stream_session_id = login_response.get('streamSessionId')
        if not stream_session_id:
            logging.error("No streamSessionId received")
            return

        streaming_client = StreamingWebSocketClient(streaming_uri, stream_session_id)
        await streaming_client.connect()
        logging.info("Streaming WebSocket connection established successfully")

        server_time_response = await get_server_time(client)
        if not server_time_response or not server_time_response.get("status"):
            logging.error("Failed to get server time")
            return
        try:
            server_datetime = datetime.datetime.strptime(
                server_time_response["returnData"]["timeString"],
                "%b %d, %Y, %I:%M:%S %p"
            )
            logging.info(f"Czas serwera: {server_datetime}")
        except ValueError as e:
            logging.error(f"Date parsing error: {e}")
            return

        tick_data = getTickData(streaming_client, SYMBOLS)
        await tick_data.start()

    except Exception as e:
        logging.error(f"Unexpected error: {e}\n{traceback.format_exc()}")
    finally:
        # Zatrzymanie zbierania danych i zapis pozostałych danych
        await tick_data.stop()
        try:
            await logout(client)
            await client.disconnect()
            await streaming_client.disconnect()
        except Exception as e:
            logging.error(f"Error during disconnection: {e}")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Program interrupted by user")
