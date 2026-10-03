"""Auth endpoints: login, me, change-password, user management."""
import secrets
from fastapi import APIRouter, HTTPException, Depends
from pymongo.errors import DuplicateKeyError
from models import LoginIn, ChangePasswordIn, UserCreateIn, UserUpdateIn
from routes import database, get, uid, now
from auth import (get_current_user, require_roles, hash_password, verify_password,
                  create_token, public_user, ROLES)

router = APIRouter(prefix="/api/auth")


def _temp_password() -> str:
    return secrets.token_urlsafe(9)


@router.post('/login')
async def login(data: LoginIn):
    raw = data.identifier.strip()
    lookup = {'email': raw.lower()} if '@' in raw else {'phone': raw}
    user = await database().users.find_one({**lookup, 'active': True}, {'_id': 0})
    if not user or not verify_password(data.password, user.get('password_hash', '')):
        raise HTTPException(401, 'Invalid credentials')
    await database().users.update_one({'id': user['id']}, {'$set': {'last_login_at': now()}})
    user['last_login_at'] = now()
    return {'token': create_token(user), 'user': public_user(user)}


@router.get('/me')
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@router.post('/change-password')
async def change_password(data: ChangePasswordIn, user: dict = Depends(get_current_user)):
    full = await database().users.find_one({'id': user['id']})
    if not full or not verify_password(data.current_password, full.get('password_hash', '')):
        raise HTTPException(400, 'Current password is incorrect')
    await database().users.update_one(
        {'id': user['id']},
        {'$set': {'password_hash': hash_password(data.new_password), 'must_change_password': False}})
    return {'ok': True}


@router.post('/users')
async def create_user(data: UserCreateIn, user: dict = Depends(require_roles('admin', 'manager'))):
    if user['role'] == 'manager' and data.role != 'worker':
        raise HTTPException(403, 'Managers can only create worker accounts')
    if data.role not in ROLES:
        raise HTTPException(400, 'Invalid role')
    email = (data.email or '').strip().lower()
    phone = (data.phone or '').strip()
    if not email and not phone:
        raise HTTPException(400, 'Email or phone is required')
    if email and await database().users.find_one({'email': email}):
        raise HTTPException(409, 'Email already registered')
    if phone and await database().users.find_one({'phone': phone}):
        raise HTTPException(409, 'Phone already registered')
    worker_id = data.worker_id if data.role == 'worker' else None
    if worker_id:
        await get('workers', worker_id)  # validate the link
    temp_password = None
    if data.password:
        password_hash, must_change = hash_password(data.password), False
    else:
        temp_password = _temp_password()
        password_hash, must_change = hash_password(temp_password), True
    doc = {'id': uid(), 'name': data.name.strip(), 'password_hash': password_hash, 'role': data.role,
           'worker_id': worker_id, 'active': True, 'must_change_password': must_change,
           'created_at': now(), 'last_login_at': None}
    # Omit empty identifiers entirely: sparse unique indexes treat explicit
    # null as a value, so storing None would collide on the second such user.
    if email: doc['email'] = email
    if phone: doc['phone'] = phone
    try:
        await database().users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, 'Email or phone already registered')
    response = {'user': public_user(doc)}
    if temp_password:
        response['temp_password'] = temp_password
    return response


@router.get('/users')
async def list_users(user: dict = Depends(require_roles('admin', 'manager'))):
    filt = {'role': 'worker'} if user['role'] == 'manager' else {}
    return await database().users.find(filt, {'_id': 0, 'password_hash': 0}).sort('created_at', -1).to_list(1000)


@router.patch('/users/{id}')
async def update_user(id: str, data: UserUpdateIn, user: dict = Depends(require_roles('admin', 'manager'))):
    target = await get('users', id)
    if user['role'] == 'manager':
        if target['role'] != 'worker':
            raise HTTPException(403, 'Managers can only manage worker accounts')
        if data.name is not None or data.role is not None:
            raise HTTPException(403, 'Managers can only activate or deactivate workers')
        patch = {} if data.active is None else {'active': data.active}
    else:
        patch = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if 'role' in patch and patch['role'] not in ROLES:
            raise HTTPException(400, 'Invalid role')
    if id == user['id'] and patch.get('active') is False:
        raise HTTPException(400, 'You cannot deactivate your own account')
    if patch:
        await database().users.update_one({'id': id}, {'$set': patch})
    return public_user(await get('users', id))


@router.post('/users/{id}/reset-password')
async def reset_password(id: str, user: dict = Depends(require_roles('admin', 'manager'))):
    target = await get('users', id)
    if user['role'] == 'manager' and target['role'] != 'worker':
        raise HTTPException(403, 'Managers can only reset worker passwords')
    temp = _temp_password()
    await database().users.update_one(
        {'id': id},
        {'$set': {'password_hash': hash_password(temp), 'must_change_password': True}})
    return {'temp_password': temp}
