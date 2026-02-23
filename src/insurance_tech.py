#!/usr/bin/env python3
"""BlackRoad Insurance Tech - Production Module.

Policy management, claims processing, and actuarial premium calculation
with persistent SQLite storage and colorized CLI output.
"""

import argparse
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

RED     = "\033[0;31m"
GREEN   = "\033[0;32m"
YELLOW  = "\033[1;33m"
CYAN    = "\033[0;36m"
BLUE    = "\033[0;34m"
MAGENTA = "\033[0;35m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
NC      = "\033[0m"

DB_PATH = Path.home() / ".blackroad" / "insurance_tech.db"

# Actuarial base rates by policy type (annual rate as fraction of coverage)
RISK_TABLE = {
    "life":     0.0015,
    "health":   0.0250,
    "auto":     0.0180,
    "home":     0.0120,
    "business": 0.0200,
    "travel":   0.0300,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Policy:
    holder_name: str
    policy_type: str       # life | health | auto | home | business | travel
    coverage_amount: float
    annual_premium: float
    start_date: str
    end_date: str
    status: str = "active"  # active | lapsed | cancelled | expired
    created_at: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class Claim:
    policy_id: int
    claimant: str
    incident_date: str
    claim_amount: float
    description: str
    status: str = "pending"   # pending | approved | denied | paid
    adjuster: str = "auto"
    approved_amount: float = 0.0
    filed_at: str = ""
    id: Optional[int] = None

    def __post_init__(self):
        if not self.filed_at:
            self.filed_at = datetime.now().isoformat()


@dataclass
class PremiumCalculation:
    policy_type: str
    coverage_amount: float
    risk_score: float
    base_rate: float
    risk_multiplier: float
    annual_premium: float
    monthly_premium: float
    daily_rate: float
    breakdown: dict


# ---------------------------------------------------------------------------
# Database / Business Logic
# ---------------------------------------------------------------------------

class InsuranceTechManager:
    """Production insurance policy management with SQLite persistence."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS policies (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    holder_name     TEXT NOT NULL,
                    policy_type     TEXT NOT NULL,
                    coverage_amount REAL NOT NULL,
                    annual_premium  REAL NOT NULL,
                    start_date      TEXT NOT NULL,
                    end_date        TEXT NOT NULL,
                    status          TEXT DEFAULT 'active',
                    created_at      TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS claims (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    policy_id       INTEGER NOT NULL,
                    claimant        TEXT NOT NULL,
                    incident_date   TEXT NOT NULL,
                    claim_amount    REAL NOT NULL,
                    description     TEXT NOT NULL,
                    status          TEXT DEFAULT 'pending',
                    adjuster        TEXT DEFAULT 'auto',
                    approved_amount REAL DEFAULT 0.0,
                    filed_at        TEXT NOT NULL,
                    FOREIGN KEY (policy_id) REFERENCES policies(id)
                );
                CREATE INDEX IF NOT EXISTS idx_claims_policy ON claims(policy_id);
                CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status);
            """)

    def create_policy(self, holder: str, policy_type: str, coverage: float,
                      start: str, end: str, risk_score: float = 5.0) -> Policy:
        """Create a new insurance policy with auto-calculated premium."""
        calc = self.calculate_premium(policy_type, coverage, risk_score)
        pol = Policy(holder_name=holder, policy_type=policy_type,
                     coverage_amount=coverage, annual_premium=calc.annual_premium,
                     start_date=start, end_date=end)
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO policies (holder_name, policy_type, coverage_amount, "
                "annual_premium, start_date, end_date, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (pol.holder_name, pol.policy_type, pol.coverage_amount,
                 pol.annual_premium, pol.start_date, pol.end_date,
                 pol.status, pol.created_at)
            )
            pol.id = cur.lastrowid
        return pol

    def list_policies(self, status: Optional[str] = None,
                      policy_type: Optional[str] = None) -> List[dict]:
        """List policies with optional status / type filter."""
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if policy_type:
            clauses.append("policy_type = ?"); params.append(policy_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM policies {where} ORDER BY created_at DESC", params
            ).fetchall()
        return [dict(r) for r in rows]

    def file_claim(self, policy_id: int, claimant: str, incident_date: str,
                   amount: float, description: str) -> Claim:
        """File a new insurance claim against a policy."""
        claim = Claim(policy_id=policy_id, claimant=claimant,
                      incident_date=incident_date, claim_amount=amount,
                      description=description)
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO claims (policy_id, claimant, incident_date, "
                "claim_amount, description, status, adjuster, approved_amount, filed_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (claim.policy_id, claim.claimant, claim.incident_date,
                 claim.claim_amount, claim.description, claim.status,
                 claim.adjuster, claim.approved_amount, claim.filed_at)
            )
            claim.id = cur.lastrowid
        return claim

    def calculate_premium(self, policy_type: str, coverage: float,
                          risk_score: float = 5.0) -> PremiumCalculation:
        """Calculate insurance premium using actuarial risk model."""
        base_rate = RISK_TABLE.get(policy_type.lower(), 0.02)
        # Risk multiplier: score 1-10 maps to 0.5x – 2.0x
        risk_mult = max(0.5, min(2.0, 1.0 + (risk_score - 5.0) * 0.15))
        effective_rate = base_rate * risk_mult
        annual = round(coverage * effective_rate, 2)
        return PremiumCalculation(
            policy_type=policy_type,
            coverage_amount=coverage,
            risk_score=risk_score,
            base_rate=base_rate,
            risk_multiplier=risk_mult,
            annual_premium=annual,
            monthly_premium=round(annual / 12.0, 2),
            daily_rate=round(annual / 365.0, 4),
            breakdown={
                "base_rate_pct":      f"{base_rate * 100:.4f}%",
                "risk_multiplier":    f"{risk_mult:.3f}x",
                "effective_rate_pct": f"{effective_rate * 100:.4f}%",
            },
        )

    def get_summary(self) -> dict:
        """Aggregate insurance portfolio statistics."""
        with self._conn() as conn:
            total_p  = conn.execute("SELECT COUNT(*) FROM policies").fetchone()[0]
            active_p = conn.execute(
                "SELECT COUNT(*) FROM policies WHERE status='active'"
            ).fetchone()[0]
            coverage = conn.execute(
                "SELECT COALESCE(SUM(coverage_amount),0) FROM policies WHERE status='active'"
            ).fetchone()[0]
            premium  = conn.execute(
                "SELECT COALESCE(SUM(annual_premium),0) FROM policies WHERE status='active'"
            ).fetchone()[0]
            total_c  = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
            pending  = conn.execute(
                "SELECT COUNT(*) FROM claims WHERE status='pending'"
            ).fetchone()[0]
            paid_out = conn.execute(
                "SELECT COALESCE(SUM(approved_amount),0) FROM claims WHERE status='paid'"
            ).fetchone()[0]
        return {
            "total_policies":        total_p,
            "active_policies":       active_p,
            "total_coverage":        f"${coverage:,.2f}",
            "annual_premium_income": f"${premium:,.2f}",
            "total_claims":          total_c,
            "pending_claims":        pending,
            "total_claims_paid":     f"${paid_out:,.2f}",
            "loss_ratio":            f"{paid_out / premium * 100:.1f}%" if premium else "N/A",
        }

    def export_report(self, output_path: str = "insurance_report.json") -> str:
        """Export full portfolio report to JSON."""
        with self._conn() as conn:
            claims = [dict(r) for r in conn.execute(
                "SELECT * FROM claims ORDER BY filed_at DESC"
            ).fetchall()]
        data = {
            "exported_at": datetime.now().isoformat(),
            "generator":   "BlackRoad Insurance Tech v1.0",
            "summary":     self.get_summary(),
            "policies":    self.list_policies(),
            "claims":      claims,
        }
        Path(output_path).write_text(json.dumps(data, indent=2))
        return output_path


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _header(title: str):
    w = 64
    print(f"\n{BOLD}{BLUE}{'━' * w}{NC}")
    print(f"{BOLD}{BLUE}  {title}{NC}")
    print(f"{BOLD}{BLUE}{'━' * w}{NC}")


def _status_badge(status: str) -> str:
    c = {"active": GREEN, "lapsed": YELLOW, "cancelled": RED, "expired": DIM,
         "pending": YELLOW, "approved": GREEN, "denied": RED, "paid": CYAN
         }.get(status.lower(), NC)
    return f"{c}{status}{NC}"


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_list(args, mgr: InsuranceTechManager):
    policies = mgr.list_policies(
        status=getattr(args, "status", None),
        policy_type=getattr(args, "type_", None),
    )
    _header("INSURANCE TECH — Policy Portfolio")
    if not policies:
        print(f"  {YELLOW}No policies found.{NC}\n")
        return
    for p in policies:
        print(f"  {CYAN}#{p['id']:04d}{NC}  {BOLD}{p['holder_name']:<22}{NC} "
              f"[{MAGENTA}{p['policy_type'].upper()}{NC}]")
        print(f"        Coverage: {GREEN}${p['coverage_amount']:>14,.2f}{NC}   "
              f"Premium: {YELLOW}${p['annual_premium']:>10,.2f}/yr{NC}")
        print(f"        {p['start_date']} → {p['end_date']}   "
              f"Status: {_status_badge(p['status'])}")
        print()


def cmd_add(args, mgr: InsuranceTechManager):
    pol = mgr.create_policy(args.holder, args.type_, args.coverage,
                            args.start, args.end,
                            risk_score=getattr(args, "risk", 5.0))
    print(f"\n{GREEN}✓ Policy created{NC}")
    print(f"  {BOLD}Policy ID:{NC}       {pol.id}")
    print(f"  {BOLD}Holder:{NC}          {pol.holder_name}")
    print(f"  {BOLD}Type:{NC}            {pol.policy_type}")
    print(f"  {BOLD}Coverage:{NC}        ${pol.coverage_amount:,.2f}")
    print(f"  {BOLD}Annual Premium:{NC}  ${pol.annual_premium:,.2f}\n")


def cmd_premium(args, mgr: InsuranceTechManager):
    calc = mgr.calculate_premium(args.type_, args.coverage,
                                 getattr(args, "risk", 5.0))
    _header("PREMIUM CALCULATION")
    print(f"  {DIM}Policy Type:{NC}       {BOLD}{calc.policy_type.upper()}{NC}")
    print(f"  {DIM}Coverage Amount:{NC}   {GREEN}${calc.coverage_amount:,.2f}{NC}")
    print(f"  {DIM}Risk Score:{NC}        {calc.risk_score}/10")
    print(f"  {DIM}Base Rate:{NC}         {calc.breakdown['base_rate_pct']}")
    print(f"  {DIM}Risk Multiplier:{NC}   {calc.breakdown['risk_multiplier']}")
    print(f"  {DIM}Effective Rate:{NC}    {calc.breakdown['effective_rate_pct']}")
    print(f"  {DIM}Annual Premium:{NC}    {BOLD}{YELLOW}${calc.annual_premium:,.2f}{NC}")
    print(f"  {DIM}Monthly Premium:{NC}   ${calc.monthly_premium:,.2f}")
    print(f"  {DIM}Daily Rate:{NC}        ${calc.daily_rate:.4f}\n")


def cmd_claim(args, mgr: InsuranceTechManager):
    claim = mgr.file_claim(args.policy_id, args.claimant, args.incident,
                           args.amount, args.description)
    print(f"\n{CYAN}✓ Claim filed{NC}")
    print(f"  {BOLD}Claim ID:{NC}     {claim.id}")
    print(f"  {BOLD}Policy ID:{NC}    {claim.policy_id}")
    print(f"  {BOLD}Claimant:{NC}     {claim.claimant}")
    print(f"  {BOLD}Amount:{NC}       ${claim.claim_amount:,.2f}")
    print(f"  {BOLD}Status:{NC}       {_status_badge(claim.status)}\n")


def cmd_status(args, mgr: InsuranceTechManager):
    s = mgr.get_summary()
    _header("INSURANCE PORTFOLIO SUMMARY")
    for key, val in s.items():
        label = key.replace("_", " ").title()
        print(f"  {DIM}{label:<28}{NC}  {BOLD}{val}{NC}")
    print()


def cmd_export(args, mgr: InsuranceTechManager):
    path = mgr.export_report(args.output)
    print(f"\n{GREEN}✓ Report exported to:{NC} {BOLD}{path}{NC}\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mgr = InsuranceTechManager()
    parser = argparse.ArgumentParser(
        prog="insurance-tech",
        description=f"{BOLD}BlackRoad Insurance Tech Manager{NC}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s add --holder 'Jane Doe' --type health "
            "--coverage 500000 --start 2024-01-01 --end 2024-12-31\n"
            "  %(prog)s premium --type auto --coverage 30000 --risk 6.5\n"
            "  %(prog)s status\n"
        ),
    )
    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    p = subs.add_parser("list", help="List insurance policies")
    p.add_argument("--status", choices=["active", "lapsed", "cancelled", "expired"])
    p.add_argument("--type", dest="type_", choices=list(RISK_TABLE.keys()))

    p = subs.add_parser("add", help="Create a new policy")
    p.add_argument("--holder",   required=True, metavar="NAME")
    p.add_argument("--type",     dest="type_", required=True,
                   choices=list(RISK_TABLE.keys()))
    p.add_argument("--coverage", required=True, type=float, metavar="AMOUNT")
    p.add_argument("--start",    required=True, metavar="YYYY-MM-DD")
    p.add_argument("--end",      required=True, metavar="YYYY-MM-DD")
    p.add_argument("--risk",     default=5.0,   type=float, metavar="1-10")

    p = subs.add_parser("premium", help="Calculate premium for a policy type")
    p.add_argument("--type",     dest="type_", required=True,
                   choices=list(RISK_TABLE.keys()))
    p.add_argument("--coverage", required=True, type=float, metavar="AMOUNT")
    p.add_argument("--risk",     default=5.0,   type=float, metavar="1-10")

    p = subs.add_parser("claim", help="File a claim against a policy")
    p.add_argument("--policy-id",   dest="policy_id", required=True, type=int)
    p.add_argument("--claimant",    required=True)
    p.add_argument("--incident",    required=True, metavar="YYYY-MM-DD")
    p.add_argument("--amount",      required=True, type=float)
    p.add_argument("--description", required=True)

    subs.add_parser("status", help="Show portfolio summary")

    p = subs.add_parser("export", help="Export portfolio report")
    p.add_argument("--output", default="insurance_report.json", metavar="FILE")

    args = parser.parse_args()
    {"list": cmd_list, "add": cmd_add, "premium": cmd_premium,
     "claim": cmd_claim, "status": cmd_status, "export": cmd_export
     }[args.command](args, mgr)


if __name__ == "__main__":
    main()
