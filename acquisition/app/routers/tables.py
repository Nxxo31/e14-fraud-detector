"""E14 Acquisition — Tables API router."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from ..database import get_db
from ..models import Table
from ..schemas import TableOut, TableDetail, TableList

router = APIRouter(prefix="/tables", tags=["tables"])


@router.get("", response_model=TableList)
def list_tables(
    dep_code: Optional[str] = Query(None, min_length=1, max_length=2),
    muni_code: Optional[str] = Query(None, min_length=1, max_length=3),
    zona_code: Optional[str] = Query(None, min_length=1, max_length=3),
    puesto_code: Optional[str] = Query(None, min_length=1, max_length=2),
    mesa_code: Optional[str] = Query(None, min_length=1, max_length=3),
    pdf_status: Optional[str] = Query(None, regex="^(pending|downloading|cached|missing|error)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List E14 tables with optional filtering by location codes."""
    query = db.query(Table)

    if dep_code:
        query = query.filter(Table.dep_code == dep_code.zfill(2))
    if muni_code:
        query = query.filter(Table.muni_code == muni_code.zfill(3))
    if zona_code:
        query = query.filter(Table.zona_code == zona_code.zfill(3))
    if puesto_code:
        query = query.filter(Table.puesto_code == puesto_code.zfill(2))
    if mesa_code:
        query = query.filter(Table.mesa_code == mesa_code.zfill(3))
    if pdf_status:
        query = query.filter(Table.pdf_status == pdf_status)

    total = query.count()
    items = query.order_by(Table.dep_code, Table.muni_code, Table.mesa_code)\
                  .offset((page - 1) * per_page)\
                  .limit(per_page)\
                  .all()

    return TableList(
        total=total,
        page=page,
        per_page=per_page,
        tables=[TableOut.model_validate(t) for t in items],
    )


@router.get("/search", response_model=TableList)
def search_tables(
    q: str = Query(..., min_length=2, description="Search term (dep_name, muni_name, zona_name, puesto_name)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Search tables by location name."""
    pattern = f"%{q}%"
    query = db.query(Table).filter(
        or_(
            Table.dep_name.ilike(pattern),
            Table.muni_name.ilike(pattern),
            Table.zona_name.ilike(pattern),
            Table.puesto_name.ilike(pattern),
        )
    )

    total = query.count()
    items = query.order_by(Table.dep_code, Table.muni_code, Table.mesa_code)\
                  .offset((page - 1) * per_page)\
                  .limit(per_page)\
                  .all()

    return TableList(
        total=total,
        page=page,
        per_page=per_page,
        tables=[TableOut.model_validate(t) for t in items],
    )


@router.get("/{table_id}", response_model=TableDetail)
def get_table(table_id: int, db: Session = Depends(get_db)):
    """Get a single table by ID with full metadata."""
    table = db.query(Table).filter(Table.id == table_id).first()
    if not table:
        raise HTTPException(status_code=404, detail="Table not found")
    return TableDetail.model_validate(table)


@router.get("/{table_id}/metadata", response_model=TableDetail)
def get_table_metadata(table_id: int, db: Session = Depends(get_db)):
    """Get table metadata only (no PDF content)."""
    return get_table(table_id, db)