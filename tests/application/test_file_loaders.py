"""FileLoader 단위 테스트 -- JsonFileLoader, CsvFileLoader, FileLoaderProvider"""

from pathlib import Path

import pytest

from app.application.file_loaders import (
    CsvFileLoader,
    FileLoaderProvider,
    JsonFileLoader,
)
from app.domain.enums import FileType
from app.domain.exceptions import DataNotFoundError, InvalidFormatError

# ── TestJsonFileLoader ──────────────────────────────────────────────


class TestJsonFileLoader:
    """JSON 파일 로더 단위 테스트"""

    def setup_method(self) -> None:
        self.loader = JsonFileLoader()

    def test_정상_JSON_배열_파싱(self, tmp_path: Path) -> None:
        """정상적인 JSON 배열 파일을 파싱하면 각 요소를 순회할 수 있다"""
        # Arrange
        file = tmp_path / "data.json"
        file.write_text('[{"id": 1}, {"id": 2}]')

        # Act
        result = list(self.loader.load(file))

        # Assert
        assert result == [{"id": 1}, {"id": 2}]

    def test_빈_배열(self, tmp_path: Path) -> None:
        """빈 JSON 배열은 빈 리스트를 반환한다"""
        # Arrange
        file = tmp_path / "empty.json"
        file.write_text("[]")

        # Act
        result = list(self.loader.load(file))

        # Assert
        assert result == []

    def test_존재하지_않는_파일_DataNotFoundError(self) -> None:
        """존재하지 않는 파일 경로는 DataNotFoundError를 발생시킨다"""
        # Arrange
        path = Path("non_existent.json")

        # Act & Assert
        with pytest.raises(DataNotFoundError, match="파일을 찾을 수 없습니다"):
            list(self.loader.load(path))

    def test_잘못된_JSON_InvalidFormatError(self, tmp_path: Path) -> None:
        """파싱 불가능한 JSON은 InvalidFormatError를 발생시킨다"""
        # Arrange
        file = tmp_path / "broken.json"
        file.write_text("{ broken json")

        # Act & Assert
        with pytest.raises(InvalidFormatError, match="JSON 파싱 실패"):
            list(self.loader.load(file))

    def test_JSON_배열이_아닌_경우_빈_결과(self, tmp_path: Path) -> None:
        """최상위가 배열이 아닌 JSON은 빈 결과를 반환한다 (ijson 스트리밍 특성)"""
        # Arrange
        file = tmp_path / "dict.json"
        file.write_text('{"key": "value"}')

        # Act
        result = list(self.loader.load(file))

        # Assert
        assert result == []


# ── TestCsvFileLoader ───────────────────────────────────────────────


class TestCsvFileLoader:
    """CSV 파일 로더 단위 테스트"""

    def setup_method(self) -> None:
        self.loader = CsvFileLoader()

    def test_정상_CSV_파싱(self, tmp_path: Path) -> None:
        """정상적인 CSV 파일을 파싱하면 헤더 기반 dict를 순회할 수 있다"""
        # Arrange
        file = tmp_path / "data.csv"
        file.write_text("id,name\n1,foo\n2,bar")

        # Act
        result = list(self.loader.load(file))

        # Assert -- CSV DictReader는 모든 값을 문자열로 반환한다
        assert result == [{"id": "1", "name": "foo"}, {"id": "2", "name": "bar"}]

    def test_헤더만_있는_CSV(self, tmp_path: Path) -> None:
        """헤더만 있고 데이터 행이 없는 CSV는 빈 리스트를 반환한다"""
        # Arrange
        file = tmp_path / "header_only.csv"
        file.write_text("id,name\n")

        # Act
        result = list(self.loader.load(file))

        # Assert
        assert result == []

    def test_존재하지_않는_CSV_DataNotFoundError(self) -> None:
        """존재하지 않는 CSV 파일 경로는 DataNotFoundError를 발생시킨다"""
        # Arrange
        path = Path("non_existent.csv")

        # Act & Assert
        with pytest.raises(DataNotFoundError, match="파일을 찾을 수 없습니다"):
            list(self.loader.load(path))


# ── TestFileLoaderProvider ──────────────────────────────────────────


class TestFileLoaderProvider:
    """FileLoaderProvider 단위 테스트"""

    def test_등록된_타입_올바른_로더_반환(self) -> None:
        """register한 FileType으로 get_loader하면 해당 로더 인스턴스를 반환한다"""
        # Arrange
        provider = FileLoaderProvider()
        json_loader = JsonFileLoader()
        provider.register(FileType.JSON, json_loader)

        # Act
        result = provider.get_loader(FileType.JSON)

        # Assert
        assert result is json_loader

    def test_미등록_타입_InvalidFormatError(self) -> None:
        """등록하지 않은 FileType으로 get_loader하면 InvalidFormatError를 발생시킨다"""
        # Arrange
        provider = FileLoaderProvider()

        # Act & Assert
        with pytest.raises(InvalidFormatError, match="지원하지 않는 파일 형식"):
            provider.get_loader(FileType.CSV)

    def test_resolve_확장자에서_로더_감지(self) -> None:
        """파일 확장자에서 적절한 로더를 자동으로 감지한다"""
        # Arrange
        provider = FileLoaderProvider()
        json_loader = JsonFileLoader()
        csv_loader = CsvFileLoader()
        provider.register(FileType.JSON, json_loader)
        provider.register(FileType.CSV, csv_loader)

        # Act & Assert
        assert provider.resolve(Path("data.json")) is json_loader
        assert provider.resolve(Path("data.csv")) is csv_loader

    def test_resolve_지원하지_않는_확장자(self) -> None:
        """지원하지 않는 확장자로 resolve하면 InvalidFormatError를 발생시킨다"""
        # Arrange
        provider = FileLoaderProvider()

        # Act & Assert
        with pytest.raises(InvalidFormatError, match="지원하지 않는 파일 확장자"):
            provider.resolve(Path("data.xml"))
