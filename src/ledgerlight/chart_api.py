"""User-invoked preview/save/edit/history; agent reads previews through CLI."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from ledgerlight import charts

router = APIRouter()


class ChartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    sql: str
    type: str
    html: str = ""


@router.post("/api/charts/preview")
def preview(body: ChartInput):
    return charts.preview(**body.model_dump())


@router.post("/api/charts/save")
def save(body: ChartInput):
    return charts.add(**body.model_dump())


@router.post("/api/charts/{id}/edit")
def edit(id: int, body: ChartInput):
    return charts.add(**body.model_dump(), chart_id=id)


@router.get("/api/charts/{id}/history")
def history(id: int):
    return charts.history(id)
