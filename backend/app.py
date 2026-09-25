import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError, WatchError


REDIS_URL = os.getenv("REDIS_URL", "redis://taskboard-redis:6379/0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = Redis.from_url(REDIS_URL, decode_responses=True)
    yield
    await app.state.redis.aclose()


app = FastAPI(title="Taskboard API", lifespan=lifespan)


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class TaskUpdate(BaseModel):
    status: Literal["todo", "doing", "done"]


def task_key(task_id: int) -> str:
    return f"taskboard:task:{task_id}"


@app.get("/health/live")
async def live():
    return {"status": "alive"}


@app.get("/health/ready")
async def ready():
    try:
        await app.state.redis.ping()
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.get("/api/tasks")
async def list_tasks():
    try:
        ids = await app.state.redis.zrevrange("taskboard:tasks", 0, -1)
        if not ids:
            return []
        values = await app.state.redis.mget([task_key(int(i)) for i in ids])
        return [json.loads(value) for value in values if value is not None]
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")


@app.post("/api/tasks", status_code=201)
async def create_task(body: TaskCreate):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Title cannot be blank")
    try:
        task_id = await app.state.redis.incr("taskboard:next-id")
        task = {"id": task_id, "title": title, "status": "todo",
                "createdAt": datetime.now(timezone.utc).isoformat()}
        async with app.state.redis.pipeline(transaction=True) as pipe:
            pipe.set(task_key(task_id), json.dumps(task))
            pipe.zadd("taskboard:tasks", {str(task_id): task_id})
            await pipe.execute()
        return task
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, body: TaskUpdate):
    try:
        async with app.state.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(task_key(task_id))
                    value = await pipe.get(task_key(task_id))
                    if value is None:
                        raise HTTPException(status_code=404, detail="Task not found")
                    task = json.loads(value)
                    task["status"] = body.status
                    pipe.multi()
                    pipe.set(task_key(task_id), json.dumps(task))
                    await pipe.execute()
                    return task
                except WatchError:
                    continue
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")


@app.delete("/api/tasks/{task_id}", status_code=204)
async def delete_task(task_id: int):
    try:
        async with app.state.redis.pipeline(transaction=True) as pipe:
            pipe.delete(task_key(task_id))
            pipe.zrem("taskboard:tasks", str(task_id))
            result = await pipe.execute()
        if result[0] == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        return Response(status_code=204)
    except RedisError:
        raise HTTPException(status_code=503, detail="Redis unavailable")
