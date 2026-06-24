"""Project endpoints: list/create/delete, generate-script, compile, video."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Project, User
from ..schemas import (
    ProjectOut,
    ScriptGenerateRequest,
    ScriptResponse,
    ScriptUpdate,
)
from ..services import pipeline
from ..services.compose import CompositionError
from ..services.gemini import ScriptGenerationError, generate_script
from ..services.transcribe import TranscriptionError
from ..services.tts import TTSError

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _get_owned_project(project_id: int, user: User, db: Session) -> Project:
    """Fetch a project scoped to the owner, or 404. Enforces tenancy."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == user.id)
        .first()
    )
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found."
        )
    return project


@router.get("", response_model=list[ProjectOut])
def list_projects(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.timestamp.desc())
        .all()
    )


@router.post("/generate-script", response_model=ScriptResponse)
def generate_script_endpoint(
    payload: ScriptGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create (or back) a project and fill in the Gemini-generated script."""
    try:
        script = generate_script(payload.prompt)
    except ScriptGenerationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    project = Project(
        user_id=current_user.id,
        prompt=payload.prompt,
        generated_script=script,
        status="scripted",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return ScriptResponse(project_id=project.id, generated_script=script)


@router.put("/{project_id}/script", response_model=ProjectOut)
def update_script(
    project_id: int,
    payload: ScriptUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Persist user edits to the script before compiling."""
    project = _get_owned_project(project_id, current_user, db)
    project.generated_script = payload.generated_script
    project.status = "scripted"
    db.commit()
    db.refresh(project)
    return project


@router.post("/{project_id}/compile", response_model=ProjectOut)
def compile_video(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run the synchronous render chain and record the result."""
    project = _get_owned_project(project_id, current_user, db)
    if not project.generated_script:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Generate or provide a script before compiling.",
        )

    project.status = "rendering"
    project.error = None
    db.commit()

    try:
        output = pipeline.render_reel(project.id, project.generated_script)
    except (TTSError, TranscriptionError, CompositionError) as exc:
        project.status = "failed"
        project.error = str(exc)
        db.commit()
        db.refresh(project)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    project.video_path = str(output)
    project.status = "done"
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}/video")
def get_video(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Stream a finished reel — only to its owner."""
    project = _get_owned_project(project_id, current_user, db)
    if not project.video_path or not Path(project.video_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No rendered video yet."
        )
    return FileResponse(
        project.video_path,
        media_type="video/mp4",
        filename=f"reel_{project.id}.mp4",
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = _get_owned_project(project_id, current_user, db)
    db.delete(project)
    db.commit()
