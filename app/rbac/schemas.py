"""RBAC request/response schemas."""

from datetime import datetime
import enum
import uuid

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class UserRole(str, enum.Enum):
    """System roles per BRD Section 5.2."""

    CUSTOMER = "customer"
    SALES = "sales"
    OPERATIONS = "operations"
    MARKETING = "marketing"
    ADMIN = "admin"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: UserRole
    description: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class UserRoleAssignmentResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    assigned_by: uuid.UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserRolesResponse(BaseModel):
    user_id: uuid.UUID
    roles: list[UserRole]


class UserWithRolesResponse(BaseModel):
    id: uuid.UUID
    email: str | None = None
    mobile_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    profile_picture: str | None = None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime
    roles: list[UserRole] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class UserListWithRolesResponse(BaseModel):
    items: list[UserWithRolesResponse]
    total: int


class AssignRoleRequest(BaseModel):
    user_id: uuid.UUID = Field(..., description="User to assign the role to")
    role: UserRole = Field(..., description="Role to assign")


class RemoveRoleRequest(BaseModel):
    user_id: uuid.UUID = Field(..., description="User to remove the role from")
    role: UserRole = Field(..., description="Role to remove")


class UpdateUserStatusRequest(BaseModel):
    user_id: uuid.UUID = Field(..., description="User ID to update status")
    is_active: bool = Field(..., description="Active status")
