"""SQLAlchemy hooks: create PendingCardOffer when a new Solve is committed."""

from sqlalchemy import event
from sqlalchemy.orm import Session


def register_solve_loot_hooks():
    @event.listens_for(Session, "before_flush")
    def _collect_new_solves(session, flush_context, instances=None):
        from CTFd.models import Solves

        batch = [obj for obj in session.new if isinstance(obj, Solves)]
        if batch:
            session.info["_atr26_pending_solves"] = (
                session.info.get("_atr26_pending_solves", []) + batch
            )

    @event.listens_for(Session, "after_flush")
    def _emit_pending_offers(session, flush_context):
        from CTFd.models import Solves

        pending = session.info.pop("_atr26_pending_solves", None)
        if not pending:
            return

        from .blueprints.api import LOOT_TIER_WEIGHTS, _challenge_tier, _pick_by_rarity
        from .models import PendingCardOffer, Weapon

        for solve in pending:
            if not isinstance(solve, Solves) or solve.id is None:
                continue
            if not solve.team_id:
                continue

            # Skip if an offer already exists for this solve's challenge+team
            exists = session.query(PendingCardOffer).filter_by(
                team_id=solve.team_id, challenge_id=solve.challenge_id
            ).first()
            if exists:
                continue

            from CTFd.models import Challenges, Tags
            challenge = session.query(Challenges).get(solve.challenge_id)
            tag_values = {
                t.value.lower()
                for t in session.query(Tags).filter_by(challenge_id=solve.challenge_id).all()
            }

            tier = _challenge_tier(challenge, tag_values)
            if tier is None:
                continue

            weapons = session.query(Weapon).all()
            if len(weapons) < 2:
                continue

            weapon_a, weapon_b = _pick_by_rarity(weapons, tier)
            if weapon_a is None or weapon_b is None:
                continue

            offer = PendingCardOffer(
                team_id=solve.team_id,
                challenge_id=solve.challenge_id,
                weapon_id_a=weapon_a.id,
                weapon_id_b=weapon_b.id,
            )
            session.add(offer)
