import csv
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path

import ijson

from app.domain.enums import FileType
from app.domain.exceptions import DataNotFoundError, InvalidFormatError

RawData = dict  # type alias -- 검증 전 원본 데이터


class FileLoader(ABC):
    """파일을 읽어 원본 데이터를 yield하는 전략 인터페이스"""

    @abstractmethod
    def load(self, path: Path) -> Iterator[RawData]: ...


class JsonFileLoader(FileLoader):
    """JSON 파일 로더 -- ijson 스트리밍으로 한 건씩 yield (메모리에 전체 로드 안 함)"""

    def load(self, path: Path) -> Iterator[RawData]:
        try:
            f = open(path, "rb")  # noqa: SIM115
        except FileNotFoundError as err:
            raise DataNotFoundError(f"파일을 찾을 수 없습니다: {path}") from err

        with f:
            try:
                yield from ijson.items(f, "item", use_float=True)
            except ijson.JSONError as e:
                raise InvalidFormatError(f"JSON 파싱 실패: {path} -- {e}") from e
            except UnicodeDecodeError as err:
                raise InvalidFormatError(f"파일 인코딩 오류: {path}") from err


class CsvFileLoader(FileLoader):
    """CSV 파일 로더 -- 스트리밍으로 한 건씩 yield (메모리에 안 올림)

    필드 검증은 Refiner에서 수행하므로, 로더는 파싱만 담당한다.
    """

    def load(self, path: Path) -> Iterator[RawData]:
        try:
            f = open(path, newline="", encoding="utf-8")  # noqa: SIM115
        except FileNotFoundError as err:
            raise DataNotFoundError(f"파일을 찾을 수 없습니다: {path}") from err

        with f:
            try:
                yield from csv.DictReader(f)
            except UnicodeDecodeError as err:
                raise InvalidFormatError(f"CSV 읽기 중 인코딩 오류: {path}") from err


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
