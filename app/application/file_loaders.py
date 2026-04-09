import csv
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

from app.domain.enums import FileType
from app.domain.exceptions import DataNotFoundError, InvalidFormatError

RawData = dict  # type alias -- 검증 전 원본 데이터


class FileLoader(ABC):
    """파일을 읽어 원본 데이터를 yield하는 전략 인터페이스"""

    @abstractmethod
    def load(self, path: Path) -> Iterator[RawData]: ...


class JsonFileLoader(FileLoader):
    """JSON 파일 로더 -- 전체 파싱 후 한 건씩 yield"""

    def load(self, path: Path) -> Iterator[RawData]:
        try:
            with open(path) as f:
                raw_list = json.load(f)
        except FileNotFoundError as err:
            raise DataNotFoundError(f"파일을 찾을 수 없습니다: {path}") from err
        except json.JSONDecodeError as e:
            raise InvalidFormatError(f"JSON 파싱 실패: {path} -- {e}") from e

        if not isinstance(raw_list, list):
            raise InvalidFormatError(f"JSON 파일은 배열이어야 합니다: {type(raw_list).__name__}")

        yield from raw_list


class CsvFileLoader(FileLoader):
    """CSV 파일 로더 -- 스트리밍으로 한 건씩 yield (메모리에 안 올림)"""

    def __init__(self, required_headers: set[str]) -> None:
        self._required_headers = required_headers

    def load(self, path: Path) -> Iterator[RawData]:
        try:
            f = open(path, newline="")  # noqa: SIM115
        except FileNotFoundError as err:
            raise DataNotFoundError(f"파일을 찾을 수 없습니다: {path}") from err

        with f:
            reader = csv.DictReader(f)

            if reader.fieldnames is not None:
                actual_headers = set(reader.fieldnames)
                missing = self._required_headers - actual_headers
                if missing:
                    raise InvalidFormatError(f"CSV 필수 헤더 누락: {path} -- {sorted(missing)}")

            yield from reader


class FileLoaderProvider:
    """FileType에 맞는 FileLoader를 반환하는 프로바이더"""

    def __init__(self) -> None:
        self._loaders: dict[FileType, FileLoader] = {}

    def register(self, file_type: FileType, loader: FileLoader) -> None:
        self._loaders[file_type] = loader

    def get_loader(self, file_type: FileType) -> FileLoader:
        loader = self._loaders.get(file_type)
        if loader is None:
            raise InvalidFormatError(f"지원하지 않는 파일 형식: {file_type}")
        return loader

    def resolve(self, path: Path) -> FileLoader:
        """파일 확장자에서 FileType을 감지하여 적절한 로더를 반환한다."""
        suffix = path.suffix.lstrip(".")
        try:
            file_type = FileType(suffix)
        except ValueError as err:
            raise InvalidFormatError(f"지원하지 않는 파일 확장자: {path.suffix}") from err
        return self.get_loader(file_type)
