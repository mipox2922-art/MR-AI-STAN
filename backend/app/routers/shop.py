from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..connectors.shop import (
    ShopConnectorError,
    shop_connection_status,
    shop_snapshot,
    shop_configuration_status,
)
from ..dependencies import get_current_user

router = APIRouter(prefix="/shop", tags=["343SHOP"])


@router.get("/status")
async def shop_status(current_user=Depends(get_current_user)):
    return await shop_connection_status()


@router.get("/overview")
async def shop_overview(current_user=Depends(get_current_user)):
    try:
        result = await shop_snapshot(product_limit=1, order_limit=10)
        return {
            "status": result["status"],
            "store": result["store"],
            "generated_at": result["generated_at"],
            "overview": result["overview"],
            "limitations": result["limitations"],
        }
    except ShopConnectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/products")
async def shop_products(
    limit: int = Query(default=40, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        result = await shop_snapshot(product_limit=limit, order_limit=1)
        return {"status": result["status"], "products": result["products"], "returned": result["products_returned"]}
    except ShopConnectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/orders")
async def shop_orders(
    limit: int = Query(default=20, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    try:
        result = await shop_snapshot(product_limit=1, order_limit=limit)
        return {"status": result["status"], "orders": result["orders"], "returned": result["orders_returned"]}
    except ShopConnectorError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
