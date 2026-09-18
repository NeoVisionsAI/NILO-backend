"""Search helpers for root admin views.

PII fields (name, email, address…) are encrypted at rest; substring search runs
in memory after documents are loaded/decrypted. Exact email lookup uses the
blind index when only ``email`` is provided.
"""

from __future__ import annotations

from app.core import crypto
from app.models.enums import UserRole
from app.models.node import Node
from app.models.user import User


def _contains(haystack: str | None, needle: str) -> bool:
    if not haystack or not needle:
        return False
    return needle.lower() in haystack.lower()


def user_geography_text(user: User) -> str:
    parts = [user.address, user.zip, user.country]
    if user.type_user == UserRole.CLINICIAN and user.clinician_profile:
        parts.extend(
            [
                user.clinician_profile.institution,
                user.clinician_profile.location,
            ]
        )
    if user.type_user == UserRole.PATIENT and user.patient_profile:
        parts.extend([user.patient_profile.room, user.patient_profile.bed])
    return " ".join(p for p in parts if p)


def user_matches_search(
    user: User,
    *,
    q: str | None = None,
    name: str | None = None,
    lastname: str | None = None,
    email: str | None = None,
    country: str | None = None,
    zip_code: str | None = None,
) -> bool:
    if name and not _contains(user.name, name):
        return False
    if lastname and not _contains(user.lastname, lastname):
        return False
    if email and not _contains(user.email, email):
        return False
    if country and not _contains(user.country, country):
        return False
    if zip_code and not _contains(user.zip, zip_code):
        return False
    if q:
        blob = " ".join(
            [
                user.name,
                user.lastname,
                user.email,
                user_geography_text(user),
            ]
        )
        if q.lower() not in blob.lower():
            return False
    return True


async def search_users(
    role: UserRole,
    *,
    q: str | None = None,
    name: str | None = None,
    lastname: str | None = None,
    email: str | None = None,
    country: str | None = None,
    zip_code: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[User]:
    has_memory_filters = any([q, name, lastname, email, country, zip_code])

    if email and not any([q, name, lastname, country, zip_code]):
        exact = await User.find_one(
            User.type_user == role,
            User.email_bidx == crypto.blind_index(email),
        )
        return [exact] if exact is not None else []

    if country and not any([q, name, lastname, email, zip_code]):
        users = (
            await User.find(User.type_user == role, User.country == country)
            .skip(skip)
            .limit(limit)
            .to_list()
        )
        return users

    if not has_memory_filters:
        return (
            await User.find(User.type_user == role)
            .skip(skip)
            .limit(limit)
            .to_list()
        )

    users = await User.find(User.type_user == role).to_list()
    filtered = [
        u
        for u in users
        if user_matches_search(
            u,
            q=q,
            name=name,
            lastname=lastname,
            email=email,
            country=country,
            zip_code=zip_code,
        )
    ]
    return filtered[skip : skip + limit]


def node_search_blob(node: Node) -> str:
    return " ".join(
        p
        for p in (
            node.name,
            node.mac_address,
            node.private_ip,
            node.public_ip,
            node.ddns,
            node.address,
            node.zip,
            node.city,
            node.location,
        )
        if p
    )


def node_matches_search(
    node: Node,
    *,
    q: str | None = None,
    name: str | None = None,
    mac_address: str | None = None,
    city: str | None = None,
    public_ip: str | None = None,
    ddns: str | None = None,
) -> bool:
    if name and not _contains(node.name, name):
        return False
    if mac_address and not _contains(node.mac_address, mac_address):
        return False
    if city and not _contains(node.city, city):
        return False
    if public_ip and not _contains(node.public_ip, public_ip):
        return False
    if ddns and not _contains(node.ddns, ddns):
        return False
    if q and q.lower() not in node_search_blob(node).lower():
        return False
    return True


async def search_nodes(
    *,
    q: str | None = None,
    name: str | None = None,
    mac_address: str | None = None,
    city: str | None = None,
    public_ip: str | None = None,
    ddns: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[Node]:
    has_filters = any([q, name, mac_address, city, public_ip, ddns])
    if not has_filters:
        return await Node.find_all().skip(skip).limit(limit).to_list()

    nodes = await Node.find_all().to_list()
    filtered = [
        n
        for n in nodes
        if node_matches_search(
            n,
            q=q,
            name=name,
            mac_address=mac_address,
            city=city,
            public_ip=public_ip,
            ddns=ddns,
        )
    ]
    return filtered[skip : skip + limit]
