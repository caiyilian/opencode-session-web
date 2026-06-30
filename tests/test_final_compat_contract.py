from collections import defaultdict

import app as webapp


def test_final_user_workflow_routes_remain_registered():
    app = webapp.create_app({"TESTING": True})
    route_methods = defaultdict(set)

    for rule in app.url_map.iter_rules():
        route_methods[rule.rule].update(rule.methods - {"HEAD", "OPTIONS"})

    expected_routes = {
        "/": {"GET"},
        "/api/stats": {"GET"},
        "/api/stats/tokens": {"GET"},
        "/api/sessions": {"GET"},
        "/api/sessions/<session_id>": {"GET", "DELETE"},
        "/api/messages/<message_id>": {"GET"},
        "/api/directories": {"GET"},
        "/api/workspace/projects": {"GET"},
        "/api/workspace/tasks": {"GET", "POST"},
        "/api/workspace/tasks/<task_id>": {"PATCH"},
        "/api/workspace/git": {"GET"},
        "/api/models": {"GET"},
        "/api/available-models": {"GET"},
        "/api/sessions/compare": {"GET"},
        "/api/sessions/<session_id>/stream": {"GET"},
        "/api/sessions/new": {"POST"},
        "/api/sessions/<session_id>/fork": {"POST"},
        "/api/sessions/<session_id>/undo": {"POST"},
        "/api/files": {"GET"},
        "/api/events": {"GET"},
        "/frontend/assets/<path:filename>": {"GET"},
    }

    missing = {
        route: sorted(methods - route_methods.get(route, set()))
        for route, methods in expected_routes.items()
        if methods - route_methods.get(route, set())
    }

    assert missing == {}
