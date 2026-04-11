"""테스트 루트 conftest — testcontainers를 session 스코프로 한 번만 생성한다.

adapter/conftest.py와 integration/conftest.py가 각각 MySQL 컨테이너를 생성하면
Docker 데몬 과부하로 타임아웃이 발생한다.
루트에서 컨테이너를 한 번 생성하고 하위 conftest가 공유하여 해결한다.
"""

import time

import pytest
from pymongo import MongoClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
from testcontainers.mysql import MySqlContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def mysql_container():
    """MySQL 8.0 테스트 컨테이너 — 전체 테스트에서 공유"""
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
    """MongoDB 7.0 테스트 컨테이너 (replica set) — 전체 테스트에서 공유"""
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
    """Redis 7.0 테스트 컨테이너 — 전체 테스트에서 공유"""
    container = RedisContainer(image="redis:7.0")
    with container:
        yield container
