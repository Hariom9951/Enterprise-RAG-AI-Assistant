"""
Enterprise RAG AI Assistant — Database Enums
=============================================
Centralised enum definitions used across ORM models and Pydantic schemas.
Using Python's native ``enum.Enum`` ensures compatibility with both
SQLAlchemy's ``Enum`` column type and Pydantic's schema generation.
"""

import enum


class UserRole(str, enum.Enum):
    """
    RBAC role assigned to every user account.

    Inheriting from ``str`` allows the enum value to be serialised directly
    in JSON responses without extra conversion, and makes it Pydantic-friendly.

    Roles (ordered from least to most privileged):
        USER  — Standard authenticated user. Can use the RAG assistant.
        ADMIN — Full administrative access. Can manage users and system config.
    """

    USER = "USER"
    ADMIN = "ADMIN"
