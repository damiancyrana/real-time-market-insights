# main.py
import os
import logging
import asyncio
import traceback
import pandas as pd
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
SYMBOLS = ["GOLD"]

# Mapowanie quoteId na opis
QUOTE_ID_MAP = {
    1: 'fixed',
    2: 'float',
    3: 'depth',
    4: 'cross'
}

class DataFetcher:
    def __init__(self, client, symbols, data_queue):
        self.client = client
        self.symbols = symbols
        self.is_running = False
        self.data_queue = data_queue

    async def subscribe_ticks(self):
        tasks = [self._subscribe_tick(symbol) for symbol in self.symbols]
        await asyncio.gather(*tasks)

    async def _subscribe_tick(self, symbol):
        subscribe_command = {
            "command": "getTickPrices",
            "streamSessionId": self.client.stream_session_id,
            "symbol": symbol,
            "minArrivalTime": 1,
            "maxLevel": 10  # Pobieranie danych do 10 poziomów głębokości
        }
        await self.client.send_command(subscribe_command)

    async def start(self):
        self.is_running = True
        await self.subscribe_ticks()
        await self.receive_ticks()

    async def receive_ticks(self):
        try:
            while self.is_running:
                try:
                    message = await self.client.receive()
                    if message:
                        await self.data_queue.put(message)
                    else:
                        logging.warning("Received empty message")
                except websockets.exceptions.ConnectionClosed as e:
                    logging.error(f"Connection closed in receive_ticks: {e}")
                    self.is_running = False
                    break
                except Exception as e:
                    logging.error(f"Exception in receive_ticks inner loop: {e}\n{traceback.format_exc()}")
        except Exception as e:
            logging.error(f"Error in receive_ticks: {e}\n{traceback.format_exc()}")
            self.is_running = False

    async def stop(self):
        self.is_running = False

class DataProcessor:
    def __init__(self, symbols, data_queue, broadcast_queue):
        self.symbols = symbols
        self.data_queue = data_queue
        self.broadcast_queue = broadcast_queue
        self.is_running = False

        self.order_books = {symbol: {} for symbol in symbols}
        self.volume_profiles = {symbol: defaultdict(float) for symbol in symbols}
        self.market_metrics = {symbol: {'total_volume': 0, 'average_volume': 0, 'trade_count': 0} for symbol in symbols}
        self.cvd = {symbol: 0 for symbol in symbols}
        self.order_imbalance = {symbol: 0 for symbol in symbols}
        self.fear_greed_index = {symbol: 50 for symbol in symbols}  # Początkowa wartość neutralna
        self.recommendations = {symbol: "Trzymaj" for symbol in symbols}
        self.transactions = {symbol: deque(maxlen=100) for symbol in symbols}
        # Nowe atrybuty dla kierunku trendu i siły
        self.trend_direction = {symbol: 'neutral' for symbol in symbols}
        self.trend_strength = {symbol: 0 for symbol in symbols}
        self.momentum = {symbol: 0 for symbol in symbols}
        # Data storage
        self.dataframes = {symbol: deque() for symbol in symbols}
        # For saving data to disk
        self.save_task = None
        # Dodatkowe atrybuty
        self.support_levels = {symbol: [] for symbol in symbols}
        self.resistance_levels = {symbol: [] for symbol in symbols}
        self.aggressive_orders = {symbol: deque(maxlen=100) for symbol in symbols}
        self.passive_orders = {symbol: deque(maxlen=100) for symbol in symbols}
        self.large_orders = {symbol: deque(maxlen=100) for symbol in symbols}
        self.tick_charts = {symbol: deque(maxlen=100) for symbol in symbols}
        self.order_flow = {symbol: deque(maxlen=1000) for symbol in symbols}  # Taśma zleceń
        self.buy_sell_ratio = {symbol: 0 for symbol in symbols}  # Wskaźnik nastroju rynku

    async def start(self):
        self.is_running = True
        self.save_task = asyncio.create_task(self.save_data_periodically())
        while self.is_running:
            try:
                message = await self.data_queue.get()
                if message:
                    await self.process_message(message)
                else:
                    logging.warning("Received empty message in processor")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Exception in DataProcessor: {e}\n{traceback.format_exc()}")

    async def process_message(self, message):
        if 'command' in message and message['command'] == 'tickPrices':
            data = message['data']
            await self.process_tick(data)
        else:
            logging.warning(f"Unknown message received: {message}")

    async def process_tick(self, data):
        symbol = data['symbol']
        level = data['level']
        if symbol in self.symbols:
            order_book = self.order_books[symbol]
            quote_id = data.get('quoteId', 0)
            quote_source = QUOTE_ID_MAP.get(quote_id, 'unknown')

            order_book[level] = {
                'ask': data['ask'],
                'askVolume': data.get('askVolume', 0),
                'bid': data['bid'],
                'bidVolume': data.get('bidVolume', 0),
                'timestamp': data['timestamp'],
                'spreadRaw': data.get('spreadRaw'),
                'spreadTable': data.get('spreadTable'),
                'quote_source': quote_source,
                'level': level
            }

            # Analiza wolumenu i profil wolumenu
            price_level = (data['ask'] + data['bid']) / 2
            volume = (data.get('askVolume', 0) + data.get('bidVolume', 0)) / 2
            self.volume_profiles[symbol][price_level] += volume

            # Aktualizacja statystyk rynkowych
            self.market_metrics[symbol]['total_volume'] += volume
            self.market_metrics[symbol]['trade_count'] += 1
            self.market_metrics[symbol]['average_volume'] = self.market_metrics[symbol]['total_volume'] / self.market_metrics[symbol]['trade_count']

            # Aktualizacja high i low
            self.market_metrics[symbol]['high'] = data['high']
            self.market_metrics[symbol]['low'] = data['low']
            self.market_metrics[symbol]['quote_source'] = quote_source

            # Wskaźniki wolumenowe i CVD
            await self.calculate_cvd(symbol, data)

            # Wskaźnik strachu i chciwości
            await self.calculate_fear_greed_index(symbol)

            # Wskaźnik przewagi zleceń kupna nad sprzedażą (Order Book Imbalance)
            await self.calculate_order_imbalance(symbol)

            # Obliczanie trendu i momentum
            await self.calculate_trend_and_momentum(symbol, data)

            # Generowanie rekomendacji
            await self.generate_recommendation(symbol)

            # Rejestrowanie transakcji
            await self.record_transaction(symbol, data)

            # Wykrywanie dużych zleceń
            await self.detect_large_orders(symbol, data)

            # Wykrywanie poziomów wsparcia i oporu
            await self.detect_support_resistance_levels(symbol)

            # Klasyfikacja zleceń na agresywne i pasywne
            await self.classify_orders(symbol, data)

            # Aktualizacja taśmy zleceń
            await self.update_order_flow(symbol, data)

            # Obliczanie wskaźnika nastroju rynku
            await self.calculate_market_sentiment(symbol)

            # Obliczanie statystyk z ostatnich N transakcji
            await self.calculate_recent_trade_stats(symbol)

            # Prepare message to broadcast
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
            self.dataframes[symbol].append(tick_data)

    async def calculate_cvd(self, symbol, data):
        # Obliczanie CVD
        bid_volume = data.get('bidVolume', 0)
        ask_volume = data.get('askVolume', 0)
        self.cvd[symbol] += bid_volume - ask_volume

    async def calculate_fear_greed_index(self, symbol):
        # Prosta implementacja wskaźnika na podstawie zmienności i wolumenu
        try:
            if 1 in self.order_books[symbol]:
                ask = self.order_books[symbol][1]['ask']
                bid = self.order_books[symbol][1]['bid']
            elif 0 in self.order_books[symbol]:
                ask = self.order_books[symbol][0]['ask']
                bid = self.order_books[symbol][0]['bid']
            else:
                ask = bid = 0
            volatility = abs(ask - bid)
            volume = self.market_metrics[symbol]['total_volume']
            index = (volatility * volume) % 100  # Przykładowy wzór
            self.fear_greed_index[symbol] = index
        except Exception as e:
            logging.error(f"Error in calculate_fear_greed_index: {e}\n{traceback.format_exc()}")
            self.fear_greed_index[symbol] = 50

    async def calculate_order_imbalance(self, symbol):
        # Obliczanie nierównowagi zleceń
        try:
            total_bid_volume = sum([level['bidVolume'] for level in self.order_books[symbol].values()])
            total_ask_volume = sum([level['askVolume'] for level in self.order_books[symbol].values()])
            if total_bid_volume + total_ask_volume > 0:
                imbalance = (total_bid_volume - total_ask_volume) / (total_bid_volume + total_ask_volume)
                self.order_imbalance[symbol] = imbalance
            else:
                self.order_imbalance[symbol] = 0
        except Exception as e:
            logging.error(f"Error in calculate_order_imbalance: {e}\n{traceback.format_exc()}")
            self.order_imbalance[symbol] = 0

    async def calculate_trend_and_momentum(self, symbol, data):
        # Prosta implementacja wskaźnika trendu i momentum
        if not hasattr(self, 'price_history'):
            self.price_history = {symbol: deque(maxlen=10) for symbol in self.symbols}

        if 0 in self.order_books[symbol]:
            current_price = (self.order_books[symbol][0]['ask'] + self.order_books[symbol][0]['bid']) / 2
            self.price_history[symbol].append(current_price)
            self.tick_charts[symbol].append({'price': current_price, 'timestamp': data['timestamp']})

            prices = list(self.price_history[symbol])
            if len(prices) >= 2:
                trend = prices[-1] - prices[0]
                self.trend_strength[symbol] = abs(trend)
                if trend > 0:
                    self.trend_direction[symbol] = 'up'
                elif trend < 0:
                    self.trend_direction[symbol] = 'down'
                else:
                    self.trend_direction[symbol] = 'neutral'
                self.momentum[symbol] = prices[-1] - prices[-2]
            else:
                self.trend_direction[symbol] = 'neutral'
                self.trend_strength[symbol] = 0
                self.momentum[symbol] = 0

    async def generate_recommendation(self, symbol):
        # Prosta logika generowania rekomendacji na podstawie wskaźników
        imbalance = self.order_imbalance[symbol]
        fear_greed = self.fear_greed_index[symbol]
        if imbalance > 0.2 and fear_greed < 40:
            self.recommendations[symbol] = "Kup"
        elif imbalance < -0.2 and fear_greed > 60:
            self.recommendations[symbol] = "Sprzedaj"
        else:
            self.recommendations[symbol] = "Trzymaj"

    async def record_transaction(self, symbol, data):
        transaction = {
            'timestamp': data['timestamp'],
            'price': (data['ask'] + data['bid']) / 2,
            'volume': (data.get('askVolume', 0) + data.get('bidVolume', 0)) / 2,
            'ask': data['ask'],
            'bid': data['bid'],
            'askVolume': data.get('askVolume', 0),
            'bidVolume': data.get('bidVolume', 0),
            'type': 'buy' if data.get('bidVolume', 0) > data.get('askVolume', 0) else 'sell'
        }
        self.transactions[symbol].append(transaction)

    async def detect_large_orders(self, symbol, data):
        # Wykrywanie dużych transakcji
        large_order_threshold = 1000  # Próg wolumenu dla dużego zlecenia (przykładowa wartość)
        ask_volume = data.get('askVolume', 0)
        bid_volume = data.get('bidVolume', 0)
        if ask_volume > large_order_threshold or bid_volume > large_order_threshold:
            large_order = {
                'timestamp': data['timestamp'],
                'price': (data['ask'] + data['bid']) / 2,
                'askVolume': ask_volume,
                'bidVolume': bid_volume
            }
            self.large_orders[symbol].append(large_order)
            # Możesz dodać powiadomienia lub dodatkowe przetwarzanie

    async def detect_support_resistance_levels(self, symbol):
        # Prosta implementacja wykrywania poziomów wsparcia i oporu
        prices = list(self.volume_profiles[symbol].keys())
        volumes = list(self.volume_profiles[symbol].values())
        if len(prices) >= 5:
            # Wybieramy poziomy z największym wolumenem
            combined = sorted(zip(prices, volumes), key=lambda x: x[1], reverse=True)
            self.support_levels[symbol] = [price for price, vol in combined[:3]]  # Top 3 poziomy wsparcia
            self.resistance_levels[symbol] = [price for price, vol in combined[-3:]]  # Top 3 poziomy oporu

    async def classify_orders(self, symbol, data):
        # Klasyfikacja zleceń na agresywne i pasywne
        ask_volume = data.get('askVolume', 0)
        bid_volume = data.get('bidVolume', 0)
        if ask_volume > bid_volume:
            self.aggressive_orders[symbol].append(data)
        else:
            self.passive_orders[symbol].append(data)

    async def update_order_flow(self, symbol, data):
        # Aktualizacja taśmy zleceń
        order_flow_entry = {
            'timestamp': data['timestamp'],
            'price': (data['ask'] + data['bid']) / 2,
            'volume': (data.get('askVolume', 0) + data.get('bidVolume', 0)) / 2,
            'type': 'buy' if data.get('bidVolume', 0) > data.get('askVolume', 0) else 'sell'
        }
        self.order_flow[symbol].append(order_flow_entry)

    async def calculate_market_sentiment(self, symbol):
        # Obliczanie proporcji zleceń kupna do sprzedaży
        total_buy_orders = sum(1 for tx in self.transactions[symbol] if tx['type'] == 'buy')
        total_sell_orders = sum(1 for tx in self.transactions[symbol] if tx['type'] == 'sell')
        total_orders = total_buy_orders + total_sell_orders
        if total_orders > 0:
            self.buy_sell_ratio[symbol] = total_buy_orders / total_orders
        else:
            self.buy_sell_ratio[symbol] = 0.5  # Neutralny sentyment

    async def calculate_recent_trade_stats(self, symbol):
        # Obliczanie statystyk z ostatnich N transakcji
        N = 50  # Ostatnie N transakcji
        recent_transactions = list(self.transactions[symbol])[-N:]
        if recent_transactions:
            volumes = [tx['volume'] for tx in recent_transactions]
            prices = [tx['price'] for tx in recent_transactions]
            self.market_metrics[symbol]['recent_avg_volume'] = sum(volumes) / len(volumes)
            self.market_metrics[symbol]['recent_avg_price'] = sum(prices) / len(prices)
            self.market_metrics[symbol]['recent_max_volume'] = max(volumes)
            self.market_metrics[symbol]['recent_min_volume'] = min(volumes)
        else:
            self.market_metrics[symbol]['recent_avg_volume'] = 0
            self.market_metrics[symbol]['recent_avg_price'] = 0
            self.market_metrics[symbol]['recent_max_volume'] = 0
            self.market_metrics[symbol]['recent_min_volume'] = 0

    async def broadcast_order_book(self, symbol):
        order_book = self.order_books[symbol]
        volume_profile = self.volume_profiles[symbol]
        market_metrics = self.market_metrics[symbol]
        transactions = list(self.transactions[symbol])
        cvd = self.cvd[symbol]
        order_imbalance = self.order_imbalance[symbol]
        fear_greed_index = self.fear_greed_index[symbol]
        recommendation = self.recommendations[symbol]
        trend_direction = self.trend_direction[symbol]
        trend_strength = self.trend_strength[symbol]
        momentum = self.momentum[symbol]
        support_levels = self.support_levels[symbol]
        resistance_levels = self.resistance_levels[symbol]
        large_orders = list(self.large_orders[symbol])
        tick_chart = list(self.tick_charts[symbol])
        order_flow = list(self.order_flow[symbol])
        buy_sell_ratio = self.buy_sell_ratio[symbol]

        # Pobieranie najlepszych spreadów
        if 0 in self.order_books[symbol]:
            best_spread_raw = self.order_books[symbol][0].get('spreadRaw')
            best_spread_table = self.order_books[symbol][0].get('spreadTable')
        else:
            best_spread_raw = None
            best_spread_table = None

        message = {
            'type': 'order_book',
            'symbol': symbol,
            'order_book': order_book,
            'volume_profile': dict(volume_profile),
            'market_metrics': market_metrics,
            'transactions': transactions,
            'cvd': cvd,
            'order_imbalance': order_imbalance,
            'fear_greed_index': fear_greed_index,
            'recommendation': recommendation,
            'trend_direction': trend_direction,
            'trend_strength': trend_strength,
            'momentum': momentum,
            'support_levels': support_levels,
            'resistance_levels': resistance_levels,
            'large_orders': large_orders,
            'tick_chart': tick_chart,
            'order_flow': order_flow,
            'buy_sell_ratio': buy_sell_ratio,
            'best_spread_raw': best_spread_raw,
            'best_spread_table': best_spread_table
        }
        await self.broadcast_queue.put(message)

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

        for symbol in self.symbols:
            data_list = list(self.dataframes[symbol])
            self.dataframes[symbol].clear()
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
        await self.save_data()

class DataBroadcaster:
    def __init__(self, broadcast_queue):
        self.broadcast_queue = broadcast_queue
        self.websockets = set()
        self.ws_lock = asyncio.Lock()
        self.is_running = False

    async def start(self):
        self.is_running = True
        while self.is_running:
            try:
                message = await self.broadcast_queue.get()
                await self.broadcast_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Exception in DataBroadcaster: {e}\n{traceback.format_exc()}")

    async def broadcast_message(self, message):
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

    async def stop(self):
        self.is_running = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    main_uri = MAIN_URI
    streaming_uri = STREAMING_URI
    client = WebSocketClient(main_uri)
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

        data_queue = asyncio.Queue()
        broadcast_queue = asyncio.Queue()

        data_fetcher = DataFetcher(streaming_client, SYMBOLS, data_queue)
        data_processor = DataProcessor(SYMBOLS, data_queue, broadcast_queue)
        data_broadcaster = DataBroadcaster(broadcast_queue)

        app.state.data_fetcher = data_fetcher
        app.state.data_processor = data_processor
        app.state.data_broadcaster = data_broadcaster

        data_fetcher_task = asyncio.create_task(data_fetcher.start())
        data_processor_task = asyncio.create_task(data_processor.start())
        data_broadcaster_task = asyncio.create_task(data_broadcaster.start())

        app.state.data_fetcher_task = data_fetcher_task
        app.state.data_processor_task = data_processor_task
        app.state.data_broadcaster_task = data_broadcaster_task

        yield  # Aplikacja jest gotowa do obsługi żądań

    except Exception as e:
        logging.error(f"Unexpected error in lifespan: {e}\n{traceback.format_exc()}")
        yield

    finally:
        await data_fetcher.stop()
        await data_processor.stop()
        await data_broadcaster.stop()
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
    data_broadcaster = app.state.data_broadcaster
    await data_broadcaster.register(websocket)
    try:
        while True:
            await asyncio.sleep(10)
    except WebSocketDisconnect:
        await data_broadcaster.unregister(websocket)

if __name__ == '__main__':
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
