"""통합 테스트 공통 fixture — testcontainers로 MySQL + MongoDB + Redis 컨테이너를 관리한다.

session 스코프로 컨테이너를 한 번만 띄우고, function 스코프로 데이터를 격리한다.
"""

import os
import time

import pytest
from pymongo import MongoClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.mysql import MySqlContainer
from testcontainers.redis import RedisContainer

# === 컨테이너 (session 스코프 — 테스트 세션 동안 한 번만 생성) ===


@pytest.fixture(scope="session")
def mysql_container():
    """MySQL 8.0 테스트 컨테이너"""
    container = MySqlContainer(
        image="mysql:8.0",
        username="test",
        password="test",
        dbname="pipeline_test",
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def mongo_container():
    """MongoDB 7.0 테스트 컨테이너 (replica set, 인증 없음)

    트랜잭션을 위해 replica set으로 시작한다.
    testcontainers의 MongoDbContainer는 인증을 강제하므로,
    DockerContainer를 직접 사용하여 인증 없이 replica set 모드로 실행한다.

    안정성 강화:
    - 로그 대기 타임아웃 60초
    - ping으로 서버 준비 확인 후 replica set 초기화
    - TESTCONTAINERS_RYUK_DISABLED=true로 Ryuk 비활성화 권장
    """
    container = (
        DockerContainer(image="mongo:7.0")
        .with_exposed_ports(27017)
        .with_command("--replSet rs0 --bind_ip_all")
    )
    with container:
        wait_for_logs(container, "Waiting for connections", timeout=60)
        _init_replica_set(container)
        yield container


def _init_replica_set(container: DockerContainer) -> None:
    """MongoDB를 single-node replica set으로 초기화한다."""
    import contextlib

    from pymongo.errors import OperationFailure

    host = container.get_container_host_ip()
    port = container.get_exposed_port(27017)
    client = MongoClient(
        f"mongodb://{host}:{port}/?directConnection=true",
        serverSelectionTimeoutMS=10000,
        connectTimeoutMS=10000,
    )

    # ping으로 서버 준비 확인
    for _ in range(30):
        try:
            client.admin.command("ping")
            break
        except Exception:
            time.sleep(1)

    with contextlib.suppress(OperationFailure):
        client.admin.command(
            "replSetInitiate",
            {
                "_id": "rs0",
                "members": [{"_id": 0, "host": "localhost:27017"}],
            },
        )

    # replica set이 PRIMARY로 전환될 때까지 대기
    for _ in range(30):
        try:
            status = client.admin.command("replSetGetStatus")
            if any(m.get("stateStr") == "PRIMARY" for m in status.get("members", [])):
                break
        except OperationFailure:
            pass
        time.sleep(1)

    client.close()


@pytest.fixture(scope="session")
def redis_container():
    """Redis 7.0 테스트 컨테이너"""
    container = RedisContainer(image="redis:7.0")
    with container:
        yield container


# === 환경변수 주입 (session 스코프 — 모듈 import 전에 환경변수 설정) ===


@pytest.fixture(scope="session")
def _set_env(mysql_container, mongo_container, redis_container):
    """테스트 컨테이너 URL을 환경변수로 주입한다.

    app 모듈이 import 시점에 환경변수를 읽으므로,
    반드시 app import 이전에 환경변수를 설정해야 한다.
    """
    mysql_url = mysql_container.get_connection_url()
    if "pymysql" not in mysql_url:
        mysql_url = mysql_url.replace("mysql://", "mysql+pymysql://")

    mongo_host = mongo_container.get_container_host_ip()
    mongo_port = mongo_container.get_exposed_port(27017)
    mongo_url = f"mongodb://{mongo_host}:{mongo_port}/pipeline_test?directConnection=true"

    redis_host = redis_container.get_container_host_ip()
    redis_port = redis_container.get_exposed_port(6379)
    redis_url = f"redis://{redis_host}:{redis_port}/0"

    os.environ["DATABASE_URL"] = mysql_url
    os.environ["MONGO_URL"] = mongo_url
    os.environ["REDIS_URL"] = redis_url
    os.environ["DATA_DIR"] = str(os.path.join(os.path.dirname(__file__), "..", "..", "data"))

    yield

    for key in ("DATABASE_URL", "MONGO_URL", "REDIS_URL", "DATA_DIR"):
        os.environ.pop(key, None)


# === DB 엔진 / 세션 ===


@pytest.fixture(scope="session")
def db_engine(_set_env):
    """MySQL 엔진 — 환경변수가 설정된 후 생성한다."""
    # 엔티티 모듈을 import하여 Base.metadata에 테이블이 등록되도록 한다
    import app.adapter.outbound.mysql.entities  # noqa: F401
    from app.adapter.outbound.mysql.database import Base

    engine = create_engine(os.environ["DATABASE_URL"], echo=False)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def _session_factory(db_engine):
    return sessionmaker(bind=db_engine)


@pytest.fixture()
def db_session(_session_factory):
    """테스트 단위 MySQL 세션 — 테스트 후 롤백한다."""
    session = _session_factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def _clean_mysql(db_engine):
    """각 테스트 후 MySQL 테이블 데이터를 삭제한다."""
    yield
    with db_engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in ("rejections", "labels", "odd_tags", "selections"):
            conn.execute(text(f"DELETE FROM {table}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()


# === MongoDB ===


@pytest.fixture(scope="session")
def mongo_client(_set_env):
    """MongoDB 클라이언트 — 연결 복원력 옵션 포함

    serverSelectionTimeoutMS: 서버 선택 대기 시간 (기본 30s → 60s)
    socketTimeoutMS: 소켓 작업 대기 시간 (기본 0=무한 → 60s)
    retryWrites/retryReads: 일시적 네트워크 오류 시 자동 재시도
    """
    client = MongoClient(
        os.environ["MONGO_URL"],
        serverSelectionTimeoutMS=60000,
        socketTimeoutMS=60000,
        connectTimeoutMS=30000,
        retryWrites=True,
        retryReads=True,
    )
    yield client
    client.close()


@pytest.fixture(scope="session")
def mongo_db(mongo_client):
    """MongoDB 데이터베이스"""
    return mongo_client.get_database("pipeline_test")


@pytest.fixture()
def _clean_mongo(mongo_db):
    """각 테스트 후 MongoDB 컬렉션 데이터를 삭제한다.

    teardown 실패가 다음 테스트로 cascade하지 않도록
    개별 컬렉션 삭제를 try/except로 보호한다.
    """
    yield
    for coll_name in ("raw_data", "analyze_tasks", "outbox"):
        try:
            mongo_db[coll_name].delete_many({})
        except Exception:
            pass


# === Redis ===


@pytest.fixture(scope="session")
def redis_client(_set_env):
    """Redis 클라이언트"""
    import redis as redis_lib

    return redis_lib.Redis.from_url(os.environ["REDIS_URL"])


@pytest.fixture()
def _clean_redis(redis_client):
    """각 테스트 후 Redis 데이터를 삭제한다."""
    yield
    try:
        redis_client.flushdb()
    except Exception:
        pass


# === Repository Fixture ===


@pytest.fixture()
def selection_repo(db_session):
    from app.adapter.outbound.mysql.repositories import SqlSelectionRepository

    return SqlSelectionRepository(db_session)


@pytest.fixture()
def odd_tag_repo(db_session):
    from app.adapter.outbound.mysql.repositories import SqlOddTagRepository

    return SqlOddTagRepository(db_session)


@pytest.fixture()
def label_repo(db_session):
    from app.adapter.outbound.mysql.repositories import SqlLabelRepository

    return SqlLabelRepository(db_session)


@pytest.fixture()
def rejection_repo(db_session):
    from app.adapter.outbound.mysql.repositories import SqlRejectionRepository

    return SqlRejectionRepository(db_session)


@pytest.fixture()
def search_repo(db_session):
    from app.adapter.outbound.mysql.repositories import SqlDataSearchRepository

    return SqlDataSearchRepository(db_session)


@pytest.fixture()
def raw_data_repo(mongo_db):
    from app.adapter.outbound.mongodb.repositories import MongoRawDataRepository

    return MongoRawDataRepository(mongo_db)


@pytest.fixture()
def task_repo(mongo_db):
    from app.adapter.outbound.mongodb.repositories import MongoTaskRepository

    return MongoTaskRepository(mongo_db)


@pytest.fixture()
def outbox_repo(mongo_db):
    from app.adapter.outbound.mongodb.repositories import MongoOutboxRepository

    return MongoOutboxRepository(mongo_db)


@pytest.fixture()
def cache_repo(redis_client):
    from app.adapter.outbound.redis.repositories import RedisCacheRepository

    return RedisCacheRepository(redis_client)


# === Service Fixture ===


@pytest.fixture()
def pipeline_service(db_session, mongo_db, redis_client, task_repo, cache_repo):
    """PipelineService — pipeline_task._build_pipeline_service 패턴을 따른다."""
    from app.adapter.outbound.mongodb.repositories import MongoRawDataRepository
    from app.adapter.outbound.mysql.repositories import (
        SqlLabelRepository,
        SqlOddTagRepository,
        SqlRejectionRepository,
        SqlSelectionRepository,
    )
    from app.application.phase_runners import (
        LabelPhaseRunner,
        OddTagPhaseRunner,
        PhaseRunnerProvider,
        SelectionPhaseRunner,
    )
    from app.application.pipeline_service import PipelineService
    from app.domain.enums import Stage

    raw_repo = MongoRawDataRepository(mongo_db)
    rej_repo = SqlRejectionRepository(db_session)
    sel_repo = SqlSelectionRepository(db_session)
    odd_repo = SqlOddTagRepository(db_session)
    lbl_repo = SqlLabelRepository(db_session)

    provider = PhaseRunnerProvider()
    provider.register(
        Stage.SELECTION,
        SelectionPhaseRunner(
            raw_data_repo=raw_repo,
            task_repo=task_repo,
            rejection_repo=rej_repo,
            selection_repo=sel_repo,
        ),
    )
    provider.register(
        Stage.ODD_TAGGING,
        OddTagPhaseRunner(
            raw_data_repo=raw_repo,
            task_repo=task_repo,
            rejection_repo=rej_repo,
            odd_tag_repo=odd_repo,
        ),
    )
    provider.register(
        Stage.AUTO_LABELING,
        LabelPhaseRunner(
            raw_data_repo=raw_repo,
            task_repo=task_repo,
            rejection_repo=rej_repo,
            label_repo=lbl_repo,
        ),
    )

    return PipelineService(
        task_repo=task_repo,
        selection_repo=sel_repo,
        odd_tag_repo=odd_repo,
        label_repo=lbl_repo,
        cache_repo=cache_repo,
        phase_runner_provider=provider,
    )


# === FastAPI TestClient ===


@pytest.fixture()
def client(db_session, mongo_db, redis_client, mongo_client):
    """DI override가 적용된 FastAPI TestClient

    lifespan을 무시하고 (raise_server_exceptions=False 대신)
    이미 테스트 fixture에서 테이블/인덱스를 생성했으므로
    lifespan의 create_tables/ensure_indexes를 skip한다.
    """
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.adapter.outbound.mongodb.repositories import (
        MongoOutboxRepository,
        MongoRawDataRepository,
        MongoTaskRepository,
    )
    from app.adapter.outbound.mongodb.transaction import MongoTransactionManager
    from app.adapter.outbound.mysql.repositories import (
        SqlDataSearchRepository,
        SqlLabelRepository,
        SqlOddTagRepository,
        SqlRejectionRepository,
        SqlSelectionRepository,
    )
    from app.adapter.outbound.redis.repositories import RedisCacheRepository
    from app.application.file_loaders import CsvFileLoader, FileLoaderProvider, JsonFileLoader
    from app.rest_dependencies import (
        get_cache_repo,
        get_db,
        get_db_session,
        get_label_repo,
        get_loader_provider,
        get_odd_tag_repo,
        get_outbox_repo,
        get_raw_data_repo,
        get_rejection_repo,
        get_search_repo,
        get_selection_repo,
        get_task_repo,
        get_tx_manager,
    )
    from app.domain.enums import FileType
    from app.main import app

    def _db_session():
        yield db_session

    def _db():
        return mongo_db

    app.dependency_overrides[get_db_session] = _db_session
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_selection_repo] = lambda: SqlSelectionRepository(db_session)
    app.dependency_overrides[get_odd_tag_repo] = lambda: SqlOddTagRepository(db_session)
    app.dependency_overrides[get_label_repo] = lambda: SqlLabelRepository(db_session)
    app.dependency_overrides[get_rejection_repo] = lambda: SqlRejectionRepository(db_session)
    app.dependency_overrides[get_search_repo] = lambda: SqlDataSearchRepository(db_session)
    app.dependency_overrides[get_raw_data_repo] = lambda: MongoRawDataRepository(mongo_db)
    app.dependency_overrides[get_task_repo] = lambda: MongoTaskRepository(mongo_db)
    app.dependency_overrides[get_outbox_repo] = lambda: MongoOutboxRepository(mongo_db)
    app.dependency_overrides[get_tx_manager] = lambda: MongoTransactionManager(mongo_client)
    app.dependency_overrides[get_cache_repo] = lambda: RedisCacheRepository(redis_client)

    # CsvFileLoader는 파일별로 다른 required_headers를 사용해야 하지만,
    def _loader_provider():
        provider = FileLoaderProvider()
        provider.register(FileType.JSON, JsonFileLoader())
        provider.register(FileType.CSV, CsvFileLoader())
        return provider

    app.dependency_overrides[get_loader_provider] = _loader_provider

    # lifespan의 create_tables/ensure_indexes를 패치하여 기본 DB가 아닌
    # 테스트 DB를 사용하도록 한다
    with (
        patch("app.adapter.outbound.mysql.database.create_tables"),
        patch("app.adapter.outbound.mongodb.client.ensure_indexes"),
        TestClient(app) as tc,
    ):
        yield tc

    app.dependency_overrides.clear()


# === MongoDB 인덱스 생성 ===


@pytest.fixture(scope="session", autouse=True)
def _create_mongo_indexes(mongo_db):
    """테스트 세션 시작 시 MongoDB 인덱스를 생성한다."""
    mongo_db.raw_data.create_index([("task_id", 1), ("source", 1)])
    mongo_db.analyze_tasks.create_index([("status", 1)])
    mongo_db.outbox.create_index([("status", 1), ("created_at", 1)])


# === 자동 정리 ===


@pytest.fixture(autouse=True)
def _auto_clean(_clean_mysql, _clean_mongo, _clean_redis):
    """모든 통합 테스트에서 자동으로 데이터 정리를 수행한다."""
    yield
