"""Org master registry — shared Code/Description CRUD config."""

from people.models import Bank, Department, Division, Location, Position

MASTER_REGISTRY = {
    "departments": {
        "model": Department,
        "singular": "Department",
        "plural": "Departments",
        "view_perm": "masters.view_departments",
        "manage_perm": "masters.manage_departments",
    },
    "divisions": {
        "model": Division,
        "singular": "Division",
        "plural": "Divisions",
        "view_perm": "masters.view_divisions",
        "manage_perm": "masters.manage_divisions",
    },
    "locations": {
        "model": Location,
        "singular": "Location",
        "plural": "Locations",
        "view_perm": "masters.view_locations",
        "manage_perm": "masters.manage_locations",
    },
    "positions": {
        "model": Position,
        "singular": "Position",
        "plural": "Positions",
        "view_perm": "masters.view_positions",
        "manage_perm": "masters.manage_positions",
    },
    "banks": {
        "model": Bank,
        "singular": "Bank",
        "plural": "Banks",
        "view_perm": "masters.view_banks",
        "manage_perm": "masters.manage_banks",
    },
}
