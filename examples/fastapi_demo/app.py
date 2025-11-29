"""Simple FastAPI app for testing."""

import asyncio

from fastapi import FastAPI

app = FastAPI()

USERS_DB = {
    1: {"id": 1, "name": "Alice", "email": "alice@example.com"},
    2: {"id": 2, "name": "Bob", "email": "bob@example.com"},
    3: {"id": 3, "name": "Charlie", "email": "charlie@example.com"},
}

PRODUCTS_DB = {
    1: {"id": 1, "name": "Laptop", "price": 999.99},
    2: {"id": 2, "name": "Phone", "price": 599.99},
    3: {"id": 3, "name": "Tablet", "price": 399.99},
}


@app.get("/users/{user_id}")
async def get_user(user_id: int) -> dict:
    await asyncio.sleep(0.1)
    if user_id not in USERS_DB:
        return {"error": "User not found"}
    return USERS_DB[user_id]


@app.get("/products/{product_id}")
async def get_product(product_id: int) -> dict:
    await asyncio.sleep(0.1)
    if product_id not in PRODUCTS_DB:
        return {"error": "Product not found"}
    return PRODUCTS_DB[product_id]


@app.get("/slow")
async def slow_endpoint() -> dict:
    await asyncio.sleep(0.5)
    return {"status": "done"}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}