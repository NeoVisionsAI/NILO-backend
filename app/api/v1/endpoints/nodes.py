"""Node management endpoints.

A node is a physical device other monitoring devices connect to. Reading is
available to any authenticated user; creating/updating/deleting requires staff
(clinician or root).
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, require_staff
from app.models.base import utcnow
from app.models.node import Node
from app.models.user import User
from app.schemas.node import NodeCreate, NodeOut, NodeUpdate

router = APIRouter()


@router.post("", response_model=NodeOut, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: NodeCreate, _: User = Depends(require_staff)
) -> Node:
    existing = await Node.find_one(Node.mac_address == payload.mac_address)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A node with this MAC address already exists",
        )
    node = Node(**payload.model_dump())
    await node.insert()
    return node


@router.get("", response_model=list[NodeOut])
async def list_nodes(
    skip: int = 0,
    limit: int = 100,
    _: User = Depends(get_current_user),
) -> list[Node]:
    return await Node.find_all().skip(skip).limit(limit).to_list()


@router.get("/{node_id}", response_model=NodeOut)
async def get_node(
    node_id: PydanticObjectId, _: User = Depends(get_current_user)
) -> Node:
    node = await Node.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.patch("/{node_id}", response_model=NodeOut)
async def update_node(
    node_id: PydanticObjectId,
    payload: NodeUpdate,
    _: User = Depends(require_staff),
) -> Node:
    node = await Node.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    data = payload.model_dump(exclude_unset=True)

    new_mac = data.get("mac_address")
    if new_mac is not None and new_mac != node.mac_address:
        other = await Node.find_one(Node.mac_address == new_mac)
        if other is not None and other.id != node.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A node with this MAC address already exists",
            )

    for key, value in data.items():
        setattr(node, key, value)
    node.updated_at = utcnow()
    await node.save()
    return node


@router.delete("/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: PydanticObjectId, _: User = Depends(require_staff)
) -> None:
    node = await Node.get(node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")
    await node.delete()
