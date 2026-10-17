from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TransactionModel
from app.schemas import Transaction

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

@router.get("/recent", response_model=List[Transaction])
def get_recent_transactions(limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    return db.query(TransactionModel).order_by(TransactionModel.timestamp.desc()).limit(limit).all()
