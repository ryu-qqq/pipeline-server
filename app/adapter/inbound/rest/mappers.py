from app.adapter.inbound.rest.schemas import (
    AnalysisResponse,
    DataSearchRequest,
    LabelResponse,
    RejectionResponse,
    RejectionSearchRequest,
    SearchResultResponse,
    StageProgressResponse,
    StageResultResponse,
    TaskProgressResponse,
    TaskResponse,
)
from app.domain.models import (
    AnalysisResult,
    AnalyzeTask,
    DataSearchCriteria,
    Rejection,
    RejectionCriteria,
    SearchResult,
)


class AnalysisResponseMapper:
    @staticmethod
    def from_domain(result: AnalysisResult) -> AnalysisResponse:
        return AnalysisResponse(
            selection=StageResultResponse(
                total=result.selection.total,
                loaded=result.selection.loaded,
                rejected=result.selection.rejected,
            ),
            odd_tagging=StageResultResponse(
                total=result.odd_tagging.total,
                loaded=result.odd_tagging.loaded,
                rejected=result.odd_tagging.rejected,
            ),
            auto_labeling=StageResultResponse(
                total=result.auto_labeling.total,
                loaded=result.auto_labeling.loaded,
                rejected=result.auto_labeling.rejected,
            ),
            fully_linked=result.fully_linked,
            partial=result.partial,
        )


class RejectionResponseMapper:
    @staticmethod
    def from_domain(rejection: Rejection) -> RejectionResponse:
        return RejectionResponse(
            stage=rejection.stage.value,
            reason=rejection.reason.value,
            source_id=rejection.source_id,
            field=rejection.field,
            detail=rejection.detail,
            created_at=rejection.created_at,
        )


class SearchResultResponseMapper:
    @staticmethod
    def from_domain(result: SearchResult) -> SearchResultResponse:
        return SearchResultResponse(
            video_id=result.selection.id.value,
            recorded_at=result.selection.recorded_at,
            temperature_celsius=result.selection.temperature.celsius,
            wiper_active=result.selection.wiper.active,
            wiper_level=result.selection.wiper.level,
            headlights_on=result.selection.headlights_on,
            source_path=result.selection.source_path.value,
            weather=result.odd_tag.weather.value if result.odd_tag else None,
            time_of_day=result.odd_tag.time_of_day.value if result.odd_tag else None,
            road_surface=result.odd_tag.road_surface.value if result.odd_tag else None,
            labels=[
                LabelResponse(
                    object_class=lb.object_class.value,
                    obj_count=lb.obj_count.value,
                    avg_confidence=lb.confidence.value,
                )
                for lb in result.labels
            ],
        )


class RejectionCriteriaMapper:
    @staticmethod
    def to_domain(request: RejectionSearchRequest) -> RejectionCriteria:
        return RejectionCriteria(
            task_id=request.task_id,
            stage=request.stage,
            reason=request.reason,
            source_id=request.source_id,
            field=request.field,
            page=request.page,
            size=request.size,
            after=request.after,
        )


class DataSearchCriteriaMapper:
    @staticmethod
    def to_domain(request: DataSearchRequest) -> DataSearchCriteria:
        return DataSearchCriteria(
            task_id=request.task_id,
            recorded_at_from=request.recorded_at_from,
            recorded_at_to=request.recorded_at_to,
            min_temperature=request.min_temperature,
            max_temperature=request.max_temperature,
            headlights_on=request.headlights_on,
            weather=request.weather,
            time_of_day=request.time_of_day,
            road_surface=request.road_surface,
            object_class=request.object_class,
            min_obj_count=request.min_obj_count,
            min_confidence=request.min_confidence,
            page=request.page,
            size=request.size,
            after=request.after,
        )


class TaskResponseMapper:
    @staticmethod
    def from_domain(task: AnalyzeTask) -> TaskResponse:
        return TaskResponse(
            task_id=task.task_id,
            status=task.status,
            progress=TaskProgressResponse(
                selection=StageProgressResponse(
                    total=task.selection_progress.total,
                    processed=task.selection_progress.processed,
                    rejected=task.selection_progress.rejected,
                    percent=task.selection_progress.percent,
                ),
                odd_tagging=StageProgressResponse(
                    total=task.odd_tagging_progress.total,
                    processed=task.odd_tagging_progress.processed,
                    rejected=task.odd_tagging_progress.rejected,
                    percent=task.odd_tagging_progress.percent,
                ),
                auto_labeling=StageProgressResponse(
                    total=task.auto_labeling_progress.total,
                    processed=task.auto_labeling_progress.processed,
                    rejected=task.auto_labeling_progress.rejected,
                    percent=task.auto_labeling_progress.percent,
                ),
            ),
            result=AnalysisResponseMapper.from_domain(task.result) if task.result else None,
            error=task.error,
            created_at=task.created_at,
            completed_at=task.completed_at,
        )
