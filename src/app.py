"""
Flask application serving the GraphQL API.

``create_app`` is a factory: gunicorn calls it with ``"app:create_app()"``
and tests call it with a ``CloudManager`` built from fake providers, so
importing this module never reads the config file or touches a cloud SDK.
"""

from flask import Flask, jsonify
from flask_graphql import GraphQLView

from cloud_manager import build_manager
from graphql_schema import schema


def create_app(manager=None):
    """Build the Flask app around ``manager`` (or one built from config)."""
    if manager is None:
        manager = build_manager()

    app = Flask(__name__)
    app.add_url_rule(
        '/graphql',
        view_func=GraphQLView.as_view(
            'graphql', schema=schema, graphiql=True, root_value=manager),
    )

    @app.route('/healthz')
    def healthz():
        return jsonify(status='ok', providers=manager.provider_names())

    return app
