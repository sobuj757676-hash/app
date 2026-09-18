import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv(Path(__file__).parent / '.env')
client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]

@asynccontextmanager
async def lifespan(app):
    from seed import initialize
    await initialize(db)
    yield
    client.close()

app = FastAPI(title='VoltCraft · Site Operations', lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ['CORS_ORIGINS'].split(','), allow_credentials=False, allow_methods=['*'], allow_headers=['*'])
from routes import router
from operations import router as operations_router
app.include_router(router, prefix='/api')
app.include_router(operations_router, prefix='/api')