import pytest

from app.application.odd_tag_refiner import OddTagRefiner
from app.domain.enums import RejectionReason, RoadSurface, TimeOfDay, Weather
from app.domain.models import OddTag, Rejection


@pytest.fixture
def refiner():
    return OddTagRefiner()


def _odd_row(**overrides) -> dict:
    base = {
        "id": 1,
        "video_id": "100",
        "weather": "sunny",
        "time_of_day": "day",
        "road_surface": "dry",
    }
    base.update(overrides)
    return base


class TestOddTagRefinerNormal:

    def test_정상_파싱(self, refiner):
        result = refiner.refine_single("task-1", _odd_row())

        assert isinstance(result, OddTag)
        assert result.id == 1
        assert result.video_id.value == 100
        assert result.weather == Weather.SUNNY
        assert result.time_of_day == TimeOfDay.DAY
        assert result.road_surface == RoadSurface.DRY

    def test_video_id_앞의_0_제거(self, refiner):
        result = refiner.refine_single("task-1", _odd_row(video_id="0042"))

        assert isinstance(result, OddTag)
        assert result.video_id.value == 42


class TestOddTagRefinerMissingFields:

    def test_weather_누락시_missing_required_field(self, refiner):
        row = _odd_row()
        del row["weather"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.MISSING_REQUIRED_FIELD and r.field == "weather" for r in result)

    def test_time_of_day_누락시_missing_required_field(self, refiner):
        row = _odd_row()
        del row["time_of_day"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.MISSING_REQUIRED_FIELD and r.field == "time_of_day" for r in result)

    def test_road_surface_누락시_missing_required_field(self, refiner):
        row = _odd_row()
        del row["road_surface"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.MISSING_REQUIRED_FIELD and r.field == "road_surface" for r in result)


class TestOddTagRefinerInvalidEnum:

    def test_weather_잘못된_값_invalid_enum_value(self, refiner):
        result = refiner.refine_single("task-1", _odd_row(weather="tornado"))

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.INVALID_ENUM_VALUE and r.field == "weather" for r in result)

    def test_time_of_day_잘못된_값(self, refiner):
        result = refiner.refine_single("task-1", _odd_row(time_of_day="dusk"))

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.INVALID_ENUM_VALUE and r.field == "time_of_day" for r in result)

    def test_road_surface_잘못된_값(self, refiner):
        result = refiner.refine_single("task-1", _odd_row(road_surface="gravel"))

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.INVALID_ENUM_VALUE and r.field == "road_surface" for r in result)


class TestOddTagRefinerMultipleErrors:

    def test_다중_에러_수집(self, refiner):
        row = _odd_row(weather="tornado", time_of_day="dusk", road_surface="gravel")
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert len(result) == 3
        fields = {r.field for r in result}
        assert fields == {"weather", "time_of_day", "road_surface"}

    def test_누락과_잘못된값_혼합_에러(self, refiner):
        row = _odd_row(weather="tornado")
        del row["road_surface"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert len(result) >= 2
        reasons = {r.reason for r in result}
        assert RejectionReason.INVALID_ENUM_VALUE in reasons
        assert RejectionReason.MISSING_REQUIRED_FIELD in reasons

    def test_빈_dict_모든_필드_누락(self, refiner):
        """빈 dict는 id, video_id, weather, time_of_day, road_surface 모두 누락으로 최소 3건 이상 Rejection"""
        result = refiner.refine_single("task-1", {})

        assert isinstance(result, list)
        assert len(result) >= 3
        fields = {r.field for r in result}
        assert "weather" in fields
        assert "time_of_day" in fields
        assert "road_surface" in fields
