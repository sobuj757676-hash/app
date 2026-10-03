"""In-app notifications (event-driven). No email/push in Phase 2."""
from fastapi import APIRouter, HTTPException, Depends, Query
from routes import database, uid, now
from auth import get_current_user

router = APIRouter()

NOTIFICATION_KINDS = ('defect_assigned', 'defect_verified', 'rto_decided',
                      'task_assigned', 'task_completed')


async def notify(user_id: str | None, kind: str, title: str, body: str, link: dict | None = None):
    """Persist a notification for one user. Safe to call from any endpoint."""
    if not user_id or kind not in NOTIFICATION_KINDS:
        return
    await database().notifications.insert_one({
        'id': uid(), 'user_id': user_id, 'kind': kind,
        'title': title[:150], 'body': body[:500], 'link': link or {},
        'read': False, 'created_at': now()})


@router.get('/notifications')
async def list_notifications(user: dict = Depends(get_current_user),
                             unread_only: bool = Query(False)):
    filt = {'user_id': user['id']}
    if unread_only:
        filt['read'] = False
    return await database().notifications.find(filt, {'_id': 0}).sort('created_at', -1).to_list(200)


@router.get('/notifications/unread-count')
async def unread_count(user: dict = Depends(get_current_user)):
    count = await database().notifications.count_documents({'user_id': user['id'], 'read': False})
    return {'count': count}


@router.post('/notifications/{id}/read')
async def mark_read(id: str, user: dict = Depends(get_current_user)):
    note = await database().notifications.find_one({'id': id, 'user_id': user['id']})
    if not note:
        raise HTTPException(404, 'Notification not found')
    await database().notifications.update_one({'id': id}, {'$set': {'read': True}})
    return {'ok': True}
