import pytest

from app.domain.exceptions import (
    InvalidFormatError,
    NegativeCountError,
    TemperatureConversionError,
)
from app.domain.value_objects import (
    Confidence,
    ObjectCount,
    SourcePath,
    StageProgress,
    Temperature,
    VideoId,
    WiperState,
)

# === VideoId ===


class TestVideoId:
    def test_valid_id(self):
        vid = VideoId(value=1)
        assert vid.value == 1
        assert int(vid) == 1

    def test_zero_rejected(self):
        with pytest.raises(InvalidFormatError):
            VideoId(value=0)

    def test_negative_rejected(self):
        with pytest.raises(InvalidFormatError):
            VideoId(value=-1)

    def test_equality_with_same_type(self):
        assert VideoId(1) == VideoId(1)
        assert VideoId(1) != VideoId(2)

    def test_equality_with_int(self):
        assert VideoId(5) == 5
        assert VideoId(5) != 6

    def test_hash_consistency(self):
        assert hash(VideoId(1)) == hash(VideoId(1))


# === Temperature ===


class TestTemperature:
    def test_valid_range_boundary(self):
        low = Temperature(celsius=-90)
        high = Temperature(celsius=60)
        assert low.celsius == -90
        assert high.celsius == 60

    def test_below_min_rejected(self):
        with pytest.raises(TemperatureConversionError):
            Temperature(celsius=-91)

    def test_above_max_rejected(self):
        with pytest.raises(TemperatureConversionError):
            Temperature(celsius=61)

    def test_from_celsius(self):
        t = Temperature.from_celsius(25.556)
        assert t.celsius == 25.56

    def test_from_fahrenheit_freezing(self):
        t = Temperature.from_fahrenheit(32)
        assert t.celsius == 0.0

    def test_from_fahrenheit_boiling(self):
        # 100°F → 37.78°C
        t = Temperature.from_fahrenheit(100)
        assert t.celsius == pytest.approx(37.78, abs=0.01)

    def test_from_fahrenheit_out_of_range(self):
        # -200°F → celsius 범위 초과
        with pytest.raises(TemperatureConversionError):
            Temperature.from_fahrenheit(-200)

    def test_nan_rejected(self):
        with pytest.raises(TemperatureConversionError, match="유효하지 않은 온도값"):
            Temperature(celsius=float("nan"))

    def test_infinity_rejected(self):
        with pytest.raises(TemperatureConversionError, match="유효하지 않은 온도값"):
            Temperature(celsius=float("inf"))

    def test_negative_infinity_rejected(self):
        with pytest.raises(TemperatureConversionError, match="유효하지 않은 온도값"):
            Temperature(celsius=float("-inf"))

    def test_from_fahrenheit_nan_rejected(self):
        with pytest.raises(TemperatureConversionError, match="유효하지 않은 화씨"):
            Temperature.from_fahrenheit(float("nan"))

    def test_from_fahrenheit_infinity_rejected(self):
        with pytest.raises(TemperatureConversionError, match="유효하지 않은 화씨"):
            Temperature.from_fahrenheit(float("inf"))


# === Confidence ===


class TestConfidence:
    def test_valid_boundaries(self):
        assert Confidence(0.0).value == 0.0
        assert Confidence(1.0).value == 1.0

    def test_below_zero_rejected(self):
        with pytest.raises(InvalidFormatError):
            Confidence(-0.01)

    def test_above_one_rejected(self):
        with pytest.raises(InvalidFormatError):
            Confidence(1.01)

    def test_is_high_default_threshold(self):
        assert Confidence(0.9).is_high() is True
        assert Confidence(0.89).is_high() is False

    def test_is_high_custom_threshold(self):
        assert Confidence(0.8).is_high(threshold=0.8) is True

    def test_is_low_default_threshold(self):
        assert Confidence(0.59).is_low() is True
        assert Confidence(0.6).is_low() is False

    def test_is_low_custom_threshold(self):
        assert Confidence(0.49).is_low(threshold=0.5) is True

    def test_nan_rejected(self):
        with pytest.raises(InvalidFormatError, match="유효하지 않은 신뢰도"):
            Confidence(float("nan"))

    def test_infinity_rejected(self):
        with pytest.raises(InvalidFormatError, match="유효하지 않은 신뢰도"):
            Confidence(float("inf"))


# === ObjectCount ===


class TestObjectCount:
    def test_valid_zero(self):
        oc = ObjectCount(0)
        assert oc.value == 0
        assert oc.is_empty() is True

    def test_valid_positive(self):
        oc = ObjectCount(5)
        assert oc.is_empty() is False
        assert int(oc) == 5

    def test_negative_rejected(self):
        with pytest.raises(NegativeCountError):
            ObjectCount(-1)

    def test_ge_with_same_type(self):
        assert ObjectCount(3) >= ObjectCount(2)
        assert ObjectCount(2) >= ObjectCount(2)
        assert not (ObjectCount(1) >= ObjectCount(2))

    def test_ge_with_int(self):
        assert ObjectCount(3) >= 2
        assert ObjectCount(0) >= 0


# === WiperState ===


class TestWiperState:
    def test_active_with_valid_level(self):
        ws = WiperState(active=True, level=2)
        assert ws.active is True
        assert ws.level == 2

    def test_inactive_with_none_level(self):
        ws = WiperState(active=False)
        assert ws.level is None

    def test_inactive_with_zero_level(self):
        ws = WiperState(active=False, level=0)
        assert ws.level == 0

    def test_level_below_zero_rejected(self):
        with pytest.raises(InvalidFormatError):
            WiperState(active=True, level=-1)

    def test_level_above_three_rejected(self):
        with pytest.raises(InvalidFormatError):
            WiperState(active=True, level=4)

    def test_inactive_with_positive_level_rejected(self):
        with pytest.raises(InvalidFormatError):
            WiperState(active=False, level=1)

    def test_is_raining_likely_true(self):
        assert WiperState(active=True, level=2).is_raining_likely() is True
        assert WiperState(active=True, level=3).is_raining_likely() is True

    def test_is_raining_likely_false(self):
        assert WiperState(active=True, level=1).is_raining_likely() is False
        assert WiperState(active=False).is_raining_likely() is False
        assert WiperState(active=True, level=None).is_raining_likely() is False


# === SourcePath ===


class TestSourcePath:
    def test_valid_mp4(self):
        sp = SourcePath("/data/raw/video.mp4")
        assert sp.value == "/data/raw/video.mp4"

    def test_empty_rejected(self):
        with pytest.raises(InvalidFormatError):
            SourcePath("")

    def test_non_mp4_rejected(self):
        with pytest.raises(InvalidFormatError):
            SourcePath("/data/video.avi")

    def test_is_raw(self):
        assert SourcePath("/data/raw/v.mp4").is_raw() is True
        assert SourcePath("/data/processed/v.mp4").is_raw() is False

    def test_is_processed(self):
        assert SourcePath("/data/processed/v.mp4").is_processed() is True
        assert SourcePath("/data/raw/v.mp4").is_processed() is False


# === StageProgress ===


class TestStageProgress:
    def test_percent_normal(self):
        sp = StageProgress(total=100, processed=50, rejected=10)
        assert sp.percent == 60.0

    def test_percent_total_zero(self):
        sp = StageProgress(total=0, processed=0, rejected=0)
        assert sp.percent == 0.0

    def test_percent_all_processed(self):
        sp = StageProgress(total=10, processed=10, rejected=0)
        assert sp.percent == 100.0

    def test_default_values(self):
        sp = StageProgress()
        assert sp.total == 0
        assert sp.processed == 0
        assert sp.rejected == 0
