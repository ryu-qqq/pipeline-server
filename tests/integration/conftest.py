"""통합 테스트 공통 fixture

컨테이너는 tests/conftest.py에서 session 스코프로 공유한다.
이 파일에서는 환경변수 주입, DB 세션, 데이터 격리만 담당한다.
"""

import contextlib
import os

import pytest
from pymongo import MongoClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

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
        with contextlib.suppress(Exception):
            mongo_db[coll_name].delete_many({})


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
    with contextlib.suppress(Exception):
        redis_client.flushdb()


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


# === Service Fixture ===


@pytest.fixture()
def pipeline_service(db_session, mongo_db, redis_client, task_repo):
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
    from app.application.file_loaders import CsvFileLoader, FileLoaderProvider, JsonFileLoader
    from app.domain.enums import FileType
    from app.main import app
    from app.rest_dependencies import (
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

    # CsvFileLoader는 파일별로 다른 required_headers를 사용��야 하지만,
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


def _clean_all_data(db_engine, mongo_db, redis_client):
    """MySQL + MongoDB + Redis 데이터를 모두 삭제한다."""
    with db_engine.connect() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in ("rejections", "labels", "odd_tags", "selections"):
            conn.execute(text(f"DELETE FROM {table}"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
        conn.commit()
    for coll_name in ("raw_data", "analyze_tasks", "outbox"):
        with contextlib.suppress(Exception):
            mongo_db[coll_name].delete_many({})
    with contextlib.suppress(Exception):
        redis_client.flushdb()


@pytest.fixture(autouse=True)
def _auto_clean(_clean_mysql, _clean_mongo, _clean_redis):
    """모든 통합 테스트에서 자동으로 데이터 정리를 수행한다."""
    yield


# === 클래스 스코프 fixture (읽기 전용 테스트 공유용) ===


@pytest.fixture(scope="class")
def class_db_session(_session_factory):
    """클래스 스코프 MySQL 세션"""
    session = _session_factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="class")
def class_client(class_db_session, mongo_db, redis_client, mongo_client):
    """클래스 스코프 FastAPI TestClient"""
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
    from app.application.file_loaders import CsvFileLoader, FileLoaderProvider, JsonFileLoader
    from app.domain.enums import FileType
    from app.main import app
    from app.rest_dependencies import (
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

    def _db_session():
        yield class_db_session

    app.dependency_overrides[get_db_session] = _db_session
    app.dependency_overrides[get_db] = lambda: mongo_db
    app.dependency_overrides[get_selection_repo] = lambda: SqlSelectionRepository(class_db_session)
    app.dependency_overrides[get_odd_tag_repo] = lambda: SqlOddTagRepository(class_db_session)
    app.dependency_overrides[get_label_repo] = lambda: SqlLabelRepository(class_db_session)
    app.dependency_overrides[get_rejection_repo] = lambda: SqlRejectionRepository(class_db_session)
    app.dependency_overrides[get_search_repo] = lambda: SqlDataSearchRepository(class_db_session)
    app.dependency_overrides[get_raw_data_repo] = lambda: MongoRawDataRepository(mongo_db)
    app.dependency_overrides[get_task_repo] = lambda: MongoTaskRepository(mongo_db)
    app.dependency_overrides[get_outbox_repo] = lambda: MongoOutboxRepository(mongo_db)
    app.dependency_overrides[get_tx_manager] = lambda: MongoTransactionManager(mongo_client)

    def _loader_provider():
        provider = FileLoaderProvider()
        provider.register(FileType.JSON, JsonFileLoader())
        provider.register(FileType.CSV, CsvFileLoader())
        return provider

    app.dependency_overrides[get_loader_provider] = _loader_provider

    with (
        patch("app.adapter.outbound.mysql.database.create_tables"),
        patch("app.adapter.outbound.mongodb.client.ensure_indexes"),
        TestClient(app) as tc,
    ):
        yield tc

    app.dependency_overrides.clear()


@pytest.fixture(scope="class")
def class_pipeline_service(class_db_session, mongo_db):
    """클래스 스코프 PipelineService"""
    from app.adapter.outbound.mongodb.repositories import (
        MongoRawDataRepository,
        MongoTaskRepository,
    )
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

    task_repo = MongoTaskRepository(mongo_db)
    raw_repo = MongoRawDataRepository(mongo_db)
    rej_repo = SqlRejectionRepository(class_db_session)
    sel_repo = SqlSelectionRepository(class_db_session)
    odd_repo = SqlOddTagRepository(class_db_session)
    lbl_repo = SqlLabelRepository(class_db_session)

    provider = PhaseRunnerProvider()
    provider.register(
        Stage.SELECTION,
        SelectionPhaseRunner(
            raw_data_repo=raw_repo, task_repo=task_repo,
            rejection_repo=rej_repo, selection_repo=sel_repo,
        ),
    )
    provider.register(
        Stage.ODD_TAGGING,
        OddTagPhaseRunner(
            raw_data_repo=raw_repo, task_repo=task_repo,
            rejection_repo=rej_repo, odd_tag_repo=odd_repo,
        ),
    )
    provider.register(
        Stage.AUTO_LABELING,
        LabelPhaseRunner(
            raw_data_repo=raw_repo, task_repo=task_repo,
            rejection_repo=rej_repo, label_repo=lbl_repo,
        ),
    )

    return PipelineService(
        task_repo=task_repo,
        selection_repo=sel_repo,
        odd_tag_repo=odd_repo,
        label_repo=lbl_repo,
        phase_runner_provider=provider,
    )


@pytest.fixture(scope="class")
def shared_task_id(class_client, class_pipeline_service, class_db_session, db_engine, mongo_db, redis_client):
    """파이프라인 1회 실행 후 task_id를 공유한다. 클래스 종료 시 정리."""
    response = class_client.post("/analyze")
    task_id = response.json()["data"]["task_id"]
    class_pipeline_service.execute(task_id)
    class_db_session.commit()
    yield task_id
    _clean_all_data(db_engine, mongo_db, redis_client)
