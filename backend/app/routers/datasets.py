"""Import organizer CSV bytes without writing arbitrary server filesystem paths."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.data.organizer import DatasetValidationError
from app.services.dataset_import import MAX_UPLOAD_BYTES, store_upload
from app.v1_contracts import DatasetImported

router = APIRouter(prefix='/datasets', tags=['Datasets'])


@router.post('', status_code=201, response_model=DatasetImported, openapi_extra={
    'requestBody': {'required': True, 'content': {'text/csv': {'schema': {'type': 'string', 'format': 'binary'}}}},
})
async def import_dataset(request: Request, db: Session = Depends(get_db)):
    if request.headers.get('content-type', '').split(';')[0].lower() != 'text/csv':
        raise HTTPException(415, detail={'error_code': 'UNSUPPORTED_MEDIA_TYPE', 'message': 'Send UTF-8 CSV as text/csv.', 'details': {}})
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, detail={'error_code': 'FILE_TOO_LARGE', 'message': 'CSV files must be 2 MB or smaller.', 'details': {}})
        raw.extend(chunk)
    try:
        stored = store_upload(db, bytes(raw))
        result = {
            'dataset_id': stored.dataset_id, 'row_count': stored.row_count,
            'content_hash': stored.content_hash, 'native_interval_seconds': stored.native_interval_seconds,
            'first_timestamp': str(stored.first_timestamp), 'last_timestamp': str(stored.last_timestamp),
            'timezone_status': stored.timezone_status, 'validation_status': stored.validation_status,
            'validation': stored.validation_json,
        }
        db.commit()
        return result
    except DatasetValidationError as exc:
        db.rollback()
        issue = exc.issues[0]
        message = f'Row {issue.row}: {issue.message}' if issue.row else issue.message
        raise HTTPException(422, detail={'error_code': 'INVALID_DATASET', 'message': message,
                                       'details': [item.model_dump() for item in exc.issues[:50]]}) from exc
    except Exception:
        db.rollback()
        raise
