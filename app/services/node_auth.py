"""Authenticate a physical NILO node (MAC + access password)."""

import secrets

from fastapi import HTTPException, status

from app.models.fields import EncStr
from app.models.node import Node


async def authenticate_node(mac_address: str, access_password: str) -> Node:
    node = await Node.find_one(Node.mac_address == mac_address)
    if node is None or node.access_password is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node credentials",
        )
    stored = str(node.access_password)
    if not secrets.compare_digest(stored, access_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid node credentials",
        )
    return node


def apply_access_password(node: Node, plain: str | None) -> None:
    if plain is None:
        return
    node.access_password = EncStr(plain)
