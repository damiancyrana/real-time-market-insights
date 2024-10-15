import websockets
import orjson
import logging
from functools import lru_cache
from azure.core.exceptions import AzureError
from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
from config import *


class WebSocketClient:
    def __init__(self, uri):
        self.uri = uri
        self.connection = None

    async def connect(self):
        self.connection = await websockets.connect(self.uri)
        logging.info(f"Connected to {self.uri}")

    async def disconnect(self):
        if self.connection:
            await self.connection.close()
            logging.info(f"Disconnected from {self.uri}")

    async def send_command(self, command):
        message = orjson.dumps(command).decode()
        await self.connection.send(message)
        response = await self.connection.recv()
        return orjson.loads(response)


class StreamingWebSocketClient:
    def __init__(self, uri, stream_session_id):
        self.uri = uri
        self.connection = None
        self.stream_session_id = stream_session_id

    async def connect(self):
        self.connection = await websockets.connect(self.uri)
        logging.info(f"Connected to {self.uri}")

    async def disconnect(self):
        if self.connection:
            await self.connection.close()
            logging.info(f"Disconnected from {self.uri}")

    async def send_command(self, command):
        message = orjson.dumps(command).decode()
        await self.connection.send(message)

    async def receive(self):
        try:
            message = await self.connection.recv()
            data = orjson.loads(message)
            return data
        except Exception as e:
            logging.error(f"Error receiving message: {e}")
            return None


@lru_cache()
def get_keyvault_secret(secret_name):
    try:
        credential = DefaultAzureCredential()
        secret_client = SecretClient(vault_url=KEY_VAULT, credential=credential)
        secret_value = secret_client.get_secret(secret_name).value
        return secret_value
    except AzureError as e:
        logging.error(f"Wystąpił błąd podczas pobierania hasła: {e}")
        return None


async def login(client):
    user_id = get_keyvault_secret("XTB-user-DEMO")
    password = get_keyvault_secret("XTB-password")
    command = {
        "command": "login",
        "arguments": {
            "userId": user_id,
            "password": password
        }
    }
    response = await client.send_command(command)
    return response


async def get_server_time(client):
    command = {
        "command": "getServerTime"
    }
    response = await client.send_command(command)
    return response


async def logout(client):
    command = {
        "command": "logout"
    }
    response = await client.send_command(command)
    return response
