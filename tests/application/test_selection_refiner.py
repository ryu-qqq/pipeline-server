import pytest

from app.application.selection_refiner import SelectionRefiner
from app.domain.enums import RejectionReason
from app.domain.models import Selection


@pytest.fixture
def refiner():
    return SelectionRefiner()


# === V1 스키마 ===


def _v1_row(**overrides) -> dict:
    base = {
        "id": 100,
        "recordedAt": "2025-01-15T10:30:00",
        "temperature": 25.0,
        "isWiperOn": False,
        "headlightsOn": True,
        "sourcePath": "/raw/video_100.mp4",
    }
    base.update(overrides)
    return base


class TestSelectionRefinerV1:

    def test_v1_정상_파싱(self, refiner):
        result = refiner.refine_single("task-1", _v1_row())

        assert isinstance(result, Selection)
        assert result.id.value == 100
        assert result.task_id == "task-1"
        assert result.temperature.celsius == 25.0
        assert result.wiper.active is False
        assert result.headlights_on is True
        assert result.source_path.value == "/raw/video_100.mp4"

    def test_v1_id_누락시_rejection(self, refiner):
        row = _v1_row()
        del row["id"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.INVALID_FORMAT and r.field == "id" for r in result)

    def test_v1_temperature_누락시_unknown_schema(self, refiner):
        """temperature 필드가 V1 스키마 감지 키이므로 삭제하면 unknown_schema"""
        row = _v1_row()
        del row["temperature"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert result[0].reason == RejectionReason.UNKNOWN_SCHEMA

    def test_v1_temperature_잘못된_값_rejection(self, refiner):
        result = refiner.refine_single("task-1", _v1_row(temperature="not_a_number"))

        assert isinstance(result, list)
        assert any(r.field == "temperature" for r in result)

    def test_v1_wiper_누락시_rejection(self, refiner):
        row = _v1_row()
        del row["isWiperOn"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.MISSING_REQUIRED_FIELD and r.field == "isWiperOn" for r in result)

    def test_v1_headlightsOn_누락시_rejection(self, refiner):
        row = _v1_row()
        del row["headlightsOn"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.MISSING_REQUIRED_FIELD and r.field == "headlightsOn" for r in result)

    def test_v1_sourcePath_잘못된_확장자(self, refiner):
        result = refiner.refine_single("task-1", _v1_row(sourcePath="/raw/video.avi"))

        assert isinstance(result, list)
        assert any(r.field == "sourcePath" for r in result)

    def test_v1_다중_필드_에러시_모든_rejection_반환(self, refiner):
        """temperature는 스키마 감지 키이므로 유지하되, 잘못된 값 + 다른 필드 누락"""
        row = _v1_row(temperature="invalid")
        del row["isWiperOn"]
        del row["headlightsOn"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert len(result) >= 3
        fields = {r.field for r in result}
        assert "temperature" in fields
        assert "isWiperOn" in fields
        assert "headlightsOn" in fields


# === V2 스키마 ===


def _v2_row(**overrides) -> dict:
    base = {
        "id": 200,
        "recordedAt": "2025-03-20T14:00:00",
        "sourcePath": "/raw/video_200.mp4",
        "sensor": {
            "temperature": {"value": 77.0, "unit": "F"},
            "wiper": {"isActive": True, "level": 2},
            "headlights": True,
        },
    }
    base.update(overrides)
    return base


class TestSelectionRefinerV2:

    def test_v2_정상_파싱_화씨_섭씨_변환(self, refiner):
        result = refiner.refine_single("task-2", _v2_row())

        assert isinstance(result, Selection)
        assert result.id.value == 200
        assert result.temperature.celsius == pytest.approx(25.0, abs=0.1)
        assert result.wiper.active is True
        assert result.wiper.level == 2
        assert result.headlights_on is True

    def test_v2_섭씨_단위_정상_파싱(self, refiner):
        row = _v2_row(sensor={
            "temperature": {"value": 15.0, "unit": "C"},
            "wiper": {"isActive": False, "level": 0},
            "headlights": False,
        })
        result = refiner.refine_single("task-2", row)

        assert isinstance(result, Selection)
        assert result.temperature.celsius == 15.0

    def test_v2_sensor_필드가_dict가_아닌_경우(self, refiner):
        result = refiner.refine_single("task-2", _v2_row(sensor="invalid"))

        assert isinstance(result, list)
        assert any(r.field == "sensor" for r in result)

    def test_v2_알수없는_온도단위_rejection(self, refiner):
        row = _v2_row(sensor={
            "temperature": {"value": 25.0, "unit": "K"},
            "wiper": {"isActive": False, "level": 0},
            "headlights": False,
        })
        result = refiner.refine_single("task-2", row)

        assert isinstance(result, list)
        assert any(r.field == "sensor.temperature.unit" for r in result)

    def test_v2_wiper_누락시_rejection(self, refiner):
        row = _v2_row(sensor={
            "temperature": {"value": 77.0, "unit": "F"},
            "headlights": True,
        })
        result = refiner.refine_single("task-2", row)

        assert isinstance(result, list)
        assert any(r.field == "sensor.wiper" for r in result)

    def test_v2_다중_에러_수집(self, refiner):
        row = _v2_row(sensor={
            "temperature": {"value": 77.0, "unit": "K"},
            "headlights": True,
        })
        result = refiner.refine_single("task-2", row)

        assert isinstance(result, list)
        assert len(result) >= 2


# === 알 수 없는 스키마 ===


class TestSelectionRefinerUnknownSchema:

    def test_unknown_schema_rejection(self, refiner):
        row = {"id": 300, "recordedAt": "2025-01-01T00:00:00", "unknown_field": "x"}
        result = refiner.refine_single("task-3", row)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].reason == RejectionReason.UNKNOWN_SCHEMA
        assert result[0].field == "schema"

    def test_빈_dict_unknown_schema(self, refiner):
        result = refiner.refine_single("task-3", {"id": 1})

        assert isinstance(result, list)
        assert result[0].reason == RejectionReason.UNKNOWN_SCHEMA

    def test_완전한_빈_dict_unknown_schema(self, refiner):
        """빈 dict는 스키마 감지 불가로 UNKNOWN_SCHEMA Rejection을 반환한다"""
        result = refiner.refine_single("task-3", {})

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0].reason == RejectionReason.UNKNOWN_SCHEMA
        assert result[0].source_id == "?"
