from itertools import islice

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.adapter.outbound.entities import (
    LabelEntity,
    OddTagEntity,
    RejectionEntity,
    SelectionEntity,
)
from app.adapter.outbound.mappers import (
    LabelMapper,
    OddTagMapper,
    RejectionMapper,
    SelectionMapper,
)
from app.adapter.outbound.query_builder import RejectionQueryBuilder, SearchQueryBuilder
from app.domain.models import Label, OddTag, Rejection, RejectionCriteria, SearchCriteria, Selection
from app.domain.ports import (
    LabelRepository,
    OddTagRepository,
    RejectionRepository,
    SearchRepository,
    SearchResult,
    SelectionRepository,
)

CHUNK_SIZE = 1000


def _chunked(iterable: list, size: int):
    """리스트를 size 단위로 분할하여 yield한다."""
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk


class SqlSelectionRepository(SelectionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_all(self, selections: list[Selection]) -> None:
        for chunk in _chunked(selections, CHUNK_SIZE):
            entities = [SelectionMapper.to_entity(s) for s in chunk]
            self._session.add_all(entities)
            self._session.flush()

    def find_by_id(self, selection_id: int) -> Selection | None:
        entity = self._session.get(SelectionEntity, selection_id)
        return SelectionMapper.to_domain(entity) if entity else None

    def find_all_ids(self) -> set[int]:
        stmt = select(SelectionEntity.id)
        result = self._session.execute(stmt)
        return {row[0] for row in result}

    def delete_all(self) -> None:
        self._session.execute(delete(SelectionEntity))
        self._session.flush()


class SqlOddTagRepository(OddTagRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_all(self, odd_tags: list[OddTag]) -> None:
        for chunk in _chunked(odd_tags, CHUNK_SIZE):
            entities = [OddTagMapper.to_entity(o) for o in chunk]
            self._session.add_all(entities)
            self._session.flush()

    def find_by_video_id(self, video_id: int) -> OddTag | None:
        stmt = select(OddTagEntity).where(OddTagEntity.video_id == video_id)
        entity = self._session.execute(stmt).scalar_one_or_none()
        return OddTagMapper.to_domain(entity) if entity else None

    def find_all_video_ids(self) -> set[int]:
        stmt = select(OddTagEntity.video_id)
        result = self._session.execute(stmt)
        return {row[0] for row in result}

    def delete_all(self) -> None:
        self._session.execute(delete(OddTagEntity))
        self._session.flush()


class SqlLabelRepository(LabelRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_all(self, labels: list[Label]) -> None:
        for chunk in _chunked(labels, CHUNK_SIZE):
            entities = [LabelMapper.to_entity(lb) for lb in chunk]
            self._session.add_all(entities)
            self._session.flush()

    def find_all_by_video_id(self, video_id: int) -> list[Label]:
        stmt = select(LabelEntity).where(LabelEntity.video_id == video_id)
        entities = self._session.execute(stmt).scalars().all()
        return [LabelMapper.to_domain(e) for e in entities]

    def find_all_video_ids(self) -> set[int]:
        stmt = select(LabelEntity.video_id).distinct()
        result = self._session.execute(stmt)
        return {row[0] for row in result}

    def delete_all(self) -> None:
        self._session.execute(delete(LabelEntity))
        self._session.flush()


class SqlRejectionRepository(RejectionRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_all(self, rejections: list[Rejection]) -> None:
        for chunk in _chunked(rejections, CHUNK_SIZE):
            entities = [RejectionMapper.to_entity(r) for r in chunk]
            self._session.add_all(entities)
            self._session.flush()

    def search(self, criteria: RejectionCriteria) -> tuple[list[Rejection], int]:
        builder = RejectionQueryBuilder(criteria)

        total = self._session.execute(builder.build_count_query()).scalar() or 0
        entities = self._session.execute(builder.build_query()).scalars().all()

        return [RejectionMapper.to_domain(e) for e in entities], total

    def delete_all(self) -> None:
        self._session.execute(delete(RejectionEntity))
        self._session.flush()


class SqlSearchRepository(SearchRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def search(self, criteria: SearchCriteria) -> tuple[list[SearchResult], int]:
        builder = SearchQueryBuilder(criteria)

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
