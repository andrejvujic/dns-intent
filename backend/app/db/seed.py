from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    DEFAULT_DOMAIN_RECORD_TYPES,
    Domain,
    DomainRecord,
    DomainRecordType,
    User,
    UserDomain,
)

"""
cd backend

# Kreiranje tabela i seed
python -m scripts.seed_database

# Brisanje svih tabela
python -m scripts.drop_database

# Drop + create + seed
python -m scripts.reset_database
"""


SEED_PASSWORD = "DnsIntent2026!"

SEED_USERS = (
    {
        "first_name": "Ana",
        "last_name": "Jovanović",
        "username": "ana.jovanovic",
        "email": "ana.jovanovic@dnsintent.test",
    },
    {
        "first_name": "Marko",
        "last_name": "Petrović",
        "username": "marko.petrovic",
        "email": "marko.petrovic@dnsintent.test",
    },
    {
        "first_name": "Jelena",
        "last_name": "Nikolić",
        "username": "jelena.nikolic",
        "email": "jelena.nikolic@dnsintent.test",
    },
    {
        "first_name": "Nikola",
        "last_name": "Stojanović",
        "username": "nikola.stojanovic",
        "email": "nikola.stojanovic@dnsintent.test",
    },
    {
        "first_name": "Milica",
        "last_name": "Ilić",
        "username": "milica.ilic",
        "email": "milica.ilic@dnsintent.test",
    },
)


def seed_database(session: Session) -> None:
    user_count = session.scalar(select(func.count()).select_from(User)) or 0
    domain_count = session.scalar(select(func.count()).select_from(Domain)) or 0
    if user_count or domain_count:
        raise RuntimeError(
            "Seed requires empty users and domains tables. Run the reset script first."
        )

    record_types = {
        name: DomainRecordType(name=name) for name in DEFAULT_DOMAIN_RECORD_TYPES
    }
    session.add_all(record_types.values())

    users: list[User] = []
    for data in SEED_USERS:
        user = User(
            first_name=data["first_name"],
            last_name=data["last_name"],
            username=data["username"],
            email=data["email"],
            password_hash=hash_password(SEED_PASSWORD),
        )
        users.append(user)

    domain = Domain(
        name="dnsintent.test",
        description="Razvojni domen za demonstraciju upravljanja DNS zapisima",
        registrar="Development Registrar",
    )

    for user in users:
        domain.user_memberships.append(UserDomain(user=user))

    domain.records.extend(
        [
            DomainRecord(
                record_type=record_types["A"],
                value={"name": "@", "address": "192.0.2.10", "ttl": 3600},
            ),
            DomainRecord(
                record_type=record_types["A"],
                value={"name": "www", "address": "192.0.2.20", "ttl": 3600},
            ),
            DomainRecord(
                record_type=record_types["MX"],
                value={
                    "name": "@",
                    "exchange": "mail.dnsintent.test",
                    "priority": 10,
                    "ttl": 3600,
                },
            ),
            DomainRecord(
                record_type=record_types["NS"],
                value={"name": "@", "host": "ns1.dnsintent.test", "ttl": 86400},
            ),
            DomainRecord(
                record_type=record_types["NS"],
                value={"name": "@", "host": "ns2.dnsintent.test", "ttl": 86400},
            ),
        ]
    )

    session.add_all(users)
    session.add(domain)
    session.commit()
