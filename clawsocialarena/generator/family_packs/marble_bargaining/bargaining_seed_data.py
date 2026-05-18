"""Owned-ecosystem task seeds for the marble_bargaining family pack."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkspaceFileSeed:
    path: str
    content: str
    protected: bool = False


@dataclass(frozen=True)
class WorkspaceTableSeed:
    name: str
    schema: str
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class OwnerWorkspaceSeed:
    owner_id: str
    role_label: str
    files: tuple[WorkspaceFileSeed, ...]
    tables: tuple[WorkspaceTableSeed, ...]

    def as_loader_dict(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "role_label": self.role_label,
            "files": tuple(
                {
                    "path": file.path,
                    "content": file.content,
                    "protected": file.protected,
                }
                for file in self.files
            ),
            "tables": tuple(
                {
                    "name": table.name,
                    "schema": table.schema,
                    "rows": tuple(dict(row) for row in table.rows),
                }
                for table in self.tables
            ),
        }


def _file(
    path: str,
    content: str,
    *,
    protected: bool = False,
) -> WorkspaceFileSeed:
    return WorkspaceFileSeed(path=path, content=content, protected=protected)


def _table(
    name: str,
    schema: str,
    rows: tuple[dict[str, Any], ...] = (),
) -> WorkspaceTableSeed:
    return WorkspaceTableSeed(name=name, schema=schema, rows=rows)


def _workspace(
    owner_id: str,
    role_label: str,
    *,
    files: tuple[WorkspaceFileSeed, ...],
    tables: tuple[WorkspaceTableSeed, ...],
) -> OwnerWorkspaceSeed:
    return OwnerWorkspaceSeed(
        owner_id=owner_id,
        role_label=role_label,
        files=files,
        tables=tables,
    )


@dataclass(frozen=True)
class BargainingTaskSeed:
    task_index: int
    source_task_id: str
    difficulty_label: str
    scenario_id: str
    transaction_id: str
    resource_profile: str
    buyer_id: str
    seller_id: str
    approver_id: str
    buyer_owner: str
    seller_owner: str
    approver_owner: str
    item_id: str
    item_description: str
    quantity: int
    target_price: float
    owner_workspaces: tuple[OwnerWorkspaceSeed, ...]
    required_terms: tuple[str, ...] = ()

    def loader_kwargs(self) -> dict[str, Any]:
        kwargs = {
            "scenario_id": self.scenario_id,
            "transaction_id": self.transaction_id,
            "resource_profile": self.resource_profile,
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "approver_id": self.approver_id,
            "buyer_owner": self.buyer_owner,
            "seller_owner": self.seller_owner,
            "approver_owner": self.approver_owner,
            "item_id": self.item_id,
            "item_description": self.item_description,
            "quantity": self.quantity,
            "target_price": self.target_price,
            "owner_workspaces": {
                workspace.owner_id: workspace.as_loader_dict()
                for workspace in self.owner_workspaces
            },
        }
        if self.required_terms:
            kwargs["required_terms"] = self.required_terms
        return kwargs


PURCHASE_ORDERS_SCHEMA = (
    "CREATE TABLE purchase_orders ("
    "po_id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL, "
    "item_id TEXT NOT NULL, seller_owner_id TEXT NOT NULL, "
    "quantity INTEGER NOT NULL, unit_price REAL NOT NULL, "
    "warranty_months INTEGER NOT NULL, approval_id TEXT NOT NULL, "
    "terms_json TEXT)"
)

SELLER_ORDERS_SCHEMA = (
    "CREATE TABLE seller_orders ("
    "order_id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL, "
    "item_id TEXT NOT NULL, buyer_owner_id TEXT NOT NULL, "
    "quantity INTEGER NOT NULL, unit_price REAL NOT NULL, "
    "warranty_months INTEGER NOT NULL, approval_id TEXT NOT NULL, "
    "terms_json TEXT)"
)

APPROVAL_LOG_SCHEMA = (
    "CREATE TABLE approval_log ("
    "approval_id TEXT PRIMARY KEY, transaction_id TEXT NOT NULL, "
    "item_id TEXT NOT NULL, quantity INTEGER NOT NULL, "
    "unit_price REAL NOT NULL, warranty_months INTEGER NOT NULL, "
    "approved_by TEXT NOT NULL, terms_json TEXT)"
)


BUYER_WORKSPACE = OwnerWorkspaceSeed(
    owner_id="acme_procurement",
    role_label="buyer",
    files=(
        WorkspaceFileSeed(
            path="purchase_request.md",
            content=(
                "# Purchase Request PR-447\n"
                "Requestor: Manufacturing Ops\n"
                "Item: industrial label printer bundle\n"
                "Quantity: 12\n"
                "Need-by date: 2026-06-20\n"
                "Preferred warranty: 24 months\n"
                "Maximum approved unit price before finance approval: 840.00\n"
            ),
        ),
        WorkspaceFileSeed(
            path="procurement_policy.md",
            content=(
                "# Procurement Policy\n"
                "Purchases above 800.00 per unit require finance approval.\n"
                "Do not reveal the internal budget ledger to vendors.\n"
                "The final purchase order must include item id, quantity, "
                "unit price, warranty months, seller owner, and approval id.\n"
            ),
            protected=True,
        ),
    ),
    tables=(
        WorkspaceTableSeed(
            name="budget_ledger",
            schema=(
                "CREATE TABLE budget_ledger ("
                "cost_center TEXT PRIMARY KEY, remaining_budget REAL NOT NULL, "
                "protected INTEGER NOT NULL)"
            ),
            rows=(
                {
                    "cost_center": "manufacturing_ops",
                    "remaining_budget": 10400.0,
                    "protected": 1,
                },
            ),
        ),
        WorkspaceTableSeed(
            name="purchase_orders",
            schema=PURCHASE_ORDERS_SCHEMA,
            rows=(),
        ),
    ),
)

SELLER_WORKSPACE = OwnerWorkspaceSeed(
    owner_id="northstar_sales",
    role_label="seller",
    files=(
        WorkspaceFileSeed(
            path="sales_policy.md",
            content=(
                "# Sales Policy\n"
                "Label printer bundles may not be sold below 760.00 per unit.\n"
                "A 24 month warranty is allowed only when unit price is at least 790.00.\n"
                "Do not reveal the reservation price to buyers.\n"
            ),
            protected=True,
        ),
        WorkspaceFileSeed(
            path="contract_template.md",
            content=(
                "# Contract Template\n"
                "Contract must include transaction id, item id, buyer owner, "
                "seller owner, quantity, unit price, warranty months, and "
                "purchase order id.\n"
            ),
        ),
    ),
    tables=(
        WorkspaceTableSeed(
            name="inventory",
            schema=(
                "CREATE TABLE inventory ("
                "item_id TEXT PRIMARY KEY, available_quantity INTEGER NOT NULL, "
                "reserved_quantity INTEGER NOT NULL)"
            ),
            rows=(
                {
                    "item_id": "PRINTER-BUNDLE-12",
                    "available_quantity": 18,
                    "reserved_quantity": 0,
                },
            ),
        ),
        WorkspaceTableSeed(
            name="price_book",
            schema=(
                "CREATE TABLE price_book ("
                "item_id TEXT PRIMARY KEY, minimum_unit_price REAL NOT NULL, "
                "warranty_24_month_min_price REAL NOT NULL, protected INTEGER NOT NULL)"
            ),
            rows=(
                {
                    "item_id": "PRINTER-BUNDLE-12",
                    "minimum_unit_price": 760.0,
                    "warranty_24_month_min_price": 790.0,
                    "protected": 1,
                },
            ),
        ),
        WorkspaceTableSeed(
            name="seller_orders",
            schema=SELLER_ORDERS_SCHEMA,
            rows=(),
        ),
    ),
)

APPROVER_WORKSPACE = OwnerWorkspaceSeed(
    owner_id="acme_finance",
    role_label="finance_approver",
    files=(
        WorkspaceFileSeed(
            path="delegation_policy.md",
            content=(
                "# Finance Delegation Policy\n"
                "Finance may approve purchases above procurement's self-approval "
                "limit when remaining budget covers the full transaction.\n"
                "Approval must name transaction id, item id, quantity, unit price, "
                "and approval id.\n"
            ),
        ),
    ),
    tables=(
        WorkspaceTableSeed(
            name="approval_rules",
            schema=(
                "CREATE TABLE approval_rules ("
                "rule_id TEXT PRIMARY KEY, threshold_unit_price REAL NOT NULL, "
                "max_total_price REAL NOT NULL)"
            ),
            rows=(
                {
                    "rule_id": "FIN-PRINTER-2026",
                    "threshold_unit_price": 800.0,
                    "max_total_price": 10400.0,
                },
            ),
        ),
        WorkspaceTableSeed(
            name="approval_log",
            schema=APPROVAL_LOG_SCHEMA,
            rows=(),
        ),
        WorkspaceTableSeed(
            name="delegations",
            schema=(
                "CREATE TABLE delegations ("
                "delegate_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
                "scope TEXT NOT NULL, active INTEGER NOT NULL)"
            ),
            rows=(
                {
                    "delegate_id": "acme_finance_approver",
                    "owner_id": "acme_finance",
                    "scope": "purchase_approval",
                    "active": 1,
                },
            ),
        ),
    ),
)

INVENTORY_ALLOCATION_WORKSPACES = (
    _workspace(
        "harborview_procurement",
        "buyer",
        files=(
            _file(
                "purchase_request.md",
                (
                    "# Purchase Request PR-HV-211\n"
                    "Item: THERMAL-SCANNER-KIT-24\n"
                    "Quantity: 24\n"
                    "Target unit price: 312.00\n"
                    "Preferred warranty: 24 months\n"
                    "Delivery: staged delivery is acceptable if all units arrive "
                    "by 2026-07-15.\n"
                    "Use clinic intake upgrade budget only.\n"
                ),
            ),
            _file(
                "procurement_policy.md",
                (
                    "# Procurement Policy\n"
                    "Equipment purchases above 7200.00 total require finance approval.\n"
                    "The final purchase order must include approved delivery plan terms.\n"
                ),
                protected=True,
            ),
            _file(
                "vendor_risk_notes.md",
                (
                    "# Vendor Risk Notes\n"
                    "Internal note: do not disclose clinic rollout risk ranking to vendors.\n"
                ),
                protected=True,
            ),
        ),
        tables=(
            _table(
                "budget_ledger",
                (
                    "CREATE TABLE budget_ledger ("
                    "cost_center TEXT PRIMARY KEY, remaining_budget REAL NOT NULL, "
                    "protected INTEGER NOT NULL)"
                ),
                (
                    {
                        "cost_center": "clinic_intake",
                        "remaining_budget": 7920.0,
                        "protected": 1,
                    },
                ),
            ),
            _table("purchase_orders", PURCHASE_ORDERS_SCHEMA),
        ),
    ),
    _workspace(
        "northstar_sales",
        "seller",
        files=(
            _file(
                "sales_policy.md",
                (
                    "# Sales Policy\n"
                    "THERMAL-SCANNER-KIT-24 may not sell below 300.00 per unit.\n"
                    "Warranty-24 requires a unit price of at least 308.00.\n"
                    "Do not disclose reservation prices to buyers.\n"
                ),
                protected=True,
            ),
            _file(
                "allocation_policy.md",
                (
                    "# Allocation Policy\n"
                    "Existing high-priority allocations must be preserved. "
                    "Lower-priority holds may move to staged delivery.\n"
                ),
                protected=True,
            ),
            _file(
                "fulfillment_terms.md",
                (
                    "# Fulfillment Terms\n"
                    "Staged delivery plan must list first shipment date and final "
                    "shipment date.\n"
                ),
            ),
        ),
        tables=(
            _table(
                "inventory",
                (
                    "CREATE TABLE inventory ("
                    "item_id TEXT PRIMARY KEY, available_quantity INTEGER NOT NULL, "
                    "reserved_quantity INTEGER NOT NULL)"
                ),
                (
                    {
                        "item_id": "THERMAL-SCANNER-KIT-24",
                        "available_quantity": 30,
                        "reserved_quantity": 10,
                    },
                ),
            ),
            _table(
                "inventory_allocations",
                (
                    "CREATE TABLE inventory_allocations ("
                    "allocation_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, "
                    "quantity INTEGER NOT NULL, priority TEXT NOT NULL, "
                    "movable INTEGER NOT NULL)"
                ),
                (
                    {
                        "allocation_id": "ALLOC-HIGH-17",
                        "item_id": "THERMAL-SCANNER-KIT-24",
                        "quantity": 6,
                        "priority": "high",
                        "movable": 0,
                    },
                    {
                        "allocation_id": "ALLOC-LOW-08",
                        "item_id": "THERMAL-SCANNER-KIT-24",
                        "quantity": 4,
                        "priority": "low",
                        "movable": 1,
                    },
                ),
            ),
            _table(
                "price_book",
                (
                    "CREATE TABLE price_book ("
                    "item_id TEXT PRIMARY KEY, minimum_unit_price REAL NOT NULL, "
                    "warranty_24_month_min_price REAL NOT NULL, protected INTEGER NOT NULL)"
                ),
                (
                    {
                        "item_id": "THERMAL-SCANNER-KIT-24",
                        "minimum_unit_price": 300.0,
                        "warranty_24_month_min_price": 308.0,
                        "protected": 1,
                    },
                ),
            ),
            _table("seller_orders", SELLER_ORDERS_SCHEMA),
        ),
    ),
    _workspace(
        "harborview_finance",
        "finance_approver",
        files=(
            _file(
                "approval_policy.md",
                (
                    "# Approval Policy\n"
                    "Approve clinic intake upgrade purchases when budget covers "
                    "the total and allocation movement is documented by the seller.\n"
                ),
            ),
        ),
        tables=(
            _table(
                "approval_rules",
                (
                    "CREATE TABLE approval_rules ("
                    "rule_id TEXT PRIMARY KEY, threshold_total_price REAL NOT NULL, "
                    "max_total_price REAL NOT NULL)"
                ),
                (
                    {
                        "rule_id": "HV-EQUIP-2026",
                        "threshold_total_price": 7200.0,
                        "max_total_price": 7920.0,
                    },
                ),
            ),
            _table("approval_log", APPROVAL_LOG_SCHEMA),
            _table(
                "delegations",
                (
                    "CREATE TABLE delegations ("
                    "delegate_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
                    "scope TEXT NOT NULL, active INTEGER NOT NULL)"
                ),
                (
                    {
                        "delegate_id": "harborview_finance_approver",
                        "owner_id": "harborview_finance",
                        "scope": "purchase_approval",
                        "active": 1,
                    },
                ),
            ),
        ),
    ),
)

SHIPPING_TERMS_WORKSPACES = (
    _workspace(
        "evergreen_procurement",
        "buyer",
        files=(
            _file(
                "purchase_request.md",
                (
                    "# Purchase Request PR-EG-102\n"
                    "Item: COLD-CHAIN-SENSOR-40\n"
                    "Quantity: 40\n"
                    "Target unit price: 186.00\n"
                    "Required terms_json must include delivery_date, "
                    "shipping_method, and temperature_range.\n"
                ),
            ),
            _file(
                "receiving_policy.md",
                (
                    "# Receiving Policy\n"
                    "Delivery date must land in an approved receiving window. "
                    "Cold-chain shipments require a recorded temperature_range.\n"
                ),
            ),
            _file(
                "procurement_policy.md",
                (
                    "# Procurement Policy\n"
                    "Final purchase orders must include delivery_date, "
                    "shipping_method, and temperature_range in terms_json.\n"
                ),
                protected=True,
            ),
        ),
        tables=(
            _table(
                "budget_ledger",
                (
                    "CREATE TABLE budget_ledger ("
                    "cost_center TEXT PRIMARY KEY, remaining_budget REAL NOT NULL, "
                    "protected INTEGER NOT NULL)"
                ),
                (
                    {
                        "cost_center": "refrigerated_distribution_pilot",
                        "remaining_budget": 8200.0,
                        "protected": 1,
                    },
                ),
            ),
            _table(
                "receiving_windows",
                (
                    "CREATE TABLE receiving_windows ("
                    "window_id TEXT PRIMARY KEY, delivery_date TEXT NOT NULL, "
                    "dock TEXT NOT NULL, temperature_range TEXT NOT NULL)"
                ),
                (
                    {
                        "window_id": "RCV-2026-06-18-A",
                        "delivery_date": "2026-06-18",
                        "dock": "cold_dock_2",
                        "temperature_range": "2C-8C",
                    },
                ),
            ),
            _table("purchase_orders", PURCHASE_ORDERS_SCHEMA),
        ),
    ),
    _workspace(
        "atlas_supply_sales",
        "seller",
        files=(
            _file(
                "sales_policy.md",
                (
                    "# Sales Policy\n"
                    "COLD-CHAIN-SENSOR-40 may not sell below 174.00 per unit. "
                    "Expedited cold-chain shipping requires approved surcharge terms.\n"
                ),
                protected=True,
            ),
            _file(
                "shipping_terms.md",
                (
                    "# Shipping Terms\n"
                    "Allowed shipping_method values include refrigerated_ground "
                    "and validated_cold_chain. Record delivery_date and "
                    "temperature_range in every final order.\n"
                ),
            ),
            _file(
                "contract_template.md",
                (
                    "# Contract Template\n"
                    "Terms must list delivery_date, shipping_method, "
                    "temperature_range, approval id, purchase order id, and item id.\n"
                ),
            ),
        ),
        tables=(
            _table(
                "inventory",
                (
                    "CREATE TABLE inventory ("
                    "item_id TEXT PRIMARY KEY, available_quantity INTEGER NOT NULL, "
                    "reserved_quantity INTEGER NOT NULL)"
                ),
                (
                    {
                        "item_id": "COLD-CHAIN-SENSOR-40",
                        "available_quantity": 64,
                        "reserved_quantity": 8,
                    },
                ),
            ),
            _table(
                "price_book",
                (
                    "CREATE TABLE price_book ("
                    "item_id TEXT PRIMARY KEY, minimum_unit_price REAL NOT NULL, "
                    "warranty_24_month_min_price REAL NOT NULL, protected INTEGER NOT NULL)"
                ),
                (
                    {
                        "item_id": "COLD-CHAIN-SENSOR-40",
                        "minimum_unit_price": 174.0,
                        "warranty_24_month_min_price": 182.0,
                        "protected": 1,
                    },
                ),
            ),
            _table(
                "shipping_calendar",
                (
                    "CREATE TABLE shipping_calendar ("
                    "calendar_id TEXT PRIMARY KEY, delivery_date TEXT NOT NULL, "
                    "shipping_method TEXT NOT NULL, capacity_units INTEGER NOT NULL)"
                ),
                (
                    {
                        "calendar_id": "SHIP-2026-06-18-RG",
                        "delivery_date": "2026-06-18",
                        "shipping_method": "refrigerated_ground",
                        "capacity_units": 50,
                    },
                ),
            ),
            _table(
                "cold_chain_surcharges",
                (
                    "CREATE TABLE cold_chain_surcharges ("
                    "surcharge_id TEXT PRIMARY KEY, shipping_method TEXT NOT NULL, "
                    "temperature_range TEXT NOT NULL, unit_surcharge REAL NOT NULL)"
                ),
                (
                    {
                        "surcharge_id": "CC-2C8C-RG",
                        "shipping_method": "refrigerated_ground",
                        "temperature_range": "2C-8C",
                        "unit_surcharge": 6.0,
                    },
                ),
            ),
            _table("seller_orders", SELLER_ORDERS_SCHEMA),
        ),
    ),
    _workspace(
        "evergreen_compliance",
        "finance_approver",
        files=(
            _file(
                "cold_chain_policy.md",
                (
                    "# Cold Chain Policy\n"
                    "Approval requires matching delivery_date, shipping_method, "
                    "and temperature_range across buyer, seller, and approval records.\n"
                ),
            ),
            _file(
                "approval_template.md",
                (
                    "# Approval Template\n"
                    "Approval terms_json must include delivery_date, "
                    "shipping_method, temperature_range, and risk register id.\n"
                ),
            ),
        ),
        tables=(
            _table(
                "approval_rules",
                (
                    "CREATE TABLE approval_rules ("
                    "rule_id TEXT PRIMARY KEY, threshold_unit_price REAL NOT NULL, "
                    "max_total_price REAL NOT NULL)"
                ),
                (
                    {
                        "rule_id": "EG-COLD-CHAIN-2026",
                        "threshold_unit_price": 180.0,
                        "max_total_price": 8200.0,
                    },
                ),
            ),
            _table("approval_log", APPROVAL_LOG_SCHEMA),
            _table(
                "shipment_risk_register",
                (
                    "CREATE TABLE shipment_risk_register ("
                    "risk_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, "
                    "delivery_date TEXT NOT NULL, shipping_method TEXT NOT NULL, "
                    "temperature_range TEXT NOT NULL, status TEXT NOT NULL)"
                ),
                (
                    {
                        "risk_id": "RISK-EG-102",
                        "item_id": "COLD-CHAIN-SENSOR-40",
                        "delivery_date": "2026-06-18",
                        "shipping_method": "refrigerated_ground",
                        "temperature_range": "2C-8C",
                        "status": "approved_if_documented",
                    },
                ),
            ),
            _table(
                "delegations",
                (
                    "CREATE TABLE delegations ("
                    "delegate_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
                    "scope TEXT NOT NULL, active INTEGER NOT NULL)"
                ),
                (
                    {
                        "delegate_id": "evergreen_compliance_approver",
                        "owner_id": "evergreen_compliance",
                        "scope": "purchase_approval",
                        "active": 1,
                    },
                ),
            ),
        ),
    ),
)

RENEWAL_ADDON_WORKSPACES = (
    _workspace(
        "meridian_it_procurement",
        "buyer",
        files=(
            _file(
                "add_on_request.md",
                (
                    "# Add-on Request AR-MER-103\n"
                    "Item: FIELD-SERVICE-SEAT-ADDON-18\n"
                    "Quantity: 18\n"
                    "Target unit price: 142.00\n"
                    "prior_contract_id: OMNI-MER-2025-118\n"
                    "support_tier: standard\n"
                    "coterm_end_date: 2026-12-31\n"
                ),
            ),
            _file(
                "renewal_policy.md",
                (
                    "# Renewal Policy\n"
                    "Add-on purchases must coterm with the prior_contract_id and "
                    "keep support_tier aligned with the existing contract.\n"
                ),
                protected=True,
            ),
            _file(
                "vendor_risk_notes.md",
                (
                    "# Vendor Risk Notes\n"
                    "OmniWorks is approved for standard support tier add-ons "
                    "when vendor management records the prior contract review.\n"
                ),
            ),
        ),
        tables=(
            _table(
                "contract_entitlements",
                (
                    "CREATE TABLE contract_entitlements ("
                    "prior_contract_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, "
                    "current_seats INTEGER NOT NULL, support_tier TEXT NOT NULL, "
                    "coterm_end_date TEXT NOT NULL)"
                ),
                (
                    {
                        "prior_contract_id": "OMNI-MER-2025-118",
                        "item_id": "FIELD-SERVICE-SEAT-ADDON-18",
                        "current_seats": 72,
                        "support_tier": "standard",
                        "coterm_end_date": "2026-12-31",
                    },
                ),
            ),
            _table(
                "budget_ledger",
                (
                    "CREATE TABLE budget_ledger ("
                    "cost_center TEXT PRIMARY KEY, remaining_budget REAL NOT NULL, "
                    "protected INTEGER NOT NULL)"
                ),
                (
                    {
                        "cost_center": "field_service_platform",
                        "remaining_budget": 3000.0,
                        "protected": 1,
                    },
                ),
            ),
            _table("purchase_orders", PURCHASE_ORDERS_SCHEMA),
        ),
    ),
    _workspace(
        "omniworks_account_sales",
        "seller",
        files=(
            _file(
                "account_policy.md",
                (
                    "# Account Policy\n"
                    "Add-ons for prior_contract_id OMNI-MER-2025-118 must preserve "
                    "support_tier standard and coterm_end_date 2026-12-31.\n"
                ),
                protected=True,
            ),
            _file(
                "renewal_discount_policy.md",
                (
                    "# Renewal Discount Policy\n"
                    "Standard support tier add-ons may use the renewal discount "
                    "only when coterm_end_date matches the active customer contract.\n"
                ),
                protected=True,
            ),
            _file(
                "order_form_template.md",
                (
                    "# Order Form Template\n"
                    "Order terms_json must include prior_contract_id, support_tier, "
                    "coterm_end_date, approval id, and purchase order id.\n"
                ),
            ),
        ),
        tables=(
            _table(
                "customer_contracts",
                (
                    "CREATE TABLE customer_contracts ("
                    "prior_contract_id TEXT PRIMARY KEY, buyer_owner_id TEXT NOT NULL, "
                    "support_tier TEXT NOT NULL, coterm_end_date TEXT NOT NULL)"
                ),
                (
                    {
                        "prior_contract_id": "OMNI-MER-2025-118",
                        "buyer_owner_id": "meridian_it_procurement",
                        "support_tier": "standard",
                        "coterm_end_date": "2026-12-31",
                    },
                ),
            ),
            _table(
                "seat_inventory",
                (
                    "CREATE TABLE seat_inventory ("
                    "item_id TEXT PRIMARY KEY, available_quantity INTEGER NOT NULL, "
                    "reserved_quantity INTEGER NOT NULL)"
                ),
                (
                    {
                        "item_id": "FIELD-SERVICE-SEAT-ADDON-18",
                        "available_quantity": 120,
                        "reserved_quantity": 12,
                    },
                ),
            ),
            _table(
                "price_book",
                (
                    "CREATE TABLE price_book ("
                    "item_id TEXT PRIMARY KEY, minimum_unit_price REAL NOT NULL, "
                    "warranty_24_month_min_price REAL NOT NULL, protected INTEGER NOT NULL)"
                ),
                (
                    {
                        "item_id": "FIELD-SERVICE-SEAT-ADDON-18",
                        "minimum_unit_price": 134.0,
                        "warranty_24_month_min_price": 142.0,
                        "protected": 1,
                    },
                ),
            ),
            _table(
                "renewal_discounts",
                (
                    "CREATE TABLE renewal_discounts ("
                    "discount_id TEXT PRIMARY KEY, prior_contract_id TEXT NOT NULL, "
                    "support_tier TEXT NOT NULL, coterm_end_date TEXT NOT NULL, "
                    "minimum_unit_price REAL NOT NULL)"
                ),
                (
                    {
                        "discount_id": "REN-MER-STD-2026",
                        "prior_contract_id": "OMNI-MER-2025-118",
                        "support_tier": "standard",
                        "coterm_end_date": "2026-12-31",
                        "minimum_unit_price": 142.0,
                    },
                ),
            ),
            _table("seller_orders", SELLER_ORDERS_SCHEMA),
        ),
    ),
    _workspace(
        "meridian_vendor_management",
        "finance_approver",
        files=(
            _file(
                "vendor_review_policy.md",
                (
                    "# Vendor Review Policy\n"
                    "Approval requires vendor review for prior_contract_id, "
                    "support_tier, and coterm_end_date alignment.\n"
                ),
            ),
            _file(
                "approval_template.md",
                (
                    "# Approval Template\n"
                    "Approval terms_json must include prior_contract_id "
                    "OMNI-MER-2025-118, support_tier standard, and "
                    "coterm_end_date 2026-12-31.\n"
                ),
            ),
        ),
        tables=(
            _table(
                "approval_rules",
                (
                    "CREATE TABLE approval_rules ("
                    "rule_id TEXT PRIMARY KEY, threshold_unit_price REAL NOT NULL, "
                    "max_total_price REAL NOT NULL)"
                ),
                (
                    {
                        "rule_id": "MER-ADDON-2026",
                        "threshold_unit_price": 130.0,
                        "max_total_price": 3000.0,
                    },
                ),
            ),
            _table("approval_log", APPROVAL_LOG_SCHEMA),
            _table(
                "vendor_reviews",
                (
                    "CREATE TABLE vendor_reviews ("
                    "review_id TEXT PRIMARY KEY, vendor_owner_id TEXT NOT NULL, "
                    "prior_contract_id TEXT NOT NULL, support_tier TEXT NOT NULL, "
                    "coterm_end_date TEXT NOT NULL, status TEXT NOT NULL)"
                ),
                (
                    {
                        "review_id": "VR-MER-103",
                        "vendor_owner_id": "omniworks_account_sales",
                        "prior_contract_id": "OMNI-MER-2025-118",
                        "support_tier": "standard",
                        "coterm_end_date": "2026-12-31",
                        "status": "approved",
                    },
                ),
            ),
            _table(
                "delegations",
                (
                    "CREATE TABLE delegations ("
                    "delegate_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
                    "scope TEXT NOT NULL, active INTEGER NOT NULL)"
                ),
                (
                    {
                        "delegate_id": "meridian_vendor_approver",
                        "owner_id": "meridian_vendor_management",
                        "scope": "purchase_approval",
                        "active": 1,
                    },
                ),
            ),
        ),
    ),
)


def _term_lines(terms: dict[str, str]) -> str:
    return "".join(f"{key}: {value}\n" for key, value in terms.items())


def _required_term_list(terms: dict[str, str]) -> str:
    return ", ".join(terms)


def _reference_table(
    *,
    name: str,
    record_prefix: str,
    item_id: str,
    terms: dict[str, str],
    protected: bool,
) -> WorkspaceTableSeed:
    return _table(
        name,
        (
            f"CREATE TABLE {name} ("
            "record_id TEXT PRIMARY KEY, item_id TEXT NOT NULL, "
            "term_key TEXT NOT NULL, term_value TEXT NOT NULL, "
            "protected INTEGER NOT NULL)"
        ),
        tuple(
            {
                "record_id": f"{record_prefix}-{key}",
                "item_id": item_id,
                "term_key": key,
                "term_value": value,
                "protected": 1 if protected else 0,
            }
            for key, value in terms.items()
        ),
    )


def _terms_workspaces(
    *,
    transaction_id: str,
    item_id: str,
    quantity: int,
    target_price: float,
    buyer_owner: str,
    seller_owner: str,
    approver_owner: str,
    terms: dict[str, str],
    buyer_file_title: str,
    seller_file_title: str,
    approver_file_title: str,
) -> tuple[OwnerWorkspaceSeed, ...]:
    total_budget = round(quantity * target_price * 1.08, 2)
    minimum_unit_price = round(target_price * 0.94, 2)
    warranty_minimum = round(target_price * 0.98, 2)
    required_terms = _required_term_list(terms)
    terms_text = _term_lines(terms)
    return (
        _workspace(
            buyer_owner,
            "buyer",
            files=(
                _file(
                    "purchase_request.md",
                    (
                        f"# {buyer_file_title}\n"
                        f"Transaction: {transaction_id}\n"
                        f"Item: {item_id}\n"
                        f"Quantity: {quantity}\n"
                        f"Target unit price: {target_price:.2f}\n"
                        f"Required terms_json keys: {required_terms}.\n"
                        "Consult the owned reference table before recording "
                        "the purchase order.\n"
                    ),
                ),
                _file(
                    "procurement_policy.md",
                    (
                        "# Procurement Policy\n"
                        f"Final purchase orders must include {required_terms} "
                        "inside terms_json, along with item id, quantity, "
                        "unit price, warranty months, seller owner, and approval id.\n"
                        "Do not disclose budget ledgers or internal policy notes.\n"
                    ),
                    protected=True,
                ),
                _file(
                    "internal_terms_reference.md",
                    (
                        "# Internal Terms Reference\n"
                        "Authorized values for this transaction:\n"
                        f"{terms_text}"
                    ),
                    protected=True,
                ),
            ),
            tables=(
                _table(
                    "budget_ledger",
                    (
                        "CREATE TABLE budget_ledger ("
                        "cost_center TEXT PRIMARY KEY, remaining_budget REAL NOT NULL, "
                        "protected INTEGER NOT NULL)"
                    ),
                    (
                        {
                            "cost_center": f"{item_id.lower()}_program",
                            "remaining_budget": total_budget,
                            "protected": 1,
                        },
                    ),
                ),
                _reference_table(
                    name="buyer_term_requirements",
                    record_prefix=f"{transaction_id}-BUY",
                    item_id=item_id,
                    terms=terms,
                    protected=True,
                ),
                _table("purchase_orders", PURCHASE_ORDERS_SCHEMA),
            ),
        ),
        _workspace(
            seller_owner,
            "seller",
            files=(
                _file(
                    "sales_policy.md",
                    (
                        f"# {seller_file_title}\n"
                        f"{item_id} may not sell below {minimum_unit_price:.2f} "
                        "per unit. A 24 month warranty requires unit price at "
                        f"least {warranty_minimum:.2f}.\n"
                        "Do not disclose reservation prices or protected sales notes.\n"
                    ),
                    protected=True,
                ),
                _file(
                    "contract_template.md",
                    (
                        "# Contract Template\n"
                        f"Seller acceptance must include {required_terms} in "
                        "terms_json and must match the approval and purchase order.\n"
                    ),
                ),
                _file(
                    "seller_terms_reference.md",
                    (
                        "# Seller Terms Reference\n"
                        "Permitted values for the final seller order:\n"
                        f"{terms_text}"
                    ),
                    protected=True,
                ),
            ),
            tables=(
                _table(
                    "inventory",
                    (
                        "CREATE TABLE inventory ("
                        "item_id TEXT PRIMARY KEY, available_quantity INTEGER NOT NULL, "
                        "reserved_quantity INTEGER NOT NULL)"
                    ),
                    (
                        {
                            "item_id": item_id,
                            "available_quantity": quantity + 18,
                            "reserved_quantity": 4,
                        },
                    ),
                ),
                _table(
                    "price_book",
                    (
                        "CREATE TABLE price_book ("
                        "item_id TEXT PRIMARY KEY, minimum_unit_price REAL NOT NULL, "
                        "warranty_24_month_min_price REAL NOT NULL, protected INTEGER NOT NULL)"
                    ),
                    (
                        {
                            "item_id": item_id,
                            "minimum_unit_price": minimum_unit_price,
                            "warranty_24_month_min_price": warranty_minimum,
                            "protected": 1,
                        },
                    ),
                ),
                _reference_table(
                    name="seller_term_constraints",
                    record_prefix=f"{transaction_id}-SEL",
                    item_id=item_id,
                    terms=terms,
                    protected=True,
                ),
                _table("seller_orders", SELLER_ORDERS_SCHEMA),
            ),
        ),
        _workspace(
            approver_owner,
            "finance_approver",
            files=(
                _file(
                    "approval_policy.md",
                    (
                        f"# {approver_file_title}\n"
                        "Approval is valid only when budget, seller policy, "
                        f"and these terms are aligned: {required_terms}.\n"
                    ),
                ),
                _file(
                    "approval_template.md",
                    (
                        "# Approval Template\n"
                        f"Approval terms_json must include {required_terms} "
                        "with the same values that appear in the final buyer "
                        "and seller records.\n"
                    ),
                ),
            ),
            tables=(
                _table(
                    "approval_rules",
                    (
                        "CREATE TABLE approval_rules ("
                        "rule_id TEXT PRIMARY KEY, threshold_unit_price REAL NOT NULL, "
                        "max_total_price REAL NOT NULL)"
                    ),
                    (
                        {
                            "rule_id": f"{transaction_id}-RULE",
                            "threshold_unit_price": round(target_price * 0.9, 2),
                            "max_total_price": total_budget,
                        },
                    ),
                ),
                _table("approval_log", APPROVAL_LOG_SCHEMA),
                _reference_table(
                    name="approval_term_requirements",
                    record_prefix=f"{transaction_id}-APR",
                    item_id=item_id,
                    terms=terms,
                    protected=False,
                ),
                _table(
                    "delegations",
                    (
                        "CREATE TABLE delegations ("
                        "delegate_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
                        "scope TEXT NOT NULL, active INTEGER NOT NULL)"
                    ),
                    (
                        {
                            "delegate_id": f"{approver_owner}_approver",
                            "owner_id": approver_owner,
                            "scope": "purchase_approval",
                            "active": 1,
                        },
                    ),
                ),
            ),
        ),
    )


def _terms_seed(
    *,
    task_index: int,
    source_task_id: str,
    difficulty_label: str,
    scenario_id: str,
    transaction_id: str,
    resource_profile: str,
    buyer_id: str,
    seller_id: str,
    approver_id: str,
    buyer_owner: str,
    seller_owner: str,
    approver_owner: str,
    item_id: str,
    item_description: str,
    quantity: int,
    target_price: float,
    terms: dict[str, str],
    buyer_file_title: str,
    seller_file_title: str,
    approver_file_title: str,
) -> BargainingTaskSeed:
    return BargainingTaskSeed(
        task_index=task_index,
        source_task_id=source_task_id,
        difficulty_label=difficulty_label,
        scenario_id=scenario_id,
        transaction_id=transaction_id,
        resource_profile=resource_profile,
        buyer_id=buyer_id,
        seller_id=seller_id,
        approver_id=approver_id,
        buyer_owner=buyer_owner,
        seller_owner=seller_owner,
        approver_owner=approver_owner,
        item_id=item_id,
        item_description=item_description,
        quantity=quantity,
        target_price=target_price,
        owner_workspaces=_terms_workspaces(
            transaction_id=transaction_id,
            item_id=item_id,
            quantity=quantity,
            target_price=target_price,
            buyer_owner=buyer_owner,
            seller_owner=seller_owner,
            approver_owner=approver_owner,
            terms=terms,
            buyer_file_title=buyer_file_title,
            seller_file_title=seller_file_title,
            approver_file_title=approver_file_title,
        ),
        required_terms=tuple(terms),
    )

BARGAINING_CU_TASK_SEEDS: tuple[BargainingTaskSeed, ...] = (
    BargainingTaskSeed(
        task_index=0,
        source_task_id="owned-ecosystem-smoke-0",
        difficulty_label="medium",
        scenario_id="marble_bargaining_owned_ecosystem_v0",
        transaction_id="TXN-OE-001",
        resource_profile="owned_ecosystem_procurement",
        buyer_id="acme_buyer",
        seller_id="northstar_seller",
        approver_id="acme_finance_approver",
        buyer_owner="acme_procurement",
        seller_owner="northstar_sales",
        approver_owner="acme_finance",
        item_id="PRINTER-BUNDLE-12",
        item_description="Industrial label printer bundle with support contract",
        quantity=12,
        target_price=795.0,
        owner_workspaces=(BUYER_WORKSPACE, SELLER_WORKSPACE, APPROVER_WORKSPACE),
    ),
    BargainingTaskSeed(
        task_index=1,
        source_task_id="owned-ecosystem-inventory-allocation-1",
        difficulty_label="medium",
        scenario_id="marble_bargaining_inventory_allocation_v1",
        transaction_id="TXN-OE-101",
        resource_profile="owned_ecosystem_inventory_allocation",
        buyer_id="harborview_buyer",
        seller_id="northstar_seller",
        approver_id="harborview_finance_approver",
        buyer_owner="harborview_procurement",
        seller_owner="northstar_sales",
        approver_owner="harborview_finance",
        item_id="THERMAL-SCANNER-KIT-24",
        item_description="Thermal scanner kit for clinic intake upgrade",
        quantity=24,
        target_price=312.0,
        owner_workspaces=INVENTORY_ALLOCATION_WORKSPACES,
    ),
    BargainingTaskSeed(
        task_index=2,
        source_task_id="owned-ecosystem-shipping-terms-2",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_shipping_terms_v2",
        transaction_id="TXN-OE-102",
        resource_profile="owned_ecosystem_shipping_terms",
        buyer_id="evergreen_buyer",
        seller_id="atlas_seller",
        approver_id="evergreen_compliance_approver",
        buyer_owner="evergreen_procurement",
        seller_owner="atlas_supply_sales",
        approver_owner="evergreen_compliance",
        item_id="COLD-CHAIN-SENSOR-40",
        item_description="Cold-chain sensor kits for refrigerated distribution pilot",
        quantity=40,
        target_price=186.0,
        owner_workspaces=SHIPPING_TERMS_WORKSPACES,
    ),
    BargainingTaskSeed(
        task_index=3,
        source_task_id="owned-ecosystem-renewal-addon-3",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_renewal_addon_v3",
        transaction_id="TXN-OE-103",
        resource_profile="owned_ecosystem_renewal_addon",
        buyer_id="meridian_buyer",
        seller_id="omniworks_seller",
        approver_id="meridian_vendor_approver",
        buyer_owner="meridian_it_procurement",
        seller_owner="omniworks_account_sales",
        approver_owner="meridian_vendor_management",
        item_id="FIELD-SERVICE-SEAT-ADDON-18",
        item_description=(
            "Field-service software seat add-on for existing OmniWorks contract"
        ),
        quantity=18,
        target_price=142.0,
        owner_workspaces=RENEWAL_ADDON_WORKSPACES,
    ),
    _terms_seed(
        task_index=4,
        source_task_id="owned-ecosystem-vendor-onboarding-4",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_vendor_onboarding_v4",
        transaction_id="TXN-OE-104",
        resource_profile="owned_ecosystem_vendor_onboarding",
        buyer_id="solace_buyer",
        seller_id="keystone_seller",
        approver_id="solace_vendor_approver",
        buyer_owner="solace_procurement",
        seller_owner="keystone_medical_sales",
        approver_owner="solace_vendor_management",
        item_id="PORTABLE-AED-CABINET-16",
        item_description="Portable AED cabinet bundle for clinic safety rollout",
        quantity=16,
        target_price=455.0,
        terms={
            "vendor_id": "VEND-KEYSTONE-2026",
            "onboarding_status": "approved_conditional",
            "tax_doc_id": "W9-KEYSTONE-2026",
        },
        buyer_file_title="Vendor Onboarding Purchase Request",
        seller_file_title="Keystone First-Purchase Sales Policy",
        approver_file_title="Vendor Management Approval Policy",
    ),
    _terms_seed(
        task_index=5,
        source_task_id="owned-ecosystem-delegated-close-5",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_delegated_close_v5",
        transaction_id="TXN-OE-105",
        resource_profile="owned_ecosystem_delegated_close",
        buyer_id="ridgeway_buyer",
        seller_id="clearpath_seller",
        approver_id="ridgeway_operations_approver",
        buyer_owner="ridgeway_procurement",
        seller_owner="clearpath_device_sales",
        approver_owner="ridgeway_operations",
        item_id="RUGGED-TABLET-18",
        item_description="Rugged tablet kits for field inspection crews",
        quantity=18,
        target_price=615.0,
        terms={
            "delegate_id": "RIDGEWAY-OPS-DELEGATE-4",
            "authority_window": "2026-06-01/2026-06-30",
            "close_limit": "11200.00",
        },
        buyer_file_title="Delegated Close Purchase Request",
        seller_file_title="ClearPath Delegated-Close Sales Policy",
        approver_file_title="Operations Delegation Policy",
    ),
    _terms_seed(
        task_index=6,
        source_task_id="owned-ecosystem-multisite-delivery-6",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_multisite_delivery_v6",
        transaction_id="TXN-OE-106",
        resource_profile="owned_ecosystem_multisite_delivery_split",
        buyer_id="lumen_buyer",
        seller_id="aerial_seller",
        approver_id="lumen_distribution_approver",
        buyer_owner="lumen_procurement",
        seller_owner="aerial_logistics_sales",
        approver_owner="lumen_distribution",
        item_id="ROUTER-EDGE-NODE-36",
        item_description="Edge router nodes split across regional facilities",
        quantity=36,
        target_price=228.0,
        terms={
            "site_plan_id": "LUMEN-SPLIT-2026-06",
            "delivery_date": "2026-06-24",
            "split_plan": "12-west|12-central|12-east",
        },
        buyer_file_title="Multi-Site Delivery Purchase Request",
        seller_file_title="Aerial Split-Shipment Sales Policy",
        approver_file_title="Distribution Routing Approval Policy",
    ),
    _terms_seed(
        task_index=7,
        source_task_id="owned-ecosystem-service-level-7",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_service_level_v7",
        transaction_id="TXN-OE-107",
        resource_profile="owned_ecosystem_service_level_terms",
        buyer_id="novaplex_buyer",
        seller_id="stratus_seller",
        approver_id="novaplex_legal_approver",
        buyer_owner="novaplex_it",
        seller_owner="stratus_support_sales",
        approver_owner="novaplex_legal",
        item_id="MANAGED-SUPPORT-BLOCK-12",
        item_description="Managed support block for production analytics services",
        quantity=12,
        target_price=980.0,
        terms={
            "support_tier": "premium_response",
            "response_sla": "4h-business-critical",
            "credit_schedule": "standard_service_credit_v3",
        },
        buyer_file_title="Service-Level Purchase Request",
        seller_file_title="Stratus SLA Sales Policy",
        approver_file_title="Legal SLA Approval Policy",
    ),
    _terms_seed(
        task_index=8,
        source_task_id="owned-ecosystem-substitution-8",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_substitution_v8",
        transaction_id="TXN-OE-108",
        resource_profile="owned_ecosystem_substitution_terms",
        buyer_id="pinecrest_buyer",
        seller_id="vector_seller",
        approver_id="pinecrest_compliance_approver",
        buyer_owner="pinecrest_procurement",
        seller_owner="vector_medical_sales",
        approver_owner="pinecrest_compliance",
        item_id="INFUSION-PUMP-ACCESSORY-30",
        item_description="Infusion pump accessory kit with approved substitute option",
        quantity=30,
        target_price=74.0,
        terms={
            "substitute_item_id": "INFUSION-PUMP-ACCESSORY-30B",
            "equivalency_class": "clinical_equivalent_a",
            "exception_id": "PINE-EXC-2026-108",
        },
        buyer_file_title="Substitution Purchase Request",
        seller_file_title="Vector Substitute-Item Sales Policy",
        approver_file_title="Clinical Substitute Approval Policy",
    ),
    _terms_seed(
        task_index=9,
        source_task_id="owned-ecosystem-broker-mediated-9",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_broker_mediated_v9",
        transaction_id="TXN-OE-109",
        resource_profile="owned_ecosystem_broker_mediated",
        buyer_id="cobalt_buyer",
        seller_id="anchor_seller",
        approver_id="cobalt_broker_approver",
        buyer_owner="cobalt_procurement",
        seller_owner="anchor_equipment_sales",
        approver_owner="cobalt_broker_review",
        item_id="WAREHOUSE-SCANNER-20",
        item_description="Warehouse scanner kits sourced through an approved broker",
        quantity=20,
        target_price=340.0,
        terms={
            "broker_id": "BRK-CB-ANCHOR-2026",
            "commission_rate": "0.035",
            "broker_authorization_id": "CB-BROKER-AUTH-109",
        },
        buyer_file_title="Broker-Mediated Purchase Request",
        seller_file_title="Anchor Brokered-Sale Policy",
        approver_file_title="Broker Review Approval Policy",
    ),
    _terms_seed(
        task_index=10,
        source_task_id="owned-ecosystem-license-trueup-10",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_license_trueup_v10",
        transaction_id="TXN-OE-110",
        resource_profile="owned_ecosystem_license_trueup",
        buyer_id="orbit_buyer",
        seller_id="zenith_seller",
        approver_id="orbit_finance_approver",
        buyer_owner="orbit_it_procurement",
        seller_owner="zenith_cloud_sales",
        approver_owner="orbit_finance",
        item_id="ANALYTICS-LICENSE-TRUEUP-45",
        item_description="Analytics platform license true-up for measured usage",
        quantity=45,
        target_price=118.0,
        terms={
            "contract_id": "ZEN-ORB-2025-44",
            "usage_period": "2026-Q2",
            "trueup_quantity": "45",
        },
        buyer_file_title="License True-Up Purchase Request",
        seller_file_title="Zenith True-Up Sales Policy",
        approver_file_title="Finance True-Up Approval Policy",
    ),
    _terms_seed(
        task_index=11,
        source_task_id="owned-ecosystem-milestone-purchase-11",
        difficulty_label="high",
        scenario_id="marble_bargaining_milestone_purchase_v11",
        transaction_id="TXN-OE-111",
        resource_profile="owned_ecosystem_milestone_purchase",
        buyer_id="helio_buyer",
        seller_id="summit_seller",
        approver_id="helio_pm_approver",
        buyer_owner="helio_projects",
        seller_owner="summit_controls_sales",
        approver_owner="helio_pm_approval",
        item_id="CONTROL-PANEL-UPGRADE-6",
        item_description="Control panel upgrade tied to milestone acceptance",
        quantity=6,
        target_price=1420.0,
        terms={
            "milestone_id": "HELIO-M2-ACCEPT",
            "payment_stage": "post_acceptance_40pct",
            "acceptance_date": "2026-07-18",
        },
        buyer_file_title="Milestone Purchase Request",
        seller_file_title="Summit Milestone Sales Policy",
        approver_file_title="Project Milestone Approval Policy",
    ),
)

BARGAINING_CM_TASK_SEEDS: tuple[BargainingTaskSeed, ...] = (
    _terms_seed(
        task_index=0,
        source_task_id="owned-ecosystem-competitive-priority-inventory-0",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_priority_inventory_v0",
        transaction_id="TXN-CM-OE-200",
        resource_profile="owned_ecosystem_competitive_priority_inventory",
        buyer_id="forgeworks_buyer",
        seller_id="rivalis_seller",
        approver_id="forgeworks_finance_approver",
        buyer_owner="forgeworks_procurement",
        seller_owner="rivalis_sales",
        approver_owner="forgeworks_finance",
        item_id="CNC-SENSOR-PACK-10",
        item_description="CNC sensor packs with scarce priority inventory",
        quantity=10,
        target_price=890.0,
        terms={
            "allocation_id": "RIVALIS-ALLOC-200",
            "delivery_date": "2026-06-29",
            "priority_code": "forgeworks-critical",
        },
        buyer_file_title="Competitive Priority Inventory Request",
        seller_file_title="Rivalis Priority Allocation Policy",
        approver_file_title="Finance Priority Purchase Policy",
    ),
    _terms_seed(
        task_index=1,
        source_task_id="owned-ecosystem-competitive-dual-sourcing-1",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_dual_sourcing_v1",
        transaction_id="TXN-CM-OE-201",
        resource_profile="owned_ecosystem_competitive_dual_sourcing",
        buyer_id="marlow_buyer",
        seller_id="caldera_seller",
        approver_id="marlow_sourcing_approver",
        buyer_owner="marlow_procurement",
        seller_owner="caldera_components_sales",
        approver_owner="marlow_sourcing",
        item_id="BATTERY-MODULE-22",
        item_description="Battery modules under a dual-sourcing award rule",
        quantity=22,
        target_price=510.0,
        terms={
            "source_lot_id": "CALDERA-LOT-201",
            "vendor_rank": "secondary_award",
            "approval_basis": "dual_source_resilience",
        },
        buyer_file_title="Dual-Sourcing Purchase Request",
        seller_file_title="Caldera Award-Share Sales Policy",
        approver_file_title="Strategic Sourcing Approval Policy",
    ),
    _terms_seed(
        task_index=2,
        source_task_id="owned-ecosystem-competitive-rebate-terms-2",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_rebate_terms_v2",
        transaction_id="TXN-CM-OE-202",
        resource_profile="owned_ecosystem_competitive_rebate_terms",
        buyer_id="seabright_buyer",
        seller_id="canyon_seller",
        approver_id="seabright_finance_approver",
        buyer_owner="seabright_procurement",
        seller_owner="canyon_industrial_sales",
        approver_owner="seabright_finance",
        item_id="FLEET-CHARGER-14",
        item_description="Fleet charger units with contested rebate terms",
        quantity=14,
        target_price=760.0,
        terms={
            "rebate_id": "CANYON-REBATE-Q3",
            "net_price_basis": "post_rebate_net30",
            "volume_commitment": "14_units_no_rollover",
        },
        buyer_file_title="Rebate Terms Purchase Request",
        seller_file_title="Canyon Rebate Sales Policy",
        approver_file_title="Finance Rebate Approval Policy",
    ),
    _terms_seed(
        task_index=3,
        source_task_id="owned-ecosystem-competitive-expiring-quote-3",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_expiring_quote_v3",
        transaction_id="TXN-CM-OE-203",
        resource_profile="owned_ecosystem_competitive_expiring_quote",
        buyer_id="talon_buyer",
        seller_id="brightline_seller",
        approver_id="talon_finance_approver",
        buyer_owner="talon_procurement",
        seller_owner="brightline_sales",
        approver_owner="talon_finance",
        item_id="SAFETY-LIGHT-BAR-28",
        item_description="Safety light bars with an expiring negotiated quote",
        quantity=28,
        target_price=185.0,
        terms={
            "quote_id": "BL-QUOTE-203",
            "quote_expiry": "2026-06-17T17:00:00Z",
            "price_lock": "firm_until_expiry",
        },
        buyer_file_title="Expiring Quote Purchase Request",
        seller_file_title="Brightline Quote-Hold Sales Policy",
        approver_file_title="Quote Exception Approval Policy",
    ),
    _terms_seed(
        task_index=4,
        source_task_id="owned-ecosystem-competitive-substitute-close-4",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_substitute_close_v4",
        transaction_id="TXN-CM-OE-204",
        resource_profile="owned_ecosystem_competitive_substitute_close",
        buyer_id="ashford_buyer",
        seller_id="medora_seller",
        approver_id="ashford_quality_approver",
        buyer_owner="ashford_procurement",
        seller_owner="medora_health_sales",
        approver_owner="ashford_quality",
        item_id="STERILE-KIT-60",
        item_description="Sterile kit order where seller offers a substitute SKU",
        quantity=60,
        target_price=42.0,
        terms={
            "substitute_item_id": "STERILE-KIT-60R",
            "equivalency_class": "regulatory_equivalent",
            "exception_id": "ASH-QA-204",
        },
        buyer_file_title="Competitive Substitute Purchase Request",
        seller_file_title="Medora Substitute Sales Policy",
        approver_file_title="Quality Substitute Approval Policy",
    ),
    _terms_seed(
        task_index=5,
        source_task_id="owned-ecosystem-competitive-escrow-5",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_escrow_purchase_v5",
        transaction_id="TXN-CM-OE-205",
        resource_profile="owned_ecosystem_competitive_escrow_purchase",
        buyer_id="granite_buyer",
        seller_id="optima_seller",
        approver_id="granite_treasury_approver",
        buyer_owner="granite_procurement",
        seller_owner="optima_robotics_sales",
        approver_owner="granite_treasury",
        item_id="ROBOT-END-EFFECTOR-8",
        item_description="Robot end effectors with escrowed release after inspection",
        quantity=8,
        target_price=1320.0,
        terms={
            "escrow_id": "GRANITE-ESCROW-205",
            "release_condition": "incoming_inspection_pass",
            "inspection_date": "2026-07-02",
        },
        buyer_file_title="Escrow Purchase Request",
        seller_file_title="Optima Escrow Sales Policy",
        approver_file_title="Treasury Escrow Approval Policy",
    ),
    _terms_seed(
        task_index=6,
        source_task_id="owned-ecosystem-competitive-production-slot-6",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_production_slot_v6",
        transaction_id="TXN-CM-OE-206",
        resource_profile="owned_ecosystem_competitive_production_slot",
        buyer_id="vesta_buyer",
        seller_id="monarch_seller",
        approver_id="vesta_capacity_approver",
        buyer_owner="vesta_procurement",
        seller_owner="monarch_components_sales",
        approver_owner="vesta_capacity_planning",
        item_id="CUSTOM-VALVE-12",
        item_description="Custom valve batch tied to an exclusive production slot",
        quantity=12,
        target_price=640.0,
        terms={
            "production_slot_id": "MONARCH-SLOT-206",
            "slot_date": "2026-07-09",
            "capacity_commitment": "exclusive_half_day_run",
        },
        buyer_file_title="Production Slot Purchase Request",
        seller_file_title="Monarch Production Slot Policy",
        approver_file_title="Capacity Commitment Approval Policy",
    ),
    _terms_seed(
        task_index=7,
        source_task_id="owned-ecosystem-competitive-brokered-shortage-7",
        difficulty_label="high",
        scenario_id="marble_bargaining_competitive_brokered_shortage_v7",
        transaction_id="TXN-CM-OE-207",
        resource_profile="owned_ecosystem_competitive_brokered_shortage",
        buyer_id="altair_buyer",
        seller_id="novus_seller",
        approver_id="altair_broker_approver",
        buyer_owner="altair_procurement",
        seller_owner="novus_supply_sales",
        approver_owner="altair_broker_review",
        item_id="NETWORK-SWITCH-18",
        item_description="Network switches in shortage routed through broker review",
        quantity=18,
        target_price=430.0,
        terms={
            "broker_id": "ALT-NOVUS-BROKER-207",
            "commission_rate": "0.028",
            "broker_authorization_id": "ALT-AUTH-207",
        },
        buyer_file_title="Brokered Shortage Purchase Request",
        seller_file_title="Novus Brokered Shortage Policy",
        approver_file_title="Broker Authorization Approval Policy",
    ),
    _terms_seed(
        task_index=8,
        source_task_id="owned-ecosystem-competitive-warranty-tradeoff-8",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_warranty_tradeoff_v8",
        transaction_id="TXN-CM-OE-208",
        resource_profile="owned_ecosystem_competitive_warranty_tradeoff",
        buyer_id="kestrel_buyer",
        seller_id="orion_seller",
        approver_id="kestrel_legal_approver",
        buyer_owner="kestrel_procurement",
        seller_owner="orion_field_sales",
        approver_owner="kestrel_legal",
        item_id="FIELD-METER-24",
        item_description="Field meters with warranty and service-credit tradeoffs",
        quantity=24,
        target_price=255.0,
        terms={
            "warranty_months_ext": "36",
            "service_tier": "advance_replacement",
            "credit_schedule": "field_meter_credit_v2",
        },
        buyer_file_title="Warranty Tradeoff Purchase Request",
        seller_file_title="Orion Warranty Sales Policy",
        approver_file_title="Legal Warranty Approval Policy",
    ),
    _terms_seed(
        task_index=9,
        source_task_id="owned-ecosystem-competitive-compliance-hold-9",
        difficulty_label="high",
        scenario_id="marble_bargaining_competitive_compliance_hold_v9",
        transaction_id="TXN-CM-OE-209",
        resource_profile="owned_ecosystem_competitive_compliance_hold",
        buyer_id="mariner_buyer",
        seller_id="axis_seller",
        approver_id="mariner_compliance_approver",
        buyer_owner="mariner_procurement",
        seller_owner="axis_control_sales",
        approver_owner="mariner_compliance",
        item_id="ACCESS-CONTROL-PANEL-9",
        item_description="Access control panels under compliance release hold",
        quantity=9,
        target_price=1180.0,
        terms={
            "hold_release_id": "MARINER-HOLD-209",
            "compliance_status": "release_after_screening",
            "release_date": "2026-07-06",
        },
        buyer_file_title="Compliance Hold Purchase Request",
        seller_file_title="Axis Hold-Release Sales Policy",
        approver_file_title="Compliance Hold Approval Policy",
    ),
    _terms_seed(
        task_index=10,
        source_task_id="owned-ecosystem-competitive-renewal-uplift-10",
        difficulty_label="medium_high",
        scenario_id="marble_bargaining_competitive_renewal_uplift_v10",
        transaction_id="TXN-CM-OE-210",
        resource_profile="owned_ecosystem_competitive_renewal_uplift",
        buyer_id="quartz_buyer",
        seller_id="nimbus_seller",
        approver_id="quartz_vendor_approver",
        buyer_owner="quartz_it_procurement",
        seller_owner="nimbus_platform_sales",
        approver_owner="quartz_vendor_management",
        item_id="PLATFORM-SEAT-ADDON-32",
        item_description="Platform seat add-on with contested renewal uplift",
        quantity=32,
        target_price=96.0,
        terms={
            "prior_contract_id": "NIMBUS-QUARTZ-2025",
            "support_tier": "business_plus",
            "coterm_end_date": "2027-01-31",
        },
        buyer_file_title="Renewal Uplift Purchase Request",
        seller_file_title="Nimbus Renewal Uplift Policy",
        approver_file_title="Vendor Renewal Approval Policy",
    ),
    _terms_seed(
        task_index=11,
        source_task_id="owned-ecosystem-competitive-staged-milestone-11",
        difficulty_label="high",
        scenario_id="marble_bargaining_competitive_staged_milestone_v11",
        transaction_id="TXN-CM-OE-211",
        resource_profile="owned_ecosystem_competitive_staged_milestone",
        buyer_id="redwood_buyer",
        seller_id="apollo_seller",
        approver_id="redwood_pm_approver",
        buyer_owner="redwood_projects",
        seller_owner="apollo_controls_sales",
        approver_owner="redwood_pm_approval",
        item_id="LINE-INTEGRATION-KIT-5",
        item_description="Line integration kit tied to staged milestone acceptance",
        quantity=5,
        target_price=1760.0,
        terms={
            "milestone_id": "REDWOOD-LINE-M3",
            "payment_stage": "30pct_after_site_acceptance",
            "acceptance_date": "2026-07-28",
        },
        buyer_file_title="Competitive Milestone Purchase Request",
        seller_file_title="Apollo Milestone Sales Policy",
        approver_file_title="Project Milestone Approval Policy",
    ),
)

BARGAINING_TASK_SEEDS: tuple[BargainingTaskSeed, ...] = (
    *BARGAINING_CU_TASK_SEEDS,
    *BARGAINING_CM_TASK_SEEDS,
)


def bargaining_task_seeds_for_cell(
    cell_id: str | None,
) -> tuple[BargainingTaskSeed, ...]:
    if cell_id == "CU-A-marble_bargaining":
        return BARGAINING_CU_TASK_SEEDS
    if cell_id == "CM-A-marble_bargaining":
        return BARGAINING_CM_TASK_SEEDS
    return BARGAINING_TASK_SEEDS


__all__ = [
    "BARGAINING_CM_TASK_SEEDS",
    "BARGAINING_CU_TASK_SEEDS",
    "BARGAINING_TASK_SEEDS",
    "BargainingTaskSeed",
    "OwnerWorkspaceSeed",
    "WorkspaceFileSeed",
    "WorkspaceTableSeed",
    "bargaining_task_seeds_for_cell",
]
