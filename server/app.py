import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from server.dependencies import init_runner, shutdown_runner
from server.routes.chat import router as chat_router
from server.routes.recognize import router as recognize_router
from server.schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PlateAgent 服务启动中...")
    await init_runner()
    logger.info("Runner 就绪，开始接收请求")
    yield
    logger.info("PlateAgent 服务关闭中...")
    await shutdown_runner()
    logger.info("Runner 已关闭")


def create_app() -> FastAPI:
    app = FastAPI(
        title="PlateAgent API",
        description="基于 tRPC-Agent 的车牌识别智能体服务",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Day 9: FastAPI OpenTelemetry 自动注入 ──
    FastAPIInstrumentor.instrument_app(app)

    # 注册路由
    app.include_router(chat_router)
    app.include_router(recognize_router)

    # 健康检查
    @app.get("/api/health", response_model=HealthResponse)
    async def health():
        return HealthResponse()

    return app


app = create_app()
