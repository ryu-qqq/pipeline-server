from itertools import islice

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.adapter.outbound.mysql.entities import (
    LabelEntity,
    OddTagEntity,
    RejectionEntity,
    SelectionEntity,
)
from app.adapter.outbound.mysql.mappers import (
    LabelMapper,
    OddTagMapper,
    RejectionMapper,
    SelectionMapper,
)
from app.adapter.outbound.mysql.query_builder import RejectionQueryBuilder, DataSearchQueryBuilder
from app.domain.models import Label, OddTag, Rejection, RejectionCriteria, DataSearchCriteria, SearchResult, Selection
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RejectionRepository,
    DataSearchRepository,
    SelectionRepository,
)

DEFAULT_CHUNK_SIZE = 1000


def _chunked(iterable: list, size: int):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


class SqlSelectionRepository(SelectionRepository):
    def __init__(self, session: Session, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._session = session
        self._chunk_size = chunk_size

    def save_all(self, selections: list[Selection]) -> int:
        total_inserted = 0
        for chunk in _chunked(selections, self._chunk_size):
            values = [SelectionMapper.to_dict(s) for s in chunk]
            stmt = insert(SelectionEntity).prefix_with("IGNORE").values(values)
            result = self._session.execute(stmt)
            self._session.flush()
            total_inserted += result.rowcount
        return total_inserted

    def find_by_id(self, selection_id: int) -> Selection | None:
        entity = self._session.get(SelectionEntity, selection_id)
        return SelectionMapper.to_domain(entity) if entity else None

    def find_all_ids_by_task(self, task_id: str) -> set[int]:
        stmt = select(SelectionEntity.id).where(SelectionEntity.task_id == task_id)
        result = self._session.execute(stmt)
        return {row[0] for row in result}


class SqlOddTagRepository(OddTagRepository):
    def __init__(self, session: Session, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._session = session
        self._chunk_size = chunk_size

    def save_all(self, odd_tags: list[OddTag]) -> int:
        total_inserted = 0
        for chunk in _chunked(odd_tags, self._chunk_size):
            values = [OddTagMapper.to_dict(o) for o in chunk]
            stmt = insert(OddTagEntity).prefix_with("IGNORE").values(values)
            result = self._session.execute(stmt)
            self._session.flush()
            total_inserted += result.rowcount
        return total_inserted

    def find_by_video_id(self, video_id: int) -> OddTag | None:
        stmt = select(OddTagEntity).where(OddTagEntity.video_id == video_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        return OddTagMapper.to_domain(entity) if entity else None

    def find_all_video_ids_by_task(self, task_id: str) -> set[int]:
        stmt = select(OddTagEntity.video_id).where(OddTagEntity.task_id == task_id)
        result = self._session.execute(stmt)
        return {row[0] for row in result}


class SqlLabelRepository(LabelRepository):
    def __init__(self, session: Session, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._session = session
        self._chunk_size = chunk_size

    def save_all(self, labels: list[Label]) -> int:
        total_inserted = 0
        for chunk in _chunked(labels, self._chunk_size):
            values = [LabelMapper.to_dict(lb) for lb in chunk]
            stmt = insert(LabelEntity).prefix_with("IGNORE").values(values)
            result = self._session.execute(stmt)
            self._session.flush()
            total_inserted += result.rowcount
        return total_inserted

    def find_all_by_video_id(self, video_id: int) -> list[Label]:
        stmt = select(LabelEntity).where(LabelEntity.video_id == video_id)
        entities = self._session.execute(stmt).scalars().all()
        return [LabelMapper.to_domain(e) for e in entities]

    def find_all_video_ids_by_task(self, task_id: str) -> set[int]:
        stmt = select(LabelEntity.video_id).where(LabelEntity.task_id == task_id).distinct()
        result = self._session.execute(stmt)
        return {row[0] for row in result}


class SqlRejectionRepository(RejectionRepository):
    def __init__(self, session: Session, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        self._session = session
        self._chunk_size = chunk_size

    def save_all(self, rejections: list[Rejection]) -> None:
        for chunk in _chunked(rejections, self._chunk_size):
            entities = [RejectionMapper.to_entity(r) for r in chunk]
            self._session.add_all(entities)
            self._session.flush()

    def search(self, criteria: RejectionCriteria) -> tuple[list[Rejection], int]:
        builder = RejectionQueryBuilder(criteria)

        total = self._session.execute(builder.build_count_query()).scalar() or 0
        entities = self._session.execute(builder.build_query()).scalars().all()

        return [RejectionMapper.to_domain(e) for e in entities], total


class SqlDataDataSearchRepository(DataSearchRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, criteria: DataSearchCriteria) -> tuple[list[SearchResult], int]:
        builder = DataSearchQueryBuilder(criteria)

        total = self._session.execute(builder.build_count_query()).scalar() or 0
        selection_entities = self._session.execute(builder.build_query()).scalars().all()

        if not selection_entities:
            return [], total

        video_ids = [e.id for e in selection_entities]

        odd_entities = (
            self._session.execute(select(OddTagEntity).where(OddTagEntity.video_id.in_(video_ids))).scalars().all()
        )
        odd_map: dict[int, OddTagEntity] = {e.video_id: e for e in odd_entities}

        label_entities = (
            self._session.execute(select(LabelEntity).where(LabelEntity.video_id.in_(video_ids))).scalars().all()
        )
        label_map: dict[int, list[LabelEntity]] = {}
        for e in label_entities:
            label_map.setdefault(e.video_id, []).append(e)

        results: list[SearchResult] = []
        for sel_entity in selection_entities:
            odd_entity = odd_map.get(sel_entity.id)
            label_list = label_map.get(sel_entity.id, [])

            results.append(
                SearchResult(
                    selection=SelectionMapper.to_domain(sel_entity),
                    odd_tag=OddTagMapper.to_domain(odd_entity) if odd_entity else None,
                    labels=[LabelMapper.to_domain(e) for e in label_list],
                )
            )

        return results, total
