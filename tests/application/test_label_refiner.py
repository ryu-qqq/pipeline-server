import pytest

from app.application.label_refiner import LabelRefiner
from app.domain.enums import ObjectClass, RejectionReason
from app.domain.models import Label, Rejection


@pytest.fixture
def refiner():
    return LabelRefiner()


def _label_row(**overrides) -> dict:
    base = {
        "video_id": 100,
        "object_class": "car",
        "obj_count": 5,
        "avg_confidence": 0.95,
        "labeled_at": "2025-03-01T12:00:00",
    }
    base.update(overrides)
    return base


class TestLabelRefinerNormal:

    def test_정상_파싱(self, refiner):
        result = refiner.refine_single("task-1", _label_row())

        assert isinstance(result, Label)
        assert result.video_id.value == 100
        assert result.object_class == ObjectClass.CAR
        assert result.obj_count.value == 5
        assert result.confidence.value == 0.95

    def test_obj_count_0_정상(self, refiner):
        result = refiner.refine_single("task-1", _label_row(obj_count=0))

        assert isinstance(result, Label)
        assert result.obj_count.value == 0


class TestLabelRefinerFractionalObjCount:

    def test_소수점_obj_count_rejection(self, refiner):
        result = refiner.refine_single("task-1", _label_row(obj_count=3.5))

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.FRACTIONAL_OBJ_COUNT and r.field == "obj_count" for r in result)

    def test_정수형_실수_obj_count_정상(self, refiner):
        """5.0처럼 정수와 동일한 실수는 정상 처리"""
        result = refiner.refine_single("task-1", _label_row(obj_count=5.0))

        assert isinstance(result, Label)
        assert result.obj_count.value == 5


class TestLabelRefinerNegativeObjCount:

    def test_음수_obj_count_rejection(self, refiner):
        result = refiner.refine_single("task-1", _label_row(obj_count=-1))

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.NEGATIVE_OBJ_COUNT and r.field == "obj_count" for r in result)


class TestLabelRefinerMissingFields:

    def test_object_class_누락(self, refiner):
        row = _label_row()
        del row["object_class"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.MISSING_REQUIRED_FIELD and r.field == "object_class" for r in result)

    def test_avg_confidence_누락(self, refiner):
        row = _label_row()
        del row["avg_confidence"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert any(r.field == "avg_confidence" for r in result)

    def test_잘못된_object_class(self, refiner):
        result = refiner.refine_single("task-1", _label_row(object_class="airplane"))

        assert isinstance(result, list)
        assert any(r.reason == RejectionReason.INVALID_ENUM_VALUE and r.field == "object_class" for r in result)


class TestLabelRefinerMultipleErrors:

    def test_다중_에러_수집(self, refiner):
        row = _label_row(obj_count=3.5, object_class="airplane")
        del row["avg_confidence"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert len(result) >= 3
        fields = {r.field for r in result}
        assert "obj_count" in fields
        assert "object_class" in fields
        assert "avg_confidence" in fields

    def test_video_id와_obj_count_동시_에러(self, refiner):
        row = _label_row(obj_count=-2)
        del row["video_id"]
        result = refiner.refine_single("task-1", row)

        assert isinstance(result, list)
        assert len(result) >= 2

    def test_빈_dict_모든_필드_누락(self, refiner):
        """빈 dict는 video_id, object_class, obj_count, avg_confidence, labeled_at 모두 누락"""
        result = refiner.refine_single("task-1", {})

        assert isinstance(result, list)
        assert len(result) >= 4
        fields = {r.field for r in result}
        assert "video_id" in fields
        assert "object_class" in fields
        assert "obj_count" in fields
        assert "avg_confidence" in fields
