import os

from flask import Blueprint as _BP
from sqlalchemy import inspect, text

from CTFd.plugins import (
    register_admin_plugin_menu_bar,
    register_plugin_script,
    register_plugin_stylesheet,
    register_user_page_menu_bar,
)

from .models import *  # noqa: F401,F403 — registers all models with SQLAlchemy


def _migrate_db(app):
    inspector = inspect(app.db.engine)

    if "atr26_weapons" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("atr26_weapons")}
        migrations = []
        if "hint_text" not in existing:
            migrations.append('ALTER TABLE atr26_weapons ADD COLUMN hint_text TEXT DEFAULT ""')
        if "min_damage" not in existing:
            migrations.append("ALTER TABLE atr26_weapons ADD COLUMN min_damage INT DEFAULT 0")
        if "max_damage" not in existing:
            migrations.append("ALTER TABLE atr26_weapons ADD COLUMN max_damage INT DEFAULT 0")
        for stmt in migrations:
            app.db.session.execute(text(stmt))
        if migrations:
            app.db.session.commit()

    if "atr26_team_inventory" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("atr26_team_inventory")}
        if "rolled_damage" not in existing:
            app.db.session.execute(
                text("ALTER TABLE atr26_team_inventory ADD COLUMN rolled_damage INT DEFAULT NULL")
            )
            app.db.session.commit()


def load(app):
    app.db.create_all()
    _migrate_db(app)

    @app.before_request
    def _block_attempt_if_unclaimed():
        from flask import jsonify, request
        if request.method != "POST" or not request.path.startswith("/api/v1/challenges/attempt"):
            return
        from CTFd.utils.user import get_current_user
        from CTFd.utils.decorators import authed_only  # noqa — just check session directly
        try:
            user = get_current_user()
        except Exception:
            return
        if not user:
            return
        team = user.team
        if not team:
            return
        from .models import PendingCardOffer
        unclaimed = PendingCardOffer.query.filter_by(team_id=team.id, selected=False).first()
        if unclaimed:
            return jsonify({
                "success": True,
                "data": {
                    "status": "error",
                    "message": "You have an unclaimed weapon! Claim it from your previous solve before attempting another challenge.",
                },
            }), 200

    _assets_bp = _BP(
        "atr26_game_static",
        __name__,
        static_folder=os.path.join(os.path.dirname(__file__), "assets"),
        static_url_path="/plugins/atr26_game/assets",
    )
    app.register_blueprint(_assets_bp)

    register_plugin_script("/plugins/atr26_game/assets/js/card-select.js")
    register_plugin_stylesheet("/plugins/atr26_game/assets/css/atr26-game.css")

    register_user_page_menu_bar("Inventory", "/atr26_game/inventory")
    register_user_page_menu_bar("Loadout", "/atr26_game/loadout")

    register_admin_plugin_menu_bar("ATR26 Game", "/atr26_game/admin/weapons")

    from .blueprints.admin import admin_bp
    from .blueprints.api import api_bp
    from .blueprints.pages import pages_bp
    from .hooks import register_solve_loot_hooks
    register_solve_loot_hooks()

    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(pages_bp)
