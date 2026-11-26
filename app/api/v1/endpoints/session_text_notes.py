"""Text notes on a monitoring session (MongoDB only)."""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, require_staff
from app.models.base import utcnow
from app.models.session_text_note import SessionTextNote
from app.models.user import User
from app.schemas.session_text_note import (
    SessionTextNoteCreate,
    SessionTextNoteOut,
    SessionTextNoteUpdate,
)
from app.services.clinical_delete import delete_text_note_record
from app.services.monitoring_session import require_session

router = APIRouter()


@router.post(
    "/{session_id}/text-notes",
    response_model=SessionTextNoteOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_text_note(
    session_id: PydanticObjectId,
    payload: SessionTextNoteCreate,
    current_user: User = Depends(require_staff),
) -> SessionTextNote:
    await require_session(
        session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
    )
    note = SessionTextNote(
        session_id=session_id,
        patient_id=payload.patient_id,
        node_id=payload.node_id,
        body=payload.body,
        recorded_at=payload.recorded_at or utcnow(),
        author_id=current_user.id,
    )
    await note.insert()
    return note


@router.get(
    "/{session_id}/text-notes",
    response_model=list[SessionTextNoteOut],
)
async def list_text_notes(
    session_id: PydanticObjectId,
    skip: int = 0,
    limit: int = 100,
    _: User = Depends(get_current_user),
) -> list[SessionTextNote]:
    await require_session(session_id)
    return (
        await SessionTextNote.find(SessionTextNote.session_id == session_id)
        .sort(-SessionTextNote.recorded_at)
        .skip(skip)
        .limit(limit)
        .to_list()
    )


@router.get(
    "/{session_id}/text-notes/{note_id}",
    response_model=SessionTextNoteOut,
)
async def get_text_note(
    session_id: PydanticObjectId,
    note_id: PydanticObjectId,
    _: User = Depends(get_current_user),
) -> SessionTextNote:
    await require_session(session_id)
    note = await SessionTextNote.get(note_id)
    if note is None or note.session_id != session_id:
        raise HTTPException(status_code=404, detail="Text note not found")
    return note


@router.patch(
    "/{session_id}/text-notes/{note_id}",
    response_model=SessionTextNoteOut,
)
async def update_text_note(
    session_id: PydanticObjectId,
    note_id: PydanticObjectId,
    payload: SessionTextNoteUpdate,
    _: User = Depends(require_staff),
) -> SessionTextNote:
    await require_session(session_id)
    note = await SessionTextNote.get(note_id)
    if note is None or note.session_id != session_id:
        raise HTTPException(status_code=404, detail="Text note not found")
    note.body = payload.body
    note.updated_at = utcnow()
    await note.save()
    return note


@router.delete(
    "/{session_id}/text-notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_text_note(
    session_id: PydanticObjectId,
    note_id: PydanticObjectId,
    _: User = Depends(require_staff),
) -> Response:
    await require_session(session_id)
    note = await SessionTextNote.get(note_id)
    if note is None or note.session_id != session_id:
        raise HTTPException(status_code=404, detail="Text note not found")
    await delete_text_note_record(note)
    return Response(status_code=status.HTTP_204_NO_CONTENT)