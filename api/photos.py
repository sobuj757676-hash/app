"""Photo evidence stored in Vercel Blob.

If BLOB_READ_WRITE_TOKEN is not configured, the upload endpoint returns 503
and everything else keeps working. _blob_put is a thin wrapper so tests can
monkeypatch storage without touching the network.
"""
import io
import os
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from PIL import Image
from models import Record, PHOTO_ENTITY_TYPES
from routes import database, get, uid, now, save, log, is_worker
from auth import get_current_user, require_roles, OPS_ROLES

router = APIRouter()

ALLOWED_MIME = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
MAX_BYTES = 10 * 1024 * 1024
THUMB_EDGE = 512


def _blob_token() -> str:
    return os.environ.get('BLOB_READ_WRITE_TOKEN', '')


def _blob_put(pathname: str, data: bytes, content_type: str) -> dict:
    """Upload bytes to Vercel Blob. Monkeypatch this in tests."""
    from vercel_blob import put
    return put(pathname, data, {'access': 'public', 'content_type': content_type})


def _thumbnail(data: bytes) -> bytes:
    img = Image.open(io.BytesIO(data))
    img.thumbnail((THUMB_EDGE, THUMB_EDGE))
    if img.mode in ('RGBA', 'LA', 'P'):
        img = img.convert('RGB')
    buf = io.BytesIO()
    img.save(buf, 'JPEG', quality=82)
    return buf.getvalue()


async def _check_entity(entity_type: str, entity_id: str, user: dict, write: bool):
    """Validate the linked entity exists and the caller may touch it.
    Returns (project_id, label). Raises 400/403/404."""
    if entity_type not in PHOTO_ENTITY_TYPES:
        raise HTTPException(400, 'Invalid entity type')
    role = user.get('role')
    if entity_type == 'defect':
        defect = await get('defects', entity_id)
        if is_worker(user):
            mine = defect.get('assigned_to') == user['id'] \
                or defect.get('reported_by', {}).get('id') == user['id']
            if not mine:
                raise HTTPException(403, 'You do not have permission for this action')
        elif write and role == 'viewer':
            raise HTTPException(403, 'You do not have permission for this action')
        return defect['project_id'], defect['title']
    if entity_type == 'task':
        task = await get('tasks', entity_id)
        if is_worker(user) and task.get('assigned_to') != user['id']:
            raise HTTPException(403, 'You do not have permission for this action')
        if write and role == 'viewer':
            raise HTTPException(403, 'You do not have permission for this action')
        return task['project_id'], task['title']
    # inspection / test / unit: reads are open to all roles; writes are OPS only.
    if write and role not in OPS_ROLES:
        raise HTTPException(403, 'You do not have permission for this action')
    if entity_type == 'inspection':
        doc = await get('inspections', entity_id)
        label = f"RTO · {doc.get('unit_label', '')}"
    elif entity_type == 'test':
        doc = await get('tests', entity_id)
        label = f"Test · {doc.get('point_name', '')}"
    else:
        doc = await get('units', entity_id)
        label = f"Blk {doc.get('block')} · #{doc.get('level'):02}-{doc.get('number')}"
    return doc['project_id'], label


@router.post('/photos/upload', response_model=Record)
async def upload_photo(file: UploadFile = File(...),
                       entity_type: str = Form(...),
                       entity_id: str = Form(...),
                       caption: str = Form(''),
                       user: dict = Depends(require_roles(*OPS_ROLES, 'worker'))):
    project_id, label = await _check_entity(entity_type, entity_id, user, write=True)
    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(400, 'Only JPEG, PNG or WebP photos are accepted')
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(400, 'Photo must be 10 MB or smaller')
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:
        raise HTTPException(400, 'File is not a valid image')
    if not _blob_token():
        raise HTTPException(503, 'Photo storage is not configured yet — ask your admin to add the storage token.')
    photo_id = uid()
    ext = ALLOWED_MIME[file.content_type]
    base = f'photos/{project_id}/{entity_type}/{entity_id}/{photo_id}'
    try:
        original = _blob_put(f'{base}.{ext}', data, file.content_type)
        thumb = _blob_put(f'{base}_thumb.jpg', _thumbnail(data), 'image/jpeg')
    except Exception as e:
        raise HTTPException(
            502, f'Photo storage upload failed ({type(e).__name__}: {e}). '
                 'Ask your admin to check the BLOB_READ_WRITE_TOKEN value.') from e
    doc = {
        'id': photo_id, 'project_id': project_id,
        'entity_type': entity_type, 'entity_id': entity_id,
        'url': original['url'], 'thumb_url': thumb['url'],
        'mime': file.content_type, 'size': len(data),
        'caption': (caption or '').strip()[:200],
        'uploaded_by': {'id': user['id'], 'name': user['name']},
        'created_at': now(), 'deleted': False,
    }
    if entity_type == 'defect':
        await database().defects.update_one({'id': entity_id}, {'$push': {'photos': photo_id}})
    elif entity_type == 'task':
        await database().tasks.update_one({'id': entity_id}, {'$push': {'photos': photo_id}})
    await log(project_id, 'photo', f'Photo added · {label}', user)
    return await save('photos', doc)


@router.get('/photos', response_model=list[Record])
async def list_photos(entity_type: str, entity_id: str,
                      user: dict = Depends(get_current_user)):
    await _check_entity(entity_type, entity_id, user, write=False)
    return await database().photos.find(
        {'entity_type': entity_type, 'entity_id': entity_id, 'deleted': {'$ne': True}},
        {'_id': 0}).sort('created_at', -1).to_list(500)


@router.delete('/photos/{id}', response_model=Record)
async def delete_photo(id: str, user: dict = Depends(require_roles('admin', 'manager'))):
    photo = await get('photos', id)
    await database().photos.update_one({'id': id}, {'$set': {'deleted': True}})
    await log(photo['project_id'], 'photo',
              f'Photo removed · {photo.get("caption") or id[:8]}', user)
    return await get('photos', id)
