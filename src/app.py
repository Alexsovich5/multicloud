"""
Flask application serving the GraphQL API.

``create_app`` is a factory: gunicorn calls it with ``"app:create_app()"``
and tests call it with a ``CloudManager`` built from fake providers, so
importing this module never reads the config file or touches a cloud SDK.

Every GraphQL request needs ``Authorization: Bearer <API key>`` (see
``auth``); POSTs must be ``application/json``, so a cross-site HTML form
cannot reach a mutation. Browsers asking for HTML get a static GraphiQL
page that runs no query. ``/healthz`` stays open for liveness probes.
"""

import json
import logging

from flask import Flask, Response, jsonify, request
from flask_graphql import GraphQLView
from graphql.error import GraphQLError
from graphql.error import format_error as default_format_error

from auth import key_matches, load_api_key
from cloud_manager import build_manager
from graphiql_page import PAGE as GRAPHIQL_PAGE
from graphql_schema import schema
from providers.base import InstanceNotFound, RequestError

logger = logging.getLogger('app')

# Resolver errors whose message is meant for the caller (unknown provider,
# bad name, unknown instance). Anything else, including plain ValueError and
# KeyError raised inside an SDK, is reported as an internal error.
EXPOSED_ERRORS = (RequestError, InstanceNotFound, GraphQLError)
INTERNAL_ERROR = 'Internal server error'

# graphql-core logs every resolver exception with its full text and
# traceback, which can carry endpoint URLs with credentials or tokens.
GRAPHQL_LOGGERS = ('graphql.execution.executor', 'graphql.execution.utils',
                   'graphql.errors')


class WithholdErrorDetails(logging.Filter):
    """Strip exception text and tracebacks from graphql-core log records.

    The executor's own message only names the field and is kept; records
    whose message is a formatted traceback are replaced. ``safe_format_error``
    still logs the exception type and path under the ``app`` logger.
    """

    def filter(self, record):
        if record.name != 'graphql.execution.executor':
            record.msg = 'GraphQL error (details withheld)'
            record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def _install_log_filter():
    for name in GRAPHQL_LOGGERS:
        target = logging.getLogger(name)
        if not any(isinstance(f, WithholdErrorDetails) for f in target.filters):
            target.addFilter(WithholdErrorDetails())


def safe_format_error(error):
    """Format a GraphQL error without leaking unexpected exception text."""
    formatted = default_format_error(error)
    original = getattr(error, 'original_error', None)
    if original is not None and not isinstance(original, EXPOSED_ERRORS):
        logger.error('GraphQL resolver failed with %s at %s',
                     type(original).__name__, formatted.get('path'))
        formatted['message'] = INTERNAL_ERROR
    return formatted


def _json_error(status, message, headers=None):
    return Response(json.dumps({'errors': [{'message': message}]}),
                    status=status, headers=headers,
                    content_type='application/json')


class ProtectedGraphQLView(GraphQLView):
    """GraphQLView that requires the API key and JSON request bodies."""

    methods = ['GET', 'POST']
    api_key = None
    format_error = staticmethod(safe_format_error)

    def dispatch_request(self):
        if (request.method == 'GET' and 'raw' not in request.args
                and self.request_wants_html()):
            return Response(GRAPHIQL_PAGE, mimetype='text/html')
        if not key_matches(self.api_key, request.headers.get('Authorization')):
            return _json_error(401, 'Unauthorized',
                               headers={'WWW-Authenticate': 'Bearer'})
        if request.method == 'POST' and request.mimetype != 'application/json':
            return _json_error(415, 'Content-Type must be application/json')
        return super(ProtectedGraphQLView, self).dispatch_request()


def create_app(manager=None, api_key=None):
    """Build the Flask app around ``manager`` (or one built from config).

    ``api_key`` defaults to ``auth.load_api_key()``, which raises if no key
    is configured, so the app never starts without authentication.
    """
    if api_key is None:
        api_key = load_api_key()
    _install_log_filter()
    if manager is None:
        manager = build_manager()

    app = Flask(__name__)
    app.add_url_rule(
        '/graphql',
        view_func=ProtectedGraphQLView.as_view(
            'graphql', schema=schema, graphiql=False, root_value=manager,
            api_key=api_key),
    )

    @app.route('/healthz')
    def healthz():
        return jsonify(status='ok', providers=manager.provider_names())

    @app.after_request
    def security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    return app
